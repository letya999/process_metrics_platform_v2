# Plan: Register Individual Recalc Jobs for New Metrics

## Context

The 9 new metric assets added in the previous session are already picked up by
`metrics_refresh_job` and `jira_sync_job` (both select by group `"metrics"`).
However, individual recalc jobs do not exist for these assets, unlike the old
metrics (lead_time, velocity, throughput, cfd, backlog_growth, time_to_market).

Additionally, the 9 new `*_data_quality_check` asset_checks are exported from
`pipelines/assets/metrics/__init__.py` but are NOT registered in
`pipelines/definitions.py`'s `asset_checks` list, so Dagster does not see them.

## New asset names (confirmed)

- `calculate_sprint_health`
- `calculate_flow_dynamics`
- `calculate_quality_metrics`
- `calculate_delivery_metrics`
- `calculate_cycle_time_extended`
- `calculate_waste_metrics`
- `calculate_estimation_metrics`
- `calculate_input_flow`
- `calculate_aging_extended`

## New asset_check names (confirmed, exported from __init__.py)

- `sprint_health_data_quality_check`
- `flow_dynamics_data_quality_check`
- `quality_data_quality_check`
- `delivery_data_quality_check`
- `cycle_time_ext_data_quality_check`
- `waste_data_quality_check`
- `estimation_data_quality_check`
- `input_flow_data_quality_check`
- `aging_extended_data_quality_check`

---

## File 1: `pipelines/jobs/schedules.py`

### What to add

After the existing `time_to_market_recalc_job` definition, add 9 new jobs:

```python
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
```

### Update the `jobs` list

Append all 9 new job variables to the existing `jobs` list:

```python
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
]
```

---

## File 2: `pipelines/definitions.py`

### Update imports

In the existing import block from `pipelines.assets.metrics`, add the 9 new
data quality check names:

```python
from pipelines.assets.metrics import (
    advanced_metrics_data_quality_check,
    backlog_growth_data_quality_check,
    cfd_data_quality_check,
    check_lead_time_no_nulls,
    check_lead_time_positive,
    check_throughput_no_future_dates,
    check_velocity_completion_rate_valid,
    lead_time_data_quality_check,
    throughput_data_quality_check,
    ttm_data_quality_check,
    velocity_data_quality_check,
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
)
```

### Update `asset_checks` list

Append the 9 new checks to the existing list:

```python
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
    advanced_metrics_data_quality_check,
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
]
```

---

## Validation

After applying changes, run:

```bash
.venv/Scripts/python -m pytest tests/unit/ -q
```

All 331 tests must pass. No new tests needed — the jobs/checks registration
does not add new logic, only wires existing assets into the Dagster graph.

Also verify Dagster can load definitions without errors:

```bash
.venv/Scripts/python -c "from pipelines.definitions import defs; print('OK', len(list(defs.get_all_job_defs())), 'jobs')"
```
