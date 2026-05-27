"""Dagster schedules and sensors for automated pipeline execution.

This module defines:
- cron schedules for regular jobs
- guarded sensors for non-overlapping light/heavy metrics refresh runs
"""

from datetime import datetime, timezone

from dagster import (
    AssetSelection,
    DagsterRunStatus,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    RunRequest,
    RunsFilter,
    ScheduleDefinition,
    SensorEvaluationContext,
    SkipReason,
    define_asset_job,
    sensor,
)

# Metrics split to reduce OOM risk and avoid queue congestion.
METRICS_HEAVY_SELECTION = AssetSelection.assets(
    "calculate_cumulative_flow_diagram",
    "calculate_backlog_growth",
    "calculate_aging_extended",
    "calculate_quality_metrics",
    "metrics_all",
)
METRICS_LIGHT_SELECTION = AssetSelection.groups("metrics") - METRICS_HEAVY_SELECTION


def _get_active_run_ids_by_job(
    context: SensorEvaluationContext, job_names: set[str]
) -> dict[str, list[str]]:
    active_statuses = [
        DagsterRunStatus.QUEUED,
        DagsterRunStatus.NOT_STARTED,
        DagsterRunStatus.STARTING,
        DagsterRunStatus.STARTED,
        DagsterRunStatus.CANCELING,
    ]
    active_runs = context.instance.get_run_records(
        filters=RunsFilter(statuses=active_statuses),
        limit=200,
    )
    by_job: dict[str, list[str]] = {}
    for record in active_runs:
        job_name = record.dagster_run.job_name
        if job_name in job_names:
            by_job.setdefault(job_name, []).append(record.dagster_run.run_id)
    return by_job


# Define jobs for scheduling

# Job: Full Jira sync (raw -> clean -> light metrics)
jira_sync_job = define_asset_job(
    name="jira_sync_job",
    selection=AssetSelection.groups("jira_raw", "jira_clean") | METRICS_LIGHT_SELECTION,
    description="Full Jira data sync: raw -> clean -> light metrics refresh",
    config={"execution": {"config": {"multiprocess": {"max_concurrent": 1}}}},
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
    description="Legacy full metrics refresh job (includes heavy assets)",
    config={"execution": {"config": {"multiprocess": {"max_concurrent": 1}}}},
)

# Job: Light metrics refresh (hourly)
metrics_light_refresh_job = define_asset_job(
    name="metrics_light_refresh_job",
    selection=METRICS_LIGHT_SELECTION,
    description="Refresh light metrics (hourly, lower OOM risk)",
    config={"execution": {"config": {"multiprocess": {"max_concurrent": 1}}}},
)

# Job: Heavy metrics refresh (nightly)
metrics_heavy_refresh_job = define_asset_job(
    name="metrics_heavy_refresh_job",
    selection=METRICS_HEAVY_SELECTION,
    description="Refresh heavy metrics (nightly, serialized)",
    config={"execution": {"config": {"multiprocess": {"max_concurrent": 1}}}},
)

# Job: staged heavy - CFD only
metrics_heavy_cfd_job = define_asset_job(
    name="metrics_heavy_cfd_job",
    selection=AssetSelection.assets("calculate_cumulative_flow_diagram"),
    description="Heavy window 1: CFD only",
    config={"execution": {"config": {"multiprocess": {"max_concurrent": 1}}}},
)

# Job: staged heavy - backlog growth + aging extended
metrics_heavy_backlog_aging_job = define_asset_job(
    name="metrics_heavy_backlog_aging_job",
    selection=AssetSelection.assets(
        "calculate_backlog_growth",
        "calculate_aging_extended",
    ),
    description="Heavy window 2: backlog growth + aging extended",
    config={"execution": {"config": {"multiprocess": {"max_concurrent": 1}}}},
)

# Define schedules

# Schedule: Daily full sync at 6 AM UTC
daily_jira_sync_schedule = ScheduleDefinition(
    job=jira_sync_job,
    cron_schedule="0 6 * * *",  # 6:00 AM UTC daily
    default_status=DefaultScheduleStatus.STOPPED,  # Start stopped, enable manually
    execution_timezone="UTC",
)

# Keep legacy schedule object for compatibility, but prefer guarded sensor below.
hourly_metrics_refresh_schedule = ScheduleDefinition(
    job=metrics_light_refresh_job,
    cron_schedule="0 * * * *",
    default_status=DefaultScheduleStatus.STOPPED,
    execution_timezone="UTC",
)


@sensor(
    name="guarded_hourly_metrics_light_refresh_sensor",
    job=metrics_light_refresh_job,
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.STOPPED,
)
def guarded_hourly_metrics_light_refresh_sensor(
    context: SensorEvaluationContext,
) -> RunRequest | SkipReason:
    """Run light metrics hourly only when no blocking jobs are active."""
    now_utc = datetime.now(timezone.utc)
    hour_bucket = now_utc.strftime("%Y-%m-%dT%H")

    if now_utc.minute != 5:
        return SkipReason("Waiting for :05 minute boundary (UTC)")

    if context.cursor == hour_bucket:
        return SkipReason(
            f"Light metrics refresh already requested for {hour_bucket}:05 UTC"
        )

    blocking_jobs = {
        "jira_sync_job",
        "jira_clean_job",
        "metrics_light_refresh_job",
        "metrics_heavy_refresh_job",
    }
    blocking_runs = _get_active_run_ids_by_job(context, blocking_jobs)
    if blocking_runs:
        return SkipReason(
            "Skipping light metrics refresh due to active blocking runs "
            f"(runs={blocking_runs})"
        )

    context.update_cursor(hour_bucket)
    return RunRequest(run_key=f"metrics-light-refresh-{hour_bucket}")


