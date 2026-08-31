"""Gold layer: analysis-ready aggregates for the dashboard, built with pandas.

Bronze/Silver use Polars for throughput on the row-level clean. Gold
switches to pandas deliberately: this stage is exploratory aggregation —
pivot_table, groupby-transform for within-group shares, and pct_change for
growth rates — the corner of the ecosystem pandas still covers most tersely.

Generic over `DatasetSpec`. The one place the two datasets genuinely diverge
is `destino_mix`: Bruta's quantities are uniformly tonnes, so a % share of
*quantity* is meaningful; Beneficiada's quantities mix t/kg/ct row to row
(see silver.py), so its destination mix is expressed as a % share of *value*
(R$) instead — still answers "where does output go", without silently
summing incompatible units.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from etl.config import DatasetSpec, GOLD_DIR

logger = logging.getLogger(__name__)


def _write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=str)
    logger.info("Gold: wrote %s", path)


def build_kpis(df: pd.DataFrame, spec: DatasetSpec) -> dict:
    total_valor = df[spec.col_valor_venda].sum() + df[spec.col_valor_transformacao].sum() + df[spec.col_valor_transferencia].sum()
    kpis = {
        "n_registros": int(len(df)),
        "ano_min": int(df[spec.col_ano].min()),
        "ano_max": int(df[spec.col_ano].max()),
        "n_substancias": int(df[spec.col_substancia].nunique()),
        "n_ufs": int(df[spec.col_uf].nunique()),
        "valor_venda_total_r$": float(df[spec.col_valor_venda].sum()),
        "valor_movimentado_total_r$": float(total_valor),
        "pct_registros_com_teor_contido": float(df["flag_possui_teor_contido"].mean()),
        "pct_registros_producao_zero": float(df["flag_producao_zero"].mean()),
    }
    if spec.quantities_uniform_unit:
        kpis["producao_total_t"] = float(df[spec.col_qtd_producao].sum())
        kpis["pct_registros_destinacao_excede_producao"] = float(df["flag_destinacao_excede_producao"].mean())
    return kpis


def build_serie_temporal(df: pd.DataFrame, spec: DatasetSpec) -> list:
    agg_map = {
        "valor_venda_r$": (spec.col_valor_venda, "sum"),
        "valor_transformacao_r$": (spec.col_valor_transformacao, "sum"),
        "valor_transferencia_r$": (spec.col_valor_transferencia, "sum"),
        "n_registros": (spec.col_valor_venda, "size"),
    }
    if spec.quantities_uniform_unit:
        agg_map["producao_t"] = (spec.col_qtd_producao, "sum")

    yearly = df.groupby(spec.col_ano, observed=True).agg(**agg_map).sort_index()
    yearly["crescimento_valor_venda_yoy"] = yearly["valor_venda_r$"].pct_change()
    if spec.quantities_uniform_unit:
        yearly["crescimento_producao_yoy"] = yearly["producao_t"].pct_change()
    yearly = yearly.reset_index().rename(columns={spec.col_ano: "ano"})
    return yearly.to_dict(orient="records")


def build_by_uf(df: pd.DataFrame, spec: DatasetSpec) -> list:
    agg = (
        df.groupby([spec.col_uf, "Regiao"], observed=True)
        .agg(**{"valor_venda_r$": (spec.col_valor_venda, "sum"), "n_registros": (spec.col_valor_venda, "size")})
        .reset_index()
        .rename(columns={spec.col_uf: "uf", "Regiao": "regiao"})
    )
    total = agg["valor_venda_r$"].sum()
    agg["pct_valor_nacional"] = agg["valor_venda_r$"] / total if total else 0.0
    return agg.sort_values("valor_venda_r$", ascending=False).to_dict(orient="records")


def build_by_substancia(df: pd.DataFrame, spec: DatasetSpec, top_n: int = 20) -> list:
    agg = (
        df.groupby(spec.col_substancia, observed=True)
        .agg(**{"valor_venda_r$": (spec.col_valor_venda, "sum"), "n_registros": (spec.col_valor_venda, "size")})
        .reset_index()
        .rename(columns={spec.col_substancia: "substancia"})
    )
    agg["pct_valor_nacional"] = agg["valor_venda_r$"] / agg["valor_venda_r$"].sum()
    return agg.sort_values("valor_venda_r$", ascending=False).head(top_n).to_dict(orient="records")


def build_by_classe(df: pd.DataFrame, spec: DatasetSpec) -> list:
    agg = (
        df.groupby(spec.col_classe, observed=True)
        .agg(**{"valor_venda_r$": (spec.col_valor_venda, "sum"), "n_registros": (spec.col_valor_venda, "size")})
        .reset_index()
        .rename(columns={spec.col_classe: "classe"})
    )
    agg["pct_valor_nacional"] = agg["valor_venda_r$"] / agg["valor_venda_r$"].sum()
    return agg.sort_values("valor_venda_r$", ascending=False).to_dict(orient="records")


def build_destino_mix(df: pd.DataFrame, spec: DatasetSpec) -> list:
    """pivot_table over the three destinations, normalized to a yearly 100%
    share. Uses quantity when the dataset's units are uniform (Bruta);
    otherwise falls back to value share (Beneficiada) — see module docstring.
    """
    if spec.quantities_uniform_unit:
        values = [spec.col_qtd_venda, spec.col_qtd_transformacao, spec.col_qtd_transferencia]
        rename = {spec.col_qtd_venda: "venda", spec.col_qtd_transformacao: "transformacao", spec.col_qtd_transferencia: "transferencia"}
    else:
        values = [spec.col_valor_venda, spec.col_valor_transformacao, spec.col_valor_transferencia]
        rename = {spec.col_valor_venda: "venda", spec.col_valor_transformacao: "transformacao", spec.col_valor_transferencia: "transferencia"}

    pivot = pd.pivot_table(df, index=spec.col_ano, values=values, aggfunc="sum").rename(columns=rename)
    totals = pivot.sum(axis=1)
    shares = pivot.div(totals.where(totals != 0), axis=0).fillna(0.0)
    shares.columns = [f"pct_{c}" for c in shares.columns]

    out = pivot.join(shares).reset_index().rename(columns={spec.col_ano: "ano"})
    return out.to_dict(orient="records")


def build_top_uf_substancia(df: pd.DataFrame, spec: DatasetSpec, top_n: int = 15) -> list:
    agg = (
        df.groupby([spec.col_uf, spec.col_substancia], observed=True)[spec.col_valor_venda]
        .sum()
        .reset_index()
        .rename(columns={spec.col_uf: "uf", spec.col_substancia: "substancia", spec.col_valor_venda: "valor_venda_r$"})
    )
    return agg.sort_values("valor_venda_r$", ascending=False).head(top_n).to_dict(orient="records")


def run_gold(spec: DatasetSpec, out_dir: Path = None) -> dict:
    out_dir = out_dir or (GOLD_DIR / spec.key)
    logger.info("Gold[%s]: reading silver parquet %s", spec.key, spec.silver_parquet)
    df = pd.read_parquet(spec.silver_parquet)

    artifacts = {
        "kpis.json": build_kpis(df, spec),
        "serie_temporal.json": build_serie_temporal(df, spec),
        "by_uf.json": build_by_uf(df, spec),
        "by_substancia.json": build_by_substancia(df, spec),
        "by_classe.json": build_by_classe(df, spec),
        "destino_mix.json": build_destino_mix(df, spec),
        "top_uf_substancia.json": build_top_uf_substancia(df, spec),
    }
    for filename, obj in artifacts.items():
        _write_json(obj, out_dir / filename)
    return artifacts


if __name__ == "__main__":
    from etl.config import BENEFICIADA, BRUTA

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_gold(BRUTA)
    run_gold(BENEFICIADA)
