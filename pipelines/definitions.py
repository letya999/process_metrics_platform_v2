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
    aging_data_quality_check,
    aging_extended_data_quality_check,
    backlog_growth_data_quality_check,
    cfd_data_quality_check,
    check_lead_time_no_nulls,
    check_lead_time_positive,
    check_throughput_no_future_dates,
    check_velocity_completion_rate_valid,
    cycle_time_ext_data_quality_check,
    delivery_data_quality_check,
    estimation_data_quality_check,
    flow_dynamics_data_quality_check,
    flow_efficiency_data_quality_check,
    input_flow_data_quality_check,
    lead_time_data_quality_check,
    metrics_metadata_contract_check,
    quality_data_quality_check,
    # New metrics checks
    sprint_health_data_quality_check,
    throughput_data_quality_check,
    ttm_data_quality_check,
    velocity_data_quality_check,
    waste_data_quality_check,
)
from pipelines.jobs.schedules import jobs, schedules
from pipelines.jobs.schedules import sensors as schedule_sensors
from pipelines.resources.database import database_resource

# Import partitions and sensor
try:
    from pipelines.partitions import (
        project_partitions,
        sync_project_partitions_sensor,
    )

    sensors = [sync_project_partitions_sensor]
except ImportError:
    project_partitions = None
    sensors = []

sensors.extend(schedule_sensors)

# Load all assets from modules
jira_assets = load_assets_from_modules([jira])
metrics_assets = load_assets_from_modules([metrics])

# Add partitioned asset if available

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
    velocity_data_quality_check,
    lead_time_data_quality_check,
    throughput_data_quality_check,
    cfd_data_quality_check,
    backlog_growth_data_quality_check,
    ttm_data_quality_check,
    aging_data_quality_check,
    flow_efficiency_data_quality_check,
    # New metrics checks
    sprint_health_data_quality_check,
    flow_dynamics_data_quality_check,
    quality_data_quality_check,
    delivery_data_quality_check,
    cycle_time_ext_data_quality_check,
    waste_data_quality_check,
    estimation_data_quality_check,
    input_flow_data_quality_check,
    aging_extended_data_quality_check,
    metrics_metadata_contract_check,
]

# Create Definitions
defs = Definitions(
    assets=[*jira_assets, *metrics_assets],
    asset_checks=asset_checks,
    jobs=jobs,
    schedules=schedules,
    sensors=sensors,
    resources={
        "database": database_resource,
    },
)
