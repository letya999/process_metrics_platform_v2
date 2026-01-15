"""Dagster pipelines for Process Metrics Platform.

This is the main entry point for Dagster. It registers all assets,
jobs, schedules, and resources.
"""

from dagster import Definitions, load_assets_from_modules

from pipelines.assets import jira, metrics
from pipelines.assets.jira import (
    check_issues_have_required_fields,
    check_no_orphan_issues,
    check_release_issues_integrity,
    check_sprint_dates_valid,
    check_sprint_issues_integrity,
)
from pipelines.assets.metrics import (
    check_lead_time_no_nulls,
    check_lead_time_positive,
    check_throughput_no_future_dates,
    check_velocity_completion_rate_valid,
)
from pipelines.jobs.schedules import jobs, schedules
from pipelines.resources.database import database_resource

# Load all assets from modules
jira_assets = load_assets_from_modules([jira])
metrics_assets = load_assets_from_modules([metrics])

asset_checks = [
    check_no_orphan_issues,
    check_issues_have_required_fields,
    check_sprint_dates_valid,
    check_sprint_issues_integrity,
    check_release_issues_integrity,
    check_lead_time_no_nulls,
    check_lead_time_positive,
    check_velocity_completion_rate_valid,
    check_throughput_no_future_dates,
]

# Create Definitions
defs = Definitions(
    assets=[*jira_assets, *metrics_assets],
    asset_checks=asset_checks,
    jobs=jobs,
    schedules=schedules,
    resources={
        "database": database_resource,
    },
)
