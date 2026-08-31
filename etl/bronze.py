"""Bronze layer: ingest a raw ANM CSV with zero interpretation.

Generic over `DatasetSpec` — Produção Bruta and Produção Beneficiada share
this exact ingestion logic (read as string, tag with lineage metadata, write
parquet); only their column names differ, and that lives in config.py.
"""

import logging

import polars as pl

from etl.config import DatasetSpec

logger = logging.getLogger(__name__)


def run_bronze(spec: DatasetSpec) -> pl.DataFrame:
    logger.info("Bronze[%s]: reading %s (encoding=%s)", spec.key, spec.raw_csv, "windows-1252")

    df = pl.read_csv(
        spec.raw_csv,
        encoding="windows-1252",
        separator=",",
        infer_schema_length=0,  # everything as Utf8 — no premature type guessing
        null_values=[""],
    )

    missing = set(spec.raw_columns) - set(df.columns)
    if missing:
        raise ValueError(f"Bronze[{spec.key}]: expected columns not found in source file: {missing}")

    df = df.with_row_index(name="_row_id").with_columns(
        pl.lit(spec.raw_csv.name).alias("_source_file"),
    )

    spec.bronze_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(spec.bronze_parquet)
    logger.info("Bronze[%s]: wrote %s rows, %s cols -> %s", spec.key, df.height, df.width, spec.bronze_parquet)
    return df


if __name__ == "__main__":
    from etl.config import BENEFICIADA, BRUTA

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_bronze(BRUTA)
    run_bronze(BENEFICIADA)
