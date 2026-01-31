"""
Lead Time Metrics Dagster Asset

This asset calculates Lead Time metrics using Python/Polars logic
(replacing the old SQL Materialized View approach).
"""

from typing import Any

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
    - metrics.fact_lead_time_bins_slice (histogram sliced by type)
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
    # Calculate SLICED facts (by issue type)
    # =====================================================
    context.log.info("Calculating lead time slices by issue type...")
    lead_time_slice_df = lead_time_logic.calculate_lead_time_slice(lead_time_df)

    context.log.info(f"Calculated {len(lead_time_slice_df)} lead time slice rows")

    # Write slices to database
    context.log.info("Writing to metrics.fact_lead_time_slice...")
    write_table(
        lead_time_slice_df, engine, table="fact_lead_time_slice", schema="metrics"
    )

    # =====================================================
    # Calculate HISTOGRAM BINS
    # =====================================================
    context.log.info("Calculating histogram bins...")
    bins_df = lead_time_logic.calculate_histogram_bins(lead_time_df)

    context.log.info(f"Calculated {len(bins_df)} histogram bins")

    # Write bins to database
    context.log.info("Writing to metrics.fact_lead_time_bins...")
    write_table(bins_df, engine, table="fact_lead_time_bins", schema="metrics")

    # =====================================================
    # Calculate HISTOGRAM BINS SLICED (by issue type)
    # =====================================================
    context.log.info("Calculating histogram bins sliced by issue type...")
    bins_slice_df = lead_time_logic.calculate_histogram_bins_slice(lead_time_df)

    context.log.info(f"Calculated {len(bins_slice_df)} histogram bins slice rows")

    # Write bins slices to database
    context.log.info("Writing to metrics.fact_lead_time_bins_slice...")
    write_table(
        bins_slice_df, engine, table="fact_lead_time_bins_slice", schema="metrics"
    )

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
        "slice_rows": len(lead_time_slice_df),
        "bins_rows": len(bins_df),
        "bins_slice_rows": len(bins_slice_df),
    }
