"""Dagster assets wrapping the Estrato pipeline: bronze -> silver -> gold ->
cross-reference -> dashboard.

Transform logic lives in etl/ and dashboard/, unchanged from Estrato. Each
asset here is a thin call into that file-based pipeline (parquet in,
parquet out via etl.config paths) — Dagster just adds dependencies,
retries, and lineage on top.
"""

import dagster as dg

from dashboard import build_dashboard
from etl import bronze, cross_reference, gold, silver
from etl.config import BENEFICIADA, BRUTA

RETRY_POLICY = dg.RetryPolicy(max_retries=2, delay=5)


def _df_metadata(df) -> dict:
    return {
        "rows": dg.MetadataValue.int(df.height),
        "columns": dg.MetadataValue.int(df.width),
        "preview": dg.MetadataValue.text(str(df.head(5))),
    }


# ---------------------------------------------------------------------------
# Bronze
# ---------------------------------------------------------------------------


@dg.asset(group_name="bronze", compute_kind="polars", retry_policy=RETRY_POLICY)
def bronze_bruta() -> dg.MaterializeResult:
    df = bronze.run_bronze(BRUTA)
    return dg.MaterializeResult(metadata=_df_metadata(df))


@dg.asset(group_name="bronze", compute_kind="polars", retry_policy=RETRY_POLICY)
def bronze_beneficiada() -> dg.MaterializeResult:
    df = bronze.run_bronze(BENEFICIADA)
    return dg.MaterializeResult(metadata=_df_metadata(df))


# ---------------------------------------------------------------------------
# Silver
# ---------------------------------------------------------------------------


@dg.asset(deps=[bronze_bruta], group_name="silver", compute_kind="polars", retry_policy=RETRY_POLICY)
def silver_bruta() -> dg.MaterializeResult:
    df = silver.run_silver(BRUTA)
    return dg.MaterializeResult(metadata=_df_metadata(df))


@dg.asset(deps=[bronze_beneficiada], group_name="silver", compute_kind="polars", retry_policy=RETRY_POLICY)
def silver_beneficiada() -> dg.MaterializeResult:
    df = silver.run_silver(BENEFICIADA)
    return dg.MaterializeResult(metadata=_df_metadata(df))


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------


@dg.asset(deps=[silver_bruta], group_name="gold", compute_kind="pandas", retry_policy=RETRY_POLICY)
def gold_bruta() -> dg.MaterializeResult:
    artifacts = gold.run_gold(BRUTA)
    return dg.MaterializeResult(metadata={"artifacts": dg.MetadataValue.json(sorted(artifacts.keys()))})


@dg.asset(deps=[silver_beneficiada], group_name="gold", compute_kind="pandas", retry_policy=RETRY_POLICY)
def gold_beneficiada() -> dg.MaterializeResult:
    artifacts = gold.run_gold(BENEFICIADA)
    return dg.MaterializeResult(metadata={"artifacts": dg.MetadataValue.json(sorted(artifacts.keys()))})


# ---------------------------------------------------------------------------
# Cross-reference (SQL join via DuckDB across both Gold outputs)
# ---------------------------------------------------------------------------


@dg.asset(deps=[gold_bruta, gold_beneficiada], group_name="gold", compute_kind="duckdb", retry_policy=RETRY_POLICY)
def cross_reference_asset() -> dg.MaterializeResult:
    artifacts = cross_reference.run_cross_reference()
    resumo = artifacts["resumo.json"]
    return dg.MaterializeResult(metadata={k: dg.MetadataValue.int(v) for k, v in resumo.items() if isinstance(v, int)})


@dg.asset_check(asset=cross_reference_asset, blocking=True)
def cross_reference_has_comparable_substances() -> dg.AssetCheckResult:
    """Fails if the join finds zero comparable substances (e.g. a
    substance-name mismatch upstream)."""
    from etl.config import GOLD_DIR

    resumo_path = GOLD_DIR / "cruzamento" / "resumo.json"
    import json

    resumo = json.loads(resumo_path.read_text(encoding="utf-8"))
    n = resumo["n_substancias_comparaveis"]
    return dg.AssetCheckResult(passed=n > 0, metadata={"n_substancias_comparaveis": n})


# ---------------------------------------------------------------------------
# Dashboard (final artifact: single self-contained HTML file)
# ---------------------------------------------------------------------------


@dg.asset(deps=[cross_reference_asset], group_name="dashboard", compute_kind="python", retry_policy=RETRY_POLICY)
def dashboard_asset() -> dg.MaterializeResult:
    out_path = build_dashboard.build_dashboard()
    size_kb = out_path.stat().st_size / 1024
    return dg.MaterializeResult(
        metadata={
            "path": dg.MetadataValue.path(str(out_path)),
            "size_kb": dg.MetadataValue.float(round(size_kb, 1)),
        }
    )
