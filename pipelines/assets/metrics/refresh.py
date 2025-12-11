"""Metrics assets - refresh materialized views for BI layer.

This module implements the metrics layer (Gold) of the medallion architecture.
Materialized views in the metrics schema are refreshed after data sync.
"""

from typing import Any

from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource


@asset(
    group_name="metrics",
    deps=["clean_jira_issues", "clean_jira_sprints"],
    description="Refresh lead time materialized view",
    compute_kind="sql",
)
def metrics_lead_time(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Refresh the metrics.mv_lead_time materialized view.

    This view calculates lead time (creation to resolution) for all
    resolved issues in the clean_jira schema.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Refreshing mv_lead_time materialized view...")

        try:
            conn.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time")
            )
            conn.commit()
            context.log.info("mv_lead_time refreshed successfully")

            # Get stats
            result = conn.execute(
                text("""
                SELECT
                    count(*) as total_issues,
                    round(avg(lead_time_days)::numeric, 2) as avg_lead_time_days,
                    round(min(lead_time_days)::numeric, 2) as min_lead_time_days,
                    round(max(lead_time_days)::numeric, 2) as max_lead_time_days
                FROM metrics.mv_lead_time
            """)
            )
            stats = result.mappings().first()

            return {
                "status": "success",
                "view": "mv_lead_time",
                "stats": dict(stats) if stats else {},
            }
        except Exception as e:
            context.log.error(f"Failed to refresh mv_lead_time: {e}")
            raise


@asset(
    group_name="metrics",
    deps=["clean_jira_issues", "clean_jira_sprints"],
    description="Refresh velocity materialized view",
    compute_kind="sql",
)
def metrics_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Refresh the metrics.mv_velocity materialized view.

    This view calculates velocity metrics (issues completed, completion rate)
    per sprint from the clean_jira schema.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Refreshing mv_velocity materialized view...")

        try:
            conn.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity")
            )
            conn.commit()
            context.log.info("mv_velocity refreshed successfully")

            # Get stats
            result = conn.execute(
                text("""
                SELECT
                    count(*) as total_sprints,
                    round(avg(completion_rate_pct)::numeric, 2) as avg_completion_rate,
                    round(avg(total_issues)::numeric, 2) as avg_issues_per_sprint
                FROM metrics.mv_velocity
            """)
            )
            stats = result.mappings().first()

            return {
                "status": "success",
                "view": "mv_velocity",
                "stats": dict(stats) if stats else {},
            }
        except Exception as e:
            context.log.error(f"Failed to refresh mv_velocity: {e}")
            raise


@asset(
    group_name="metrics",
    deps=["clean_jira_issues"],
    description="Refresh throughput materialized view",
    compute_kind="sql",
)
def metrics_throughput(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Refresh the metrics.mv_throughput materialized view.

    This view calculates daily throughput (issues completed per day)
    from the clean_jira schema.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Refreshing mv_throughput materialized view...")

        try:
            conn.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_throughput")
            )
            conn.commit()
            context.log.info("mv_throughput refreshed successfully")

            # Get stats
            result = conn.execute(
                text("""
                SELECT
                    count(DISTINCT resolved_date) as days_with_data,
                    sum(issues_completed) as total_completed,
                    round(avg(issues_completed)::numeric, 2) as avg_daily_throughput
                FROM metrics.mv_throughput
            """)
            )
            stats = result.mappings().first()

            return {
                "status": "success",
                "view": "mv_throughput",
                "stats": dict(stats) if stats else {},
            }
        except Exception as e:
            context.log.error(f"Failed to refresh mv_throughput: {e}")
            raise


@asset(
    group_name="metrics",
    deps=["metrics_lead_time", "metrics_velocity", "metrics_throughput"],
    description="Refresh all metrics views at once",
    compute_kind="sql",
)
def metrics_all(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Refresh all metrics materialized views using the refresh function.

    This is a convenience asset that ensures all metrics are refreshed
    together and can be used as a single dependency.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("All metrics views refreshed via individual assets")

        # Get overall stats
        result = conn.execute(
            text("""
            SELECT
                (SELECT count(*) FROM metrics.mv_lead_time) as lead_time_records,
                (SELECT count(*) FROM metrics.mv_velocity) as velocity_records,
                (SELECT count(*) FROM metrics.mv_throughput) as throughput_records
        """)
        )
        stats = result.mappings().first()

        return {
            "status": "success",
            "stats": dict(stats) if stats else {},
        }


# Asset checks for metrics quality


@asset_check(asset=metrics_lead_time)
def check_lead_time_no_nulls(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure lead_time_days is populated for all resolved issues."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM metrics.mv_lead_time
            WHERE lead_time_days IS NULL
        """)
        )
        null_count = result.scalar() or 0

    return AssetCheckResult(
        passed=null_count == 0,
        metadata={"null_lead_time_count": null_count},
    )


@asset_check(asset=metrics_lead_time)
def check_lead_time_positive(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure lead_time_days is positive (resolved after created)."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM metrics.mv_lead_time
            WHERE lead_time_days < 0
        """)
        )
        negative_count = result.scalar() or 0

    return AssetCheckResult(
        passed=negative_count == 0,
        metadata={"negative_lead_time_count": negative_count},
    )


@asset_check(asset=metrics_velocity)
def check_velocity_completion_rate_valid(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure completion_rate_pct is between 0 and 100."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM metrics.mv_velocity
            WHERE completion_rate_pct < 0 OR completion_rate_pct > 100
        """)
        )
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_completion_rate_count": invalid_count},
    )


@asset_check(asset=metrics_throughput)
def check_throughput_no_future_dates(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure no throughput records have future resolved_date."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM metrics.mv_throughput
            WHERE resolved_date > CURRENT_DATE
        """)
        )
        future_count = result.scalar() or 0

    return AssetCheckResult(
        passed=future_count == 0,
        metadata={"future_date_count": future_count},
    )
