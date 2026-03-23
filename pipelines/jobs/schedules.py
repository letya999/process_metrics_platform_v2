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

# Job: Recalculate Backlog Growth (Fact only)
backlog_growth_recalc_job = define_asset_job(
    name="recalculate_backlog_growth_job",
    selection=AssetSelection.assets("calculate_backlog_growth"),
    description="Recalculate Backlog Growth facts",
)

# Job: Recalculate Time to Market (Fact only)
time_to_market_recalc_job = define_asset_job(
    name="recalculate_time_to_market_job",
    selection=AssetSelection.assets("calculate_time_to_market"),
    description="Recalculate Time to Market facts",
)

# Job: Recalculate Sprint Health
sprint_health_recalc_job = define_asset_job(
    name="recalculate_sprint_health_job",
    selection=AssetSelection.assets("calculate_sprint_health"),
    description="Recalculate sprint health metrics (scope changes, burndown, spillover)",
)

# Job: Recalculate Flow Dynamics
flow_dynamics_recalc_job = define_asset_job(
    name="recalculate_flow_dynamics_job",
    selection=AssetSelection.assets("calculate_flow_dynamics"),
    description="Recalculate flow dynamics metrics (daily status entry, field changes)",
)

# Job: Recalculate Quality Metrics
quality_recalc_job = define_asset_job(
    name="recalculate_quality_metrics_job",
    selection=AssetSelection.assets("calculate_quality_metrics"),
    description="Recalculate quality metrics (defect density, backflow rate)",
)

# Job: Recalculate Delivery Metrics
delivery_recalc_job = define_asset_job(
    name="recalculate_delivery_metrics_job",
    selection=AssetSelection.assets("calculate_delivery_metrics"),
    description="Recalculate delivery metrics (release burnup scope/done)",
)

# Job: Recalculate Cycle Time Extended
cycle_time_ext_recalc_job = define_asset_job(
    name="recalculate_cycle_time_extended_job",
    selection=AssetSelection.assets("calculate_cycle_time_extended"),
    description="Recalculate extended cycle time metrics (lifetime, custom CT, epic delivery)",
)

# Job: Recalculate Waste Metrics
waste_recalc_job = define_asset_job(
    name="recalculate_waste_metrics_job",
    selection=AssetSelection.assets("calculate_waste_metrics"),
    description="Recalculate waste metrics (cancellation rate)",
)

# Job: Recalculate Estimation Metrics
estimation_recalc_job = define_asset_job(
    name="recalculate_estimation_metrics_job",
    selection=AssetSelection.assets("calculate_estimation_metrics"),
    description="Recalculate estimation metrics (estimate volatility)",
)

# Job: Recalculate Input Flow
input_flow_recalc_job = define_asset_job(
    name="recalculate_input_flow_job",
    selection=AssetSelection.assets("calculate_input_flow"),
    description="Recalculate input flow metrics (weekly issue intake)",
)

# Job: Recalculate Aging Extended
aging_extended_recalc_job = define_asset_job(
    name="recalculate_aging_extended_job",
    selection=AssetSelection.assets("calculate_aging_extended"),
    description="Recalculate extended aging metrics (blocked time, stale days)",
)

# Job: Ghost Cleanup (remove deleted issues)
jira_ghost_cleanup_job = define_asset_job(
    name="jira_ghost_cleanup_job",
    selection=AssetSelection.assets("jira_ghost_cleanup"),
    description="Cleanup issues from raw layer that were deleted in Jira",
)

# Schedule: Weekly ghost cleanup (Sunday at 2 AM)
weekly_ghost_cleanup_schedule = ScheduleDefinition(
    job=jira_ghost_cleanup_job,
    cron_schedule="0 2 * * 0",  # 2:00 AM UTC every Sunday
    default_status=DefaultScheduleStatus.STOPPED,
    execution_timezone="UTC",
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
    backlog_growth_recalc_job,
    time_to_market_recalc_job,
    # New metrics
    sprint_health_recalc_job,
    flow_dynamics_recalc_job,
    quality_recalc_job,
    delivery_recalc_job,
    cycle_time_ext_recalc_job,
    waste_recalc_job,
    estimation_recalc_job,
    input_flow_recalc_job,
    aging_extended_recalc_job,
    jira_ghost_cleanup_job,
]

schedules = [
    daily_jira_sync_schedule,
    hourly_metrics_refresh_schedule,
    weekly_ghost_cleanup_schedule,
]
