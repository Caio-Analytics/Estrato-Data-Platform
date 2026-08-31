"""Sanity checks for the pipeline. Not exhaustive — enough to catch a
schema drift in a future daily refresh of either source file, or a
regression in the decimal-parsing / null-handling logic documented in
etl/silver.py. Bronze/Silver/Gold tests are parametrized over both dataset
specs so the same assertions guard Produção Bruta and Produção Beneficiada.
"""

import polars as pl
import pytest

from etl import bronze, cross_reference, gold, silver
from etl.config import BENEFICIADA, BRUTA, DatasetSpec
from etl.silver import parse_br_decimal

SPECS = [BRUTA, BENEFICIADA]
SPEC_IDS = [s.key for s in SPECS]


@pytest.fixture(scope="module", params=SPECS, ids=SPEC_IDS)
def spec(request):
    return request.param


@pytest.fixture(scope="module")
def bronze_df(spec, tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp(f"{spec.key}_bronze")
    return bronze.run_bronze(_patched(spec, tmp_dir))


@pytest.fixture(scope="module")
def silver_df(spec, bronze_df, tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp(f"{spec.key}_silver")
    patched = _patched(spec, tmp_dir)
    bronze_df.write_parquet(patched.bronze_parquet)
    return silver.run_silver(patched)


def _patched(spec: DatasetSpec, tmp_dir):
    # DatasetSpec.bronze_parquet / silver_parquet are derived properties, not
    # fields — patch via a thin subclass-free wrapper that overrides them.
    import dataclasses

    class _Patched(DatasetSpec):
        @property
        def bronze_parquet(self):
            return tmp_dir / f"{self.key}_bronze.parquet"

        @property
        def silver_parquet(self):
            return tmp_dir / f"{self.key}_silver.parquet"

    return _Patched(**{f.name: getattr(spec, f.name) for f in dataclasses.fields(spec)})


class TestParseBrDecimal:
    def test_standard_decimal(self):
        df = pl.DataFrame({"x": ["155024,500000"]})
        assert df.select(parse_br_decimal("x"))["x"][0] == pytest.approx(155024.5)

    def test_zero_as_leading_comma(self):
        df = pl.DataFrame({"x": [",000000"]})
        assert df.select(parse_br_decimal("x"))["x"][0] == pytest.approx(0.0)

    def test_scientific_notation(self):
        df = pl.DataFrame({"x": ["4,0000000000000001E-2"]})
        assert df.select(parse_br_decimal("x"))["x"][0] == pytest.approx(0.04)

    def test_distinct_values_not_collapsed(self):
        # recon flagged '145' vs '14,5' as "the same value written two ways" —
        # they are 145 and 14.5, not duplicates once parsed.
        df = pl.DataFrame({"x": ["145", "14,5"]})
        out = df.select(parse_br_decimal("x"))["x"].to_list()
        assert out == pytest.approx([145.0, 14.5])


class TestBronze:
    def test_columns_present(self, spec, bronze_df):
        for c in spec.raw_columns:
            assert c in bronze_df.columns

    def test_everything_is_string_typed(self, spec, bronze_df):
        for c in spec.raw_columns:
            assert bronze_df.schema[c] == pl.Utf8


class TestSilver:
    def test_row_count_preserved(self, spec, bronze_df, silver_df):
        assert silver_df.height == bronze_df.height

    def test_no_row_lost_to_decimal_parsing(self, spec, silver_df):
        for c in spec.br_decimal_columns:
            assert silver_df[c].null_count() == 0

    def test_ano_base_is_plain_year_int(self, spec, silver_df):
        assert silver_df.schema[spec.col_ano] == pl.Int16
        assert silver_df[spec.col_ano].min() == 2010

    def test_uf_values_are_valid(self, spec, silver_df):
        from etl.config import VALID_UFS

        ufs = set(silver_df.select(pl.col(spec.col_uf).cast(pl.Utf8)).unique().to_series().to_list())
        assert ufs <= VALID_UFS

    def test_unidade_contido_sentinel_converted_to_null(self, spec, silver_df):
        from etl.config import NULL_SENTINEL_UNIDADE

        raw_dash_count = (
            silver_df.select(pl.col(spec.col_unidade_contido).cast(pl.Utf8))
            .to_series()
            .eq(NULL_SENTINEL_UNIDADE)
            .sum()
        )
        assert raw_dash_count == 0

    def test_regiao_populated_for_every_row(self, spec, silver_df):
        assert silver_df["Regiao"].null_count() == 0

    def test_quantity_total_only_computed_when_unit_uniform(self, spec, silver_df):
        if spec.quantities_uniform_unit:
            assert "Qtd_Total_Destinada" in silver_df.columns
        else:
            assert "Qtd_Total_Destinada" not in silver_df.columns


class TestGold:
    def test_kpis_consistent_with_silver(self, spec, silver_df, tmp_path):
        import dataclasses

        patched = _patched(spec, tmp_path)
        silver_df.write_parquet(patched.silver_parquet)
        artifacts = gold.run_gold(patched, out_dir=tmp_path / "gold")

        kpis = artifacts["kpis.json"]
        assert kpis["n_registros"] == silver_df.height
        assert kpis["ano_min"] == 2010
        assert kpis["ano_max"] == silver_df[spec.col_ano].max()
        assert 0.0 <= kpis["pct_registros_producao_zero" if spec.quantities_uniform_unit else "pct_registros_com_teor_contido"] <= 1.0

    def test_by_classe_shares_sum_to_one(self, spec, silver_df, tmp_path):
        patched = _patched(spec, tmp_path)
        silver_df.write_parquet(patched.silver_parquet)
        artifacts = gold.run_gold(patched, out_dir=tmp_path / "gold2")

        total_share = sum(row["pct_valor_nacional"] for row in artifacts["by_classe.json"])
        assert total_share == pytest.approx(1.0, abs=1e-6)


class TestCrossReference:
    @pytest.fixture(scope="class")
    def cruzamento(self, tmp_path_factory):
        # Independent of the parametrized `spec`/`silver_df` fixtures above —
        # this needs both datasets' Silver output at once, built fresh into
        # their own temp dirs so the test never depends on data/silver/
        # already existing on disk (e.g. a clean CI checkout).
        bruta_dir = tmp_path_factory.mktemp("cruz_bruta")
        ben_dir = tmp_path_factory.mktemp("cruz_ben")
        bruta_spec = _patched(BRUTA, bruta_dir)
        ben_spec = _patched(BENEFICIADA, ben_dir)
        bronze.run_bronze(bruta_spec)
        bronze.run_bronze(ben_spec)
        silver.run_silver(bruta_spec)
        silver.run_silver(ben_spec)

        out_dir = tmp_path_factory.mktemp("cruzamento")
        return cross_reference.run_cross_reference(bruta=bruta_spec, beneficiada=ben_spec, out_dir=out_dir)

    def test_summary_counts_are_consistent(self, cruzamento):
        resumo = cruzamento["resumo.json"]
        assert resumo["n_substancias_comparaveis"] <= resumo["n_substancias_ambas"]
        assert resumo["n_substancias_ambas"] <= min(resumo["n_substancias_bruta"], resumo["n_substancias_beneficiada"])

    def test_comparable_rows_meet_the_minimum_threshold(self, cruzamento):
        for row in cruzamento["por_substancia_comparavel.json"]:
            assert row["n_bruta"] >= cross_reference.MIN_RECORDS_PER_SIDE
            assert row["n_beneficiada"] >= cross_reference.MIN_RECORDS_PER_SIDE

    def test_valor_agregado_matches_the_difference(self, cruzamento):
        for row in cruzamento["por_substancia.json"]:
            expected = row["valor_venda_beneficiada"] - row["valor_venda_bruta"]
            assert row["valor_agregado"] == pytest.approx(expected, abs=1e-6)
