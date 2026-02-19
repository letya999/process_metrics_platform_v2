"""
Lead Time Metrics Dagster Asset

This asset calculates Lead Time metrics using Python/Polars logic
(replacing the old SQL Materialized View approach).
"""

from typing import Any

import polars as pl
from dagster import AssetExecutionContext, asset

from pipelines.calculations import lead_time as lead_time_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Lead Time facts using Python/Polars logic",
    compute_kind="python",
)
def calculate_lead_time(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Lead Time metrics (In Progress → Done) for all issues.

    This asset replaces the SQL Materialized View with Python/Polars logic,
    providing debuggable, testable metrics calculation.

    Outputs:
    - metrics.fact_lead_time (base facts: per-issue lead time)
    - metrics.fact_lead_time_slice (aggregated by issue type)
    - metrics.fact_lead_time_bins (histogram distribution)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load required tables into Polars DataFrames
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name, i.status_id,
               i.jira_created_at, i.jira_resolved_at
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    status_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, from_status_id, to_status_id, changed_at
        FROM clean_jira.issue_status_changelog
        ORDER BY changed_at
        """,
    )

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bc.position, bcs.status_id
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    context.log.info(
        f"Loaded {len(issues_df)} issues, {len(status_changelog_df)} status changes, "
        f"{len(boards_df)} boards"
    )

    # =====================================================
    # Calculate BASE lead time facts (per issue)
    # =====================================================
    context.log.info("Calculating lead time facts...")
    lead_time_df = lead_time_logic.calculate_lead_time_facts(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
    )

    if lead_time_df.is_empty():
        context.log.warning(
            "⚠️ No lead time data calculated. Check board column configuration "
            "(need 'In Progress' and 'Done' columns)."
        )
        return {
            "status": "warning",
            "message": "No lead time data - check board configuration",
            "fact_rows": 0,
        }

    context.log.info(f"Calculated lead time for {len(lead_time_df)} issues")

    # Write base facts to database
    context.log.info("Writing to metrics.fact_lead_time...")
    write_table(lead_time_df, engine, table="fact_lead_time", schema="metrics")

    # =====================================================
    # Calculate SLICED facts (Generic)
    # =====================================================
    context.log.info("Calculating lead time slices...")
    from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules

    rules_df = get_slice_rules(engine, target_metric_table="fact_lead_time")

    def lead_time_slice_identity(df_subset):
        # Return raw rows for the slice (NO AGGREGATION)
        # Match schema: project_id, issue_id, issue_key, issue_type, commitment_start_at, commitment_end_at, lead_time_days
        if df_subset.is_empty():
            return pl.DataFrame()

        return df_subset.select(
            [
                "project_id",
                "issue_id",
                "issue_key",
                "issue_type",
                "commitment_start_at",
                "commitment_end_at",
                "lead_time_days",
            ]
        )

    # lead_time_df already has issue_type column (from type_name)
    slice_df = apply_slicing(
        lead_time_df, rules_df, lead_time_slice_identity, base_columns=["project_id"]
    )

    if not slice_df.is_empty():
        context.log.info(
            f"Writing {len(slice_df)} rows to metrics.fact_lead_time_slices..."
        )
        write_table(slice_df, engine, table="fact_lead_time_slices", schema="metrics")

    # =====================================================
    # Calculate HISTOGRAM BINS (Base) - DEPRECATED / DROPPED
    # =====================================================
    # context.log.info("Calculating histogram bins... (Skipped - table dropped)")
    # bins_df = lead_time_logic.calculate_histogram_bins(lead_time_df)
    # write_table(bins_df, engine, table="fact_lead_time_bins", schema="metrics")

    # =====================================================
    # Return summary statistics
    # =====================================================
    avg_lead_time = (
        float(lead_time_df["lead_time_days"].mean())
        if not lead_time_df.is_empty()
        else 0.0
    )

    context.log.info(
        f"✅ Lead Time calculation complete: "
        f"{len(lead_time_df)} issues, avg {avg_lead_time:.2f} days"
    )

    return {
        "status": "success",
        "fact_rows": len(lead_time_df),
        "avg_lead_time_days": round(avg_lead_time, 2),
        "slice_rows": len(slice_df) if not slice_df.is_empty() else 0,
        "bins_rows": 0,  # DEPRECATED / DROPPED
    }
