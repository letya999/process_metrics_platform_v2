"""
Backlog Growth Metrics Dagster Asset

This asset calculates metrics to assess the growth and health of the product backlog.
"""

from typing import Any

import polars as pl
from dagster import AssetExecutionContext, asset

from pipelines.calculations import backlog_growth as backlog_logic
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
        "clean_jira_issue_status_changelog",
        "clean_jira_board_column_statuses",
    ],
    description="Calculate Backlog Growth metrics (size, age, staleness, daily growth)",
    compute_kind="python",
)
def calculate_backlog_growth(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Backlog Growth metrics.

    This asset calculates:
    - Overall backlog health (size, age, staleness)
    - Backlog distribution by type and priority
    - Age distribution (how long issues have been open)
    - Daily created/closed/entered/exited counts

    Outputs:
    - metrics.fact_backlog_growth (main health metrics)
    - metrics.fact_backlog_growth_slices (breakdown by type/priority)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load required tables into Polars DataFrames
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.type_id, i.status_id,
               i.jira_created_at, i.jira_updated_at, i.jira_resolved_at
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

    changelog_df = read_table(
        engine,
        """
        SELECT issue_id, from_status_id, to_status_id, changed_at
        FROM clean_jira.issue_status_changelog
        """,
    )

    board_column_statuses_df = read_table(
        engine,
        """
        SELECT b.project_id, bc.position, bcs.status_id
        FROM clean_jira.board_column_statuses bcs
        JOIN clean_jira.board_columns bc ON bcs.board_column_id = bc.id
        JOIN clean_jira.boards b ON bc.board_id = b.id
        """,
    )

    context.log.info(
        f"Loaded {len(issues_df)} issues, {len(issue_statuses_df)} statuses, {len(changelog_df)} changelog rows"
    )

    # =====================================================
    # Calculate main backlog growth metrics
    # =====================================================
    context.log.info("Calculating backlog growth metrics...")
    health_df = backlog_logic.calculate_backlog_growth(
        issues_df=issues_df,
        issue_statuses_df=issue_statuses_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        changelog_df=changelog_df,
        board_column_statuses_df=board_column_statuses_df,
        days_back=90,
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
    context.log.info("Writing to metrics.fact_backlog_growth...")
    write_table(health_df, engine, table="fact_backlog_growth", schema="metrics")

    # =====================================================
    # Calculate Backlog Growth Slices (Trends)
    # =====================================================
    context.log.info("Calculating backlog growth slices...")

    from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules

    # Get generic rules for backlog growth
    rules_df = get_slice_rules(engine, target_metric_table="fact_backlog_growth")

    # Define calculation for slices
    def calc_health_wrapper(df_subset):
        # We need to filter field_values and changelog to only those in the subset
        subset_ids = df_subset.select("id")
        subset_field_values = field_values_df.join(
            subset_ids, left_on="issue_id", right_on="id"
        )
        subset_changelog = changelog_df.join(
            subset_ids, left_on="issue_id", right_on="id"
        )

        return backlog_logic.calculate_backlog_growth(
            issues_df=df_subset,
            issue_statuses_df=issue_statuses_df,
            field_values_df=subset_field_values,
            field_keys_df=field_keys_df,
            changelog_df=subset_changelog,
            board_column_statuses_df=board_column_statuses_df,
            days_back=90,
            stale_threshold_days=30,
        )

    # Let's join type name to issues_df for slicing
    issues_with_type = issues_df.join(
        issue_types_df.select(["id", "name"]),
        left_on="type_id",
        right_on="id",
        how="left",
    ).rename({"name": "issue_type"})

    slice_df = apply_slicing(
        issues_with_type,
        rules_df,
        calc_health_wrapper,
        base_columns=["project_id", "fact_date"],
    )

    if not slice_df.is_empty():
        # Filter out slices with no issues in backlog to prevent zero-bloating for unused types
        slice_df = slice_df.filter(pl.col("total_backlog_size") > 0)

    if not slice_df.is_empty():
        context.log.info(
            f"Writing {len(slice_df)} rows to metrics.fact_backlog_growth_slices..."
        )
        write_table(
            slice_df, engine, table="fact_backlog_growth_slices", schema="metrics"
        )
    else:
        context.log.info("No slice data generated for backlog growth.")

    # =====================================================
    # Return summary statistics
    # =====================================================
    # For summary, use statistics from the latest date
    latest_date = health_df["fact_date"].max()
    latest_health = health_df.filter(pl.col("fact_date") == latest_date)

    total_backlog = (
        int(latest_health["total_backlog_size"].sum())
        if not latest_health.is_empty()
        else 0
    )
    avg_stale_pct = (
        float(latest_health["stale_percentage"].mean())
        if not latest_health.is_empty()
        else 0.0
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
        "slice_rows": len(slice_df),
    }
