"""Exercise the quality check through Dagster's execution engine."""

import json

import dagster as dg
import pytest

from etl import config
from orchestration.assets import cross_reference_has_comparable_substances


@pytest.mark.parametrize("count, expected_success", [(0, False), (1, True)])
def test_quality_check_controls_dashboard(tmp_path, monkeypatch, count, expected_success):
    monkeypatch.setattr(config, "GOLD_DIR", tmp_path)
    dashboard_path = tmp_path / "dashboard.html"

    @dg.asset(name="cross_reference_asset")
    def synthetic_cross_reference():
        folder = tmp_path / "cruzamento"
        folder.mkdir()
        (folder / "resumo.json").write_text(
            json.dumps({"n_substancias_comparaveis": count}), encoding="utf-8"
        )

    @dg.asset(name="dashboard_asset", deps=[synthetic_cross_reference])
    def synthetic_dashboard():
        dashboard_path.write_text("generated", encoding="utf-8")

    result = dg.materialize(
        [synthetic_cross_reference, synthetic_dashboard,
         cross_reference_has_comparable_substances],
        raise_on_error=False,
    )

    assert result.success is expected_success
    assert dashboard_path.exists() is expected_success
    evaluations = result.get_asset_check_evaluations()
    assert len(evaluations) == 1
    assert evaluations[0].passed is expected_success
