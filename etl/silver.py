"""Silver layer: type, clean, and validate a Bronze table.

Bruta reports quantities in tonnes only (unit's baked into the column
name), so summing them across rows is fine. Beneficiada's quantities are in
whatever unit the product sells in — t, kg, ct, varying row to row — so
summing would mix carats and tonnes; only its R$ columns get aggregated.
`spec.quantities_uniform_unit` flags which case applies; gold.py and the
dashboard follow the same rule.
"""

import logging

import polars as pl

from etl.config import DatasetSpec, UF_REGIAO, VALID_UFS, NULL_SENTINEL_UNIDADE

logger = logging.getLogger(__name__)


def parse_br_decimal(col: str) -> pl.Expr:
    """Brazilian-locale decimal string (decimal comma, occasional scientific
    notation, e.g. "155024,500000" / "4,0000000000000001E-2") -> Float64.
    """
    return (
        pl.col(col)
        .str.replace_all(".", "", literal=True)  # defensive: strip any thousands dot
        .str.replace_all(",", ".", literal=True)
        .cast(pl.Float64, strict=False)
        .alias(col)
    )


def run_silver(spec: DatasetSpec) -> pl.DataFrame:
    logger.info("Silver[%s]: reading bronze parquet %s", spec.key, spec.bronze_parquet)
    df = pl.read_parquet(spec.bronze_parquet)
    n_before = df.height

    df = df.with_columns(pl.col(spec.col_ano).cast(pl.Int16))

    decimal_exprs = [parse_br_decimal(c) for c in spec.br_decimal_columns]
    df = df.with_columns(decimal_exprs)

    n_parse_failures = sum(df.filter(pl.col(c).is_null()).height for c in spec.br_decimal_columns)
    if n_parse_failures:
        logger.warning("Silver[%s]: %s null values produced while parsing decimal columns", spec.key, n_parse_failures)

    df = df.with_columns(
        pl.when(pl.col(spec.col_unidade_contido) == NULL_SENTINEL_UNIDADE)
        .then(None)
        .otherwise(pl.col(spec.col_unidade_contido))
        .alias(spec.col_unidade_contido)
    )

    df = df.with_columns([pl.col(c).cast(pl.Categorical) for c in spec.categorical_columns])

    present_ufs = set(df.select(pl.col(spec.col_uf).cast(pl.Utf8)).unique().to_series().drop_nulls().to_list())
    unknown = sorted(present_ufs - VALID_UFS)
    if unknown:
        raise ValueError(f"Silver[{spec.key}]: unrecognized UF codes found: {unknown}")

    df = df.with_columns(
        pl.col(spec.col_uf).cast(pl.Utf8).replace_strict(UF_REGIAO, default=None).cast(pl.Categorical).alias("Regiao"),
    )

    # R$ totals are unit-agnostic — always safe to sum, for both datasets.
    df = df.with_columns(
        (pl.col(spec.col_valor_venda) + pl.col(spec.col_valor_transformacao) + pl.col(spec.col_valor_transferencia)).alias("Valor_Total_R$"),
    )
    df = df.with_columns(
        pl.when(pl.col("Valor_Total_R$") > 0)
        .then(pl.col(spec.col_valor_venda) / pl.col("Valor_Total_R$"))
        .otherwise(None)
        .alias("Pct_Valor_Venda"),
    )

    df = df.with_columns(
        (pl.col(spec.col_qtd_producao) <= 0).alias("flag_producao_zero"),
        pl.col(spec.col_unidade_contido).is_not_null().alias("flag_possui_teor_contido"),
    )

    if spec.quantities_uniform_unit:
        # Only meaningful when every quantity column is in the same unit
        # (Bruta: always tonnes) — see module docstring.
        TOLERANCE = 1.01
        df = df.with_columns(
            (pl.col(spec.col_qtd_venda) + pl.col(spec.col_qtd_transformacao) + pl.col(spec.col_qtd_transferencia)).alias("Qtd_Total_Destinada"),
        )
        df = df.with_columns(
            (pl.col("Qtd_Total_Destinada") > pl.col(spec.col_qtd_producao) * TOLERANCE).alias("flag_destinacao_excede_producao"),
        )

    spec.silver_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(spec.silver_parquet)

    logger.info("Silver[%s]: %s rows in -> %s rows out -> %s", spec.key, n_before, df.height, spec.silver_parquet)
    return df


if __name__ == "__main__":
    from etl.config import BENEFICIADA, BRUTA

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_silver(BRUTA)
    run_silver(BENEFICIADA)
