"""Assembles the single-file dashboard from the Silver + cross-reference layers.

Builds a compact row-level payload per dataset (categorical columns
dictionary-encoded to integer indices) plus the pre-aggregated Bruta x
Beneficiada cross-reference, and injects all three, plus the vanilla-JS app,
into template.html. The output is one self-contained HTML file — no CDN, no
build step, opens straight from disk.
"""

import json
import logging
from pathlib import Path

import polars as pl

from etl.config import BENEFICIADA, BRUTA, DASHBOARD_HTML, DatasetSpec, GOLD_DIR

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = DASHBOARD_DIR / "template.html"
APP_JS_PATH = DASHBOARD_DIR / "app.js"


def build_dataset_payload(spec: DatasetSpec) -> dict:
    df = pl.read_parquet(spec.silver_parquet)

    ufs = sorted(df.select(pl.col(spec.col_uf).cast(pl.Utf8)).unique().to_series().drop_nulls().to_list())
    classes = sorted(df.select(pl.col(spec.col_classe).cast(pl.Utf8)).unique().to_series().drop_nulls().to_list())
    substancias = sorted(df.select(pl.col(spec.col_substancia).cast(pl.Utf8)).unique().to_series().drop_nulls().to_list())

    uf_idx = {u: i for i, u in enumerate(ufs)}
    cl_idx = {c: i for i, c in enumerate(classes)}
    sb_idx = {s: i for i, s in enumerate(substancias)}

    from etl.config import UF_REGIAO

    select_exprs = [
        pl.col(spec.col_ano),
        pl.col(spec.col_uf).cast(pl.Utf8).replace_strict(uf_idx).alias("uf_i"),
        pl.col(spec.col_classe).cast(pl.Utf8).replace_strict(cl_idx).alias("cl_i"),
        pl.col(spec.col_substancia).cast(pl.Utf8).replace_strict(sb_idx).alias("sb_i"),
    ]
    if spec.quantities_uniform_unit:
        select_exprs.append(pl.col(spec.col_qtd_producao).round(1))
        select_exprs.append(pl.col(spec.col_qtd_venda).round(1))
    select_exprs.append(pl.col(spec.col_valor_venda).round(2))
    if spec.quantities_uniform_unit:
        select_exprs.append(pl.col(spec.col_qtd_transformacao).round(1))
    select_exprs.append(pl.col(spec.col_valor_transformacao).round(2))
    if spec.quantities_uniform_unit:
        select_exprs.append(pl.col(spec.col_qtd_transferencia).round(1))
    select_exprs.append(pl.col(spec.col_valor_transferencia).round(2))

    rows = df.select(select_exprs).rows()

    regioes_presentes = sorted({UF_REGIAO[u] for u in ufs})

    return {
        "ufs": ufs,
        "classes": classes,
        "substancias": substancias,
        "regiaoByUf": {u: UF_REGIAO[u] for u in ufs},
        "regioesSet": {r: True for r in regioes_presentes},
        "anoMin": int(df[spec.col_ano].min()),
        "anoMax": int(df[spec.col_ano].max()),
        "rows": rows,
    }


def build_cruzamento_payload(gold_dir: Path = GOLD_DIR) -> dict:
    cruz_dir = gold_dir / "cruzamento"
    with open(cruz_dir / "por_substancia_comparavel.json", encoding="utf-8") as f:
        por_sub = json.load(f)
    with open(cruz_dir / "por_ano.json", encoding="utf-8") as f:
        por_ano = json.load(f)
    with open(cruz_dir / "resumo.json", encoding="utf-8") as f:
        resumo = json.load(f)

    return {
        "porSubstanciaComparavel": [
            {
                "substancia": r["substancia"],
                "valorAgregado": r["valor_agregado"],
                "fatorAgregacao": r["fator_agregacao"],
            }
            for r in por_sub
        ],
        "porAno": [
            {"ano": r["ano"], "valorVendaBruta": r["valor_venda_bruta"], "valorVendaBeneficiada": r["valor_venda_beneficiada"]}
            for r in por_ano
        ],
        "resumo": {
            "nSubstanciasAmbas": resumo["n_substancias_ambas"],
            "nSubstanciasComparaveis": resumo["n_substancias_comparaveis"],
        },
    }


def build_dashboard(out_path: Path = DASHBOARD_HTML) -> Path:
    payload = {
        "bruta": build_dataset_payload(BRUTA),
        "beneficiada": build_dataset_payload(BENEFICIADA),
        "cruzamento": build_cruzamento_payload(),
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Defensive: a "</script>" substring anywhere in the data (or in the app
    # JS) would prematurely close the inline <script> tag and break parsing.
    data_json = data_json.replace("</script", "<\\/script")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    app_js = APP_JS_PATH.read_text(encoding="utf-8")

    html = template.replace("__DATA_JSON__", data_json).replace("__APP_JS__", app_js)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    n_rows = len(payload["bruta"]["rows"]) + len(payload["beneficiada"]["rows"])
    logger.info("Dashboard: wrote %s (%.0f KB, %s rows embedded)", out_path, size_kb, n_rows)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_dashboard()