@sensor(
    name="guarded_nightly_metrics_heavy_refresh_sensor",
    job=metrics_heavy_refresh_job,
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.STOPPED,
)
def guarded_nightly_metrics_heavy_refresh_sensor(
    context: SensorEvaluationContext,
) -> RunRequest | SkipReason:
    """Run heavy metrics nightly only when no blocking jobs are active."""
    now_utc = datetime.now(timezone.utc)
    day_bucket = now_utc.strftime("%Y-%m-%d")

    if not (now_utc.hour == 2 and now_utc.minute == 35):
        return SkipReason("Waiting for 02:35 UTC nightly window")

    if context.cursor == day_bucket:
        return SkipReason(f"Heavy metrics refresh already requested for {day_bucket}")

    blocking_jobs = {
        "jira_sync_job",
        "jira_clean_job",
        "metrics_light_refresh_job",
        "metrics_heavy_refresh_job",
    }
    blocking_runs = _get_active_run_ids_by_job(context, blocking_jobs)
    if blocking_runs:
        return SkipReason(
            "Skipping heavy metrics refresh due to active blocking runs "
            f"(runs={blocking_runs})"
        )

    context.update_cursor(day_bucket)
    return RunRequest(run_key=f"metrics-heavy-refresh-{day_bucket}")


@sensor(
    name="guarded_nightly_metrics_heavy_cfd_sensor",
    job=metrics_heavy_cfd_job,
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.STOPPED,
)
def guarded_nightly_metrics_heavy_cfd_sensor(
    context: SensorEvaluationContext,
) -> RunRequest | SkipReason:
    """Run CFD in a dedicated heavy window."""
    now_utc = datetime.now(timezone.utc)
    day_bucket = now_utc.strftime("%Y-%m-%d")
    if not (now_utc.hour == 2 and now_utc.minute == 35):
        return SkipReason("Waiting for 02:35 UTC heavy CFD window")
    if context.cursor == day_bucket:
        return SkipReason(f"Heavy CFD already requested for {day_bucket}")
    blocking_jobs = {
        "jira_sync_job",
        "jira_clean_job",
        "metrics_light_refresh_job",
        "metrics_heavy_refresh_job",
        "metrics_heavy_backlog_aging_job",
        "metrics_heavy_cfd_job",
    }
    blocking_runs = _get_active_run_ids_by_job(context, blocking_jobs)
    if blocking_runs:
        return SkipReason(
            f"Skipping heavy CFD due to active blocking runs (runs={blocking_runs})"
        )
    context.update_cursor(day_bucket)
    return RunRequest(run_key=f"metrics-heavy-cfd-{day_bucket}")


@sensor(
    name="guarded_nightly_metrics_heavy_backlog_aging_sensor",
    job=metrics_heavy_backlog_aging_job,
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.STOPPED,
)
def guarded_nightly_metrics_heavy_backlog_aging_sensor(
    context: SensorEvaluationContext,
) -> RunRequest | SkipReason:
    """Run backlog/aging in dedicated follow-up window after CFD."""
    now_utc = datetime.now(timezone.utc)
    day_bucket = now_utc.strftime("%Y-%m-%d")
    if not (now_utc.hour == 3 and now_utc.minute == 20):
        return SkipReason("Waiting for 03:20 UTC heavy backlog/aging window")
    if context.cursor == day_bucket:
        return SkipReason(f"Heavy backlog/aging already requested for {day_bucket}")
    blocking_jobs = {
        "jira_sync_job",
        "jira_clean_job",
        "metrics_light_refresh_job",
        "metrics_heavy_refresh_job",
        "metrics_heavy_backlog_aging_job",
        "metrics_heavy_cfd_job",
    }
    blocking_runs = _get_active_run_ids_by_job(context, blocking_jobs)
    if blocking_runs:
        return SkipReason(
            "Skipping heavy backlog/aging due to active blocking runs "
            f"(runs={blocking_runs})"
        )
    context.update_cursor(day_bucket)
    return RunRequest(run_key=f"metrics-heavy-backlog-aging-{day_bucket}")


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
    metrics_light_refresh_job,
    metrics_heavy_refresh_job,
    metrics_heavy_cfd_job,
    metrics_heavy_backlog_aging_job,
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
    # Guarded sensor is the recommended path; keep schedule for backward compatibility.
    hourly_metrics_refresh_schedule,
    weekly_ghost_cleanup_schedule,
]

sensors = [
    guarded_hourly_metrics_light_refresh_sensor,
    guarded_nightly_metrics_heavy_refresh_sensor,
    guarded_nightly_metrics_heavy_cfd_sensor,
    guarded_nightly_metrics_heavy_backlog_aging_sensor,
]
