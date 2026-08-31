"""Cross-references Produção Bruta and Produção Beneficiada via SQL (DuckDB).

This is the one place in the pipeline where a real multi-table join earns
its keep, so it's written as SQL against the two Silver parquet files
directly rather than as another pandas/Polars join — DuckDB reads Parquet
natively and is genuinely the most direct tool for "aggregate two tables on
a shared key and compare them."

The join key is `Substância Mineral` (aggregated first, then joined) rather
than the full (ano, UF, substância) grain: raw and processed output for the
same substance don't necessarily get reported from the same mine in the
same year, so joining at row grain would silently drop real volume. Value
(R$) is used, not physical quantity — Beneficiada's quantities aren't in a
uniform unit (see silver.py), so R$ is the only metric safe to compare
across the two tables.

Output feeds the dashboard's "Beneficiamento" section: how much value
processing adds over selling ore raw, per substance and per year.
"""

import json
import logging
from pathlib import Path

import duckdb

from etl.config import BENEFICIADA, BRUTA, DatasetSpec, GOLD_DIR

logger = logging.getLogger(__name__)

# Below this many source records on either side, a value-add ratio is too
# noisy to publish as a ranking (a single declared row can swing it wildly).
MIN_RECORDS_PER_SIDE = 5


def _write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=str)
    logger.info("Cruzamento: wrote %s", path)


def run_cross_reference(bruta: DatasetSpec = BRUTA, beneficiada: DatasetSpec = BENEFICIADA, out_dir: Path = None) -> dict:
    out_dir = out_dir or (GOLD_DIR / "cruzamento")
    con = duckdb.connect()

    con.execute(f"""
        CREATE OR REPLACE VIEW bruta_by_sub AS
        SELECT "{bruta.col_substancia}" AS substancia,
               SUM("{bruta.col_valor_venda}") AS valor_venda_bruta,
               COUNT(*) AS n_bruta
        FROM read_parquet('{bruta.silver_parquet.as_posix()}')
        GROUP BY 1
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW ben_by_sub AS
        SELECT "{beneficiada.col_substancia}" AS substancia,
               SUM("{beneficiada.col_valor_venda}") AS valor_venda_beneficiada,
               COUNT(*) AS n_beneficiada
        FROM read_parquet('{beneficiada.silver_parquet.as_posix()}')
        GROUP BY 1
    """)

    por_substancia = con.execute("""
        SELECT
            COALESCE(b.substancia, f.substancia) AS substancia,
            COALESCE(b.valor_venda_bruta, 0) AS valor_venda_bruta,
            COALESCE(f.valor_venda_beneficiada, 0) AS valor_venda_beneficiada,
            COALESCE(f.valor_venda_beneficiada, 0) - COALESCE(b.valor_venda_bruta, 0) AS valor_agregado,
            CASE WHEN COALESCE(b.valor_venda_bruta, 0) > 0
                 THEN f.valor_venda_beneficiada / b.valor_venda_bruta
                 ELSE NULL END AS fator_agregacao,
            COALESCE(b.n_bruta, 0) AS n_bruta,
            COALESCE(f.n_beneficiada, 0) AS n_beneficiada
        FROM bruta_by_sub b
        FULL OUTER JOIN ben_by_sub f USING (substancia)
        ORDER BY valor_agregado DESC NULLS LAST
    """).fetchdf()

    por_ano = con.execute(f"""
        WITH b AS (
            SELECT "{bruta.col_ano}" AS ano, SUM("{bruta.col_valor_venda}") AS valor_venda_bruta
            FROM read_parquet('{bruta.silver_parquet.as_posix()}') GROUP BY 1
        ), f AS (
            SELECT "{beneficiada.col_ano}" AS ano, SUM("{beneficiada.col_valor_venda}") AS valor_venda_beneficiada
            FROM read_parquet('{beneficiada.silver_parquet.as_posix()}') GROUP BY 1
        )
        SELECT COALESCE(b.ano, f.ano) AS ano,
               COALESCE(b.valor_venda_bruta, 0) AS valor_venda_bruta,
               COALESCE(f.valor_venda_beneficiada, 0) AS valor_venda_beneficiada
        FROM b FULL OUTER JOIN f USING (ano)
        ORDER BY ano
    """).fetchdf()

    con.close()

    substancia_records = por_substancia.to_dict(orient="records")
    comparable = [
        r for r in substancia_records
        if r["n_bruta"] >= MIN_RECORDS_PER_SIDE and r["n_beneficiada"] >= MIN_RECORDS_PER_SIDE
    ]

    artifacts = {
        "por_substancia.json": substancia_records,
        "por_substancia_comparavel.json": comparable,
        "por_ano.json": por_ano.to_dict(orient="records"),
        "resumo.json": {
            "n_substancias_bruta": int((por_substancia["n_bruta"] > 0).sum()),
            "n_substancias_beneficiada": int((por_substancia["n_beneficiada"] > 0).sum()),
            "n_substancias_ambas": int(((por_substancia["n_bruta"] > 0) & (por_substancia["n_beneficiada"] > 0)).sum()),
            "n_substancias_comparaveis": len(comparable),
            "min_registros_por_lado": MIN_RECORDS_PER_SIDE,
        },
    }
    for filename, obj in artifacts.items():
        _write_json(obj, out_dir / filename)
    return artifacts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_cross_reference()
