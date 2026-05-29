"""Metrics assets - summary stats from the generic fact_values store.

Downstream of calculation assets; queries metrics.v_facts for aggregated stats.
"""

from typing import Any

from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetExecutionContext,
    asset,
    asset_check,
)
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource


@asset(
    group_name="metrics",
    deps=["calculate_lead_time"],
    description="Summarize lead time stats from fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="sql",
)
def metrics_lead_time(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                count(*) as total_issues,
                round(avg(value)::numeric, 2) as avg_lead_time_days,
                round(min(value)::numeric, 2) as min_lead_time_days,
                round(max(value)::numeric, 2) as max_lead_time_days
            FROM metrics.v_facts
            WHERE calc_code = 'lead_time_days'
              AND slice_rule_id IS NULL
        """))
        stats = result.mappings().first()

    return {
        "status": "success",
        "table": "fact_values",
        "calc_code": "lead_time_days",
        "stats": dict(stats) if stats else {},
    }


@asset(
    group_name="metrics",
    deps=["calculate_velocity"],
    description="Summarize velocity stats from fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="sql",
)
def metrics_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            WITH sprints AS (
                SELECT
                    project_key,
                    entity_id AS sprint_id,
                    time_id,
                    max(CASE WHEN calc_code = 'velocity_planned_sp' THEN value ELSE 0 END) AS planned_sp,
                    max(CASE WHEN calc_code = 'velocity_completed_sp' THEN value ELSE 0 END) AS completed_sp,
                    max(CASE WHEN calc_code = 'velocity_planned_count' THEN value ELSE 0 END) AS planned_count,
                    max(CASE WHEN calc_code = 'velocity_completed_count' THEN value ELSE 0 END) AS completed_count
                FROM metrics.v_facts
                WHERE calc_code IN (
                    'velocity_planned_sp', 'velocity_completed_sp',
                    'velocity_planned_count', 'velocity_completed_count'
                ) AND slice_rule_id IS NULL
                GROUP BY project_key, entity_id, time_id
            )
            SELECT
                count(*) as total_sprints,
                round(avg(CASE WHEN planned_sp > 0 THEN completed_sp * 100.0 / planned_sp ELSE 0 END)::numeric, 2) as avg_completion_rate_pct,
                round(avg(completed_count)::numeric, 2) as avg_issues_per_sprint
            FROM sprints
        """))
        stats = result.mappings().first()

    return {
        "status": "success",
        "table": "fact_values",
        "calc_code": "velocity_*",
        "stats": dict(stats) if stats else {},
    }


@asset(
    group_name="metrics",
    deps=["calculate_throughput"],
    description="Summarize throughput stats from fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="sql",
)
def metrics_throughput(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                count(*) as total_weeks,
                sum(value) as total_completed,
                round(avg(value)::numeric, 2) as avg_weekly_throughput
            FROM metrics.v_facts
            WHERE calc_code = 'throughput_count'
              AND slice_rule_id IS NULL
        """))
        stats = result.mappings().first()

    return {
        "status": "success",
        "source": "fact_values",
        "calc_code": "throughput_count",
        "stats": dict(stats) if stats else {},
    }


@asset(
    group_name="metrics",
    deps=[
        "metrics_lead_time",
        "metrics_velocity",
        "metrics_throughput",
        "calculate_aging",
        "calculate_flow_efficiency",
        "calculate_sprint_health",
        "calculate_flow_dynamics",
        "calculate_input_flow",
        "calculate_quality_metrics",
        "calculate_delivery_metrics",
        "calculate_cycle_time_extended",
        "calculate_waste_metrics",
        "calculate_estimation_metrics",
        "calculate_aging_extended",
    ],
    description="Aggregate stats across all metrics",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="sql",
)
def metrics_all(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                count(*) FILTER (WHERE calc_code = 'lead_time_days' AND slice_rule_id IS NULL) as lead_time_records,
                count(DISTINCT entity_id) FILTER (
                    WHERE calc_code = 'velocity_completed_sp' AND slice_rule_id IS NULL
                ) as velocity_sprints,
                count(*) FILTER (WHERE calc_code = 'throughput_count' AND slice_rule_id IS NULL) as throughput_weeks,
                count(*) FILTER (WHERE calc_code = 'cfd_count') as cfd_records
            FROM metrics.v_facts
        """))
        stats = result.mappings().first()

    return {
        "status": "success",
        "stats": dict(stats) if stats else {},
    }


@asset_check(asset=metrics_lead_time)
def check_lead_time_no_nulls(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM metrics.v_facts
            WHERE calc_code = 'lead_time_days' AND value IS NULL
        """))
        null_count = result.scalar() or 0

    return AssetCheckResult(
        passed=null_count == 0,
        metadata={"null_lead_time_count": null_count},
    )


@asset_check(asset=metrics_lead_time)
def check_lead_time_positive(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM metrics.v_facts
            WHERE calc_code = 'lead_time_days' AND value < 0
        """))
        negative_count = result.scalar() or 0

    return AssetCheckResult(
        passed=negative_count == 0,
        metadata={"negative_lead_time_count": negative_count},
    )


@asset_check(asset=metrics_velocity)
def check_velocity_completion_rate_valid(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            WITH sprints AS (
                SELECT
                    entity_id,
                    max(CASE WHEN calc_code = 'velocity_planned_sp' THEN value ELSE 0 END) AS planned_sp,
                    max(CASE WHEN calc_code = 'velocity_completed_sp' THEN value ELSE 0 END) AS completed_sp
                FROM metrics.v_facts
                WHERE calc_code IN ('velocity_planned_sp', 'velocity_completed_sp')
                  AND slice_rule_id IS NULL
                GROUP BY entity_id
            )
            SELECT count(*) FROM sprints
            WHERE planned_sp > 10 AND completed_sp > planned_sp * 5.0
        """))
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"suspicious_completion_rate_count": invalid_count},
    )


@asset_check(asset=metrics_throughput)
def check_throughput_no_future_dates(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM metrics.v_facts
            WHERE calc_code = 'throughput_count'
              AND full_date > CURRENT_DATE + INTERVAL '1 day'
        """))
        future_count = result.scalar() or 0

    return AssetCheckResult(
        passed=future_count == 0,
        metadata={"future_date_count": future_count},
    )
