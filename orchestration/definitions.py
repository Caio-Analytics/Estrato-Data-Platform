"""Dagster entry point: `dagster dev -m orchestration.definitions`.

Defines one job that materializes the whole asset graph and a daily
schedule for it — the ANM/RAL source files are refreshed by the
government on an annual cadence, but daily is a deliberately conservative
default that's easy to demo in the UI (`dagster dev` shows the next tick
without waiting a year for it to matter).
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
