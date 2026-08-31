"""Dagster entry point: `dagster dev -m orchestration.definitions`.

One job materializes the whole graph. Schedule is daily and stopped by
default — ANM/RAL data only refreshes yearly, but daily keeps the next
tick visible in the UI without waiting a year.
"""

import dagster as dg

from orchestration import assets

all_assets = dg.load_assets_from_modules([assets])

build_pipeline_job = dg.define_asset_job(
    name="build_pipeline_job",
    selection=dg.AssetSelection.all(),
)

daily_schedule = dg.ScheduleDefinition(
    job=build_pipeline_job,
    cron_schedule="0 6 * * *",
    default_status=dg.DefaultScheduleStatus.STOPPED,
)

defs = dg.Definitions(
    assets=all_assets,
    asset_checks=[assets.cross_reference_has_comparable_substances],
    jobs=[build_pipeline_job],
    schedules=[daily_schedule],
)
