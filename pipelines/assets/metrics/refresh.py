"""Metrics assets - refresh materialized views for BI layer.

This module implements the metrics layer (Gold) of the medallion architecture.
Materialized views in the metrics schema are refreshed after data sync.
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
    description="Refresh lead time metrics",
    compute_kind="sql",
)
def metrics_lead_time(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Get stats from the metrics.fact_lead_time table.

    This table contains lead time (creation to resolution) for all
    resolved issues, calculated by the calculate_lead_time asset.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Getting lead time stats from fact_lead_time...")

        try:
            # Get stats directly from the fact table
            result = conn.execute(
                text(
                    """
                SELECT
                    count(*) as total_issues,
                    round(avg(lead_time_days)::numeric, 2) as avg_lead_time_days,
                    round(min(lead_time_days)::numeric, 2) as min_lead_time_days,
                    round(max(lead_time_days)::numeric, 2) as max_lead_time_days
                FROM metrics.fact_lead_time
            """
                )
            )
            stats = result.mappings().first()

            return {
                "status": "success",
                "table": "fact_lead_time",
                "stats": dict(stats) if stats else {},
            }
        except Exception as e:
            context.log.error(f"Failed to get lead time stats: {e}")
            raise


@asset(
    group_name="metrics",
    deps=["calculate_velocity"],
    description="Refresh velocity metrics",
    compute_kind="sql",
)
def metrics_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Get stats from the metrics.fact_velocity table.

    This table contains velocity metrics (planned/completed issues and story points)
    per sprint, calculated by the calculate_velocity asset.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Getting velocity stats from fact_velocity...")

        try:
            # fact_velocity is populated by calculate_velocity asset
            result = conn.execute(
                text(
                    """
                SELECT
                    count(*) as total_sprints,
                    round(
                        avg(CASE WHEN planned_story_points > 0
                            THEN completed_story_points * 100.0 / planned_story_points
                            ELSE 0 END)::numeric, 2
                    ) as avg_completion_rate_pct,
                    round(avg(completed_issues)::numeric, 2) as avg_issues_per_sprint
                FROM metrics.fact_velocity
            """
                )
            )
            stats = result.mappings().first()

            return {
                "status": "success",
                "table": "fact_velocity",
                "stats": dict(stats) if stats else {},
            }
        except Exception as e:
            context.log.error(f"Failed to get velocity stats: {e}")
            raise


@asset(
    group_name="metrics",
    deps=["calculate_lead_time"],
    description="Refresh throughput metrics",
    compute_kind="sql",
)
def metrics_throughput(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Calculate throughput stats from metrics.fact_lead_time.

    Throughput is calculated as issues completed per day.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Calculating throughput stats from fact_lead_time...")

        try:
            # Calculate throughput stats from fact_lead_time
            # throughput = count of issues with commitment_end_at per day
            result = conn.execute(
                text(
                    """
                WITH daily_stats AS (
                    SELECT
                        DATE(commitment_end_at) as resolved_date,
                        count(*) as issues_completed
                    FROM metrics.fact_lead_time
                    WHERE commitment_end_at IS NOT NULL
                    GROUP BY DATE(commitment_end_at)
                )
                SELECT
                    count(DISTINCT resolved_date) as days_with_data,
                    sum(issues_completed) as total_completed,
                    round(avg(issues_completed)::numeric, 2) as avg_daily_throughput
                FROM daily_stats
            """
                )
            )
            stats = result.mappings().first()

            return {
                "status": "success",
                "source": "fact_lead_time",
                "type": "throughput_derived",
                "stats": dict(stats) if stats else {},
            }
        except Exception as e:
            context.log.error(f"Failed to calculate throughput stats: {e}")
            raise


@asset(
    group_name="metrics",
    deps=["metrics_lead_time", "metrics_velocity", "metrics_throughput"],
    description="Refresh all metrics stats",
    compute_kind="sql",
)
def metrics_all(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Get summarized stats for all metrics.

    This ensures all metrics stats are available.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("All metrics stats refreshed via individual assets")

        # Get overall stats
        result = conn.execute(
            text(
                """
            SELECT
                (SELECT count(*) FROM metrics.fact_lead_time) as lead_time_records,
                (SELECT count(*) FROM metrics.fact_velocity) as velocity_records,
                (SELECT count(DISTINCT DATE(commitment_end_at)) FROM metrics.fact_lead_time WHERE commitment_end_at IS NOT NULL) as throughput_days
        """
            )
        )
        stats = result.mappings().first()

        return {
            "status": "success",
            "stats": dict(stats) if stats else {},
        }


# Asset checks for metrics quality


@asset_check(asset=metrics_lead_time)
def check_lead_time_no_nulls(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure lead_time_days is populated for all resolved issues."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT count(*) FROM metrics.fact_lead_time
            WHERE lead_time_days IS NULL
        """
            )
        )
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
    """Ensure lead_time_days is positive."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT count(*) FROM metrics.fact_lead_time
            WHERE lead_time_days < 0
        """
            )
        )
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
    """Ensure completed_story_points does not exceed planned_story_points unreasonably."""
    engine = database.get_engine()

    with engine.connect() as conn:
        # Check if completed is more than 150% of planned (allows some scope creep)
        result = conn.execute(
            text(
                """
            SELECT count(*) FROM metrics.fact_velocity
            WHERE planned_story_points > 0
              AND completed_story_points > planned_story_points * 1.5
        """
            )
        )
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
    """Ensure no throughput records have future dates."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT count(*) FROM metrics.fact_lead_time
            WHERE commitment_end_at > CURRENT_DATE + INTERVAL '1 day'
        """
            )
        )
        future_count = result.scalar() or 0

    return AssetCheckResult(
        passed=future_count == 0,
        metadata={"future_date_count": future_count},
    )
