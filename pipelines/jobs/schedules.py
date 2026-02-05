"""Dagster schedules for automated pipeline execution.

This module defines cron schedules for running data sync jobs:
- Daily Jira sync at 6:00 AM UTC
- Hourly metrics refresh
"""

from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    ScheduleDefinition,
    define_asset_job,
)

# Define jobs for scheduling

# Job: Full Jira sync (raw → clean → metrics)
jira_sync_job = define_asset_job(
    name="jira_sync_job",
    selection=AssetSelection.groups("jira_raw", "jira_clean", "metrics"),
    description="Full Jira data sync: raw → clean → metrics refresh",
)

# Job: Jira raw only (useful for incremental loads)
jira_raw_job = define_asset_job(
    name="jira_raw_job",
    selection=AssetSelection.groups("jira_raw"),
    description="Load raw data from Jira API",
)

# Job: Clean transformation only
jira_clean_job = define_asset_job(
    name="jira_clean_job",
    selection=AssetSelection.groups("jira_clean"),
    description="Transform raw Jira data to clean layer",
)

# Job: Metrics refresh only
metrics_refresh_job = define_asset_job(
    name="metrics_refresh_job",
    selection=AssetSelection.groups("metrics"),
    description="Refresh all metrics materialized views",
)

# Define schedules

# Schedule: Daily full sync at 6 AM UTC
daily_jira_sync_schedule = ScheduleDefinition(
    job=jira_sync_job,
    cron_schedule="0 6 * * *",  # 6:00 AM UTC daily
    default_status=DefaultScheduleStatus.STOPPED,  # Start stopped, enable manually
    execution_timezone="UTC",
)

# Schedule: Hourly metrics refresh
hourly_metrics_refresh_schedule = ScheduleDefinition(
    job=metrics_refresh_job,
    cron_schedule="0 * * * *",  # Every hour at minute 0
    default_status=DefaultScheduleStatus.STOPPED,
    execution_timezone="UTC",
)

# Job: Recalculate Lead Time (Fact + View)
lead_time_recalc_job = define_asset_job(
    name="recalculate_lead_time_job",
    selection=AssetSelection.assets("calculate_lead_time", "metrics_lead_time"),
    description="Recalculate Lead Time facts and refresh view",
)

# Job: Recalculate Velocity (Fact + View)
velocity_recalc_job = define_asset_job(
    name="recalculate_velocity_job",
    selection=AssetSelection.assets("calculate_velocity", "metrics_velocity"),
    description="Recalculate Velocity facts and refresh view",
)

# Job: Recalculate Throughput (Fact + View)
throughput_recalc_job = define_asset_job(
    name="recalculate_throughput_job",
    selection=AssetSelection.assets("calculate_throughput", "metrics_throughput"),
    description="Recalculate Throughput facts and refresh view",
)

# Job: Recalculate CFD (Fact only)
cfd_recalc_job = define_asset_job(
    name="recalculate_cfd_job",
    selection=AssetSelection.assets("calculate_cumulative_flow_diagram"),
    description="Recalculate Cumulative Flow Diagram facts",
)

# Job: Recalculate Backlog Health (Fact only)
backlog_health_recalc_job = define_asset_job(
    name="recalculate_backlog_health_job",
    selection=AssetSelection.assets("calculate_backlog_health"),
    description="Recalculate Backlog Health facts",
)

# Job: Recalculate Time to Market (Fact only)
time_to_market_recalc_job = define_asset_job(
    name="recalculate_time_to_market_job",
    selection=AssetSelection.assets("calculate_time_to_market"),
    description="Recalculate Time to Market facts",
)


# Export all jobs and schedules
jobs = [
    jira_sync_job,
    jira_raw_job,
    jira_clean_job,
    metrics_refresh_job,
    lead_time_recalc_job,
    velocity_recalc_job,
    throughput_recalc_job,
    cfd_recalc_job,
    backlog_health_recalc_job,
    time_to_market_recalc_job,
    # New Advanced Metrics
    define_asset_job(
        name="recalculate_advanced_metrics_job",
        selection=AssetSelection.assets("calculate_advanced_metrics"),
        description="Recalculate Pro Metrics (Aging, Flow Efficiency, Trends)",
    ),
]

schedules = [
    daily_jira_sync_schedule,
    hourly_metrics_refresh_schedule,
]
