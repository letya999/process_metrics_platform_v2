"""
Backlog Health Metrics Dagster Asset

This asset calculates metrics to assess the health of the product backlog.
"""

from typing import Any

from dagster import AssetExecutionContext, asset

from pipelines.calculations import backlog_health as backlog_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_statuses",
        "clean_jira_issue_types",
        "clean_jira_field_values",
        "clean_jira_field_keys",
    ],
    description="Calculate Backlog Health metrics (size, age, staleness)",
    compute_kind="python",
)
def calculate_backlog_health(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Backlog Health metrics.

    This asset calculates:
    - Overall backlog health (size, age, staleness)
    - Backlog distribution by type and priority
    - Age distribution (how long issues have been open)

    Outputs:
    - metrics.fact_backlog_health (main health metrics)
    - metrics.fact_backlog_distribution (breakdown by type/priority)
    - metrics.fact_backlog_age_distribution (age buckets)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load required tables into Polars DataFrames
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.type_id, i.status_id,
               i.jira_created_at, i.jira_updated_at
        FROM clean_jira.issues i
        """,
    )

    issue_statuses_df = read_table(
        engine,
        """
        SELECT id, project_id, name, category
        FROM clean_jira.issue_statuses
        """,
    )

    issue_types_df = read_table(
        engine,
        """
        SELECT id, project_id, name, hierarchy_level
        FROM clean_jira.issue_types
        """,
    )

    field_values_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id, json_value::text AS json_value
        FROM clean_jira.field_values
        """,
    )

    field_keys_df = read_table(
        engine,
        """
        SELECT id, external_key, name
        FROM clean_jira.field_keys
        """,
    )

    context.log.info(
        f"Loaded {len(issues_df)} issues, {len(issue_statuses_df)} statuses"
    )

    # =====================================================
    # Calculate main backlog health metrics
    # =====================================================
    context.log.info("Calculating backlog health metrics...")
    health_df = backlog_logic.calculate_backlog_health(
        issues_df=issues_df,
        issue_statuses_df=issue_statuses_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        stale_threshold_days=30,
    )

    if health_df.is_empty():
        context.log.warning(
            "⚠️ No backlog health data calculated. All issues may be completed."
        )
        return {
            "status": "warning",
            "message": "No backlog health data - no open issues found",
            "fact_rows": 0,
        }

    context.log.info(f"Calculated health metrics for {len(health_df)} projects")

    # Write health facts to database
    context.log.info("Writing to metrics.fact_backlog_health...")
    write_table(health_df, engine, table="fact_backlog_health", schema="metrics")

    # =====================================================
    # Calculate backlog distribution
    # =====================================================
    context.log.info("Calculating backlog distribution by type/priority...")
    distribution_df = backlog_logic.calculate_backlog_distribution(
        issues_df=issues_df,
        issue_statuses_df=issue_statuses_df,
        issue_types_df=issue_types_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
    )

    context.log.info(f"Calculated {len(distribution_df)} distribution rows")

    # Write distribution to database
    context.log.info("Writing to metrics.fact_backlog_distribution...")
    write_table(
        distribution_df, engine, table="fact_backlog_distribution", schema="metrics"
    )

    # =====================================================
    # Calculate age distribution
    # =====================================================
    context.log.info("Calculating age distribution...")
    age_distribution_df = backlog_logic.calculate_age_distribution(
        issues_df=issues_df,
        issue_statuses_df=issue_statuses_df,
    )

    context.log.info(f"Calculated {len(age_distribution_df)} age bucket rows")

    # Write age distribution to database
    context.log.info("Writing to metrics.fact_backlog_age_distribution...")
    write_table(
        age_distribution_df,
        engine,
        table="fact_backlog_age_distribution",
        schema="metrics",
    )

    # =====================================================
    # Return summary statistics
    # =====================================================
    total_backlog = (
        int(health_df["total_backlog_size"].sum()) if not health_df.is_empty() else 0
    )
    avg_stale_pct = (
        float(health_df["stale_percentage"].mean()) if not health_df.is_empty() else 0.0
    )

    context.log.info(
        f"✅ Backlog health calculation complete: "
        f"{total_backlog} total backlog items, {avg_stale_pct:.1f}% stale (avg)"
    )

    return {
        "status": "success",
        "total_backlog_size": total_backlog,
        "avg_stale_percentage": round(avg_stale_pct, 2),
        "health_rows": len(health_df),
        "distribution_rows": len(distribution_df),
        "age_distribution_rows": len(age_distribution_df),
    }
