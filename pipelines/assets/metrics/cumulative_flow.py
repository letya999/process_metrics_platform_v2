"""
Cumulative Flow Diagram (CFD) Dagster Asset

This asset calculates daily issue counts per status for CFD visualization.
"""

from typing import Any

import polars as pl
from dagster import AssetExecutionContext, asset

from pipelines.calculations import cumulative_flow as cfd_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_statuses",
        "clean_jira_issue_types",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Cumulative Flow Diagram data (daily issue counts per status)",
    compute_kind="python",
)
def calculate_cumulative_flow_diagram(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Cumulative Flow Diagram (CFD) data.

    This asset calculates:
    - Daily snapshot of how many issues are in each status
    - Flow trends and aggregates

    Outputs:
    - metrics.fact_cfd (daily status counts)
    - metrics.fact_cfd_aggregates (summary statistics and trends)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load required tables into Polars DataFrames
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.type_id, i.status_id, i.jira_created_at, i.jira_updated_at
        FROM clean_jira.issues i
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

    issue_statuses_df = read_table(
        engine,
        """
        SELECT id, project_id, external_id, name, category
        FROM clean_jira.issue_statuses
        """,
    )

    issue_types_df = read_table(
        engine,
        """
        SELECT id, name
        FROM clean_jira.issue_types
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
        f"Loaded {len(issues_df)} issues, {len(issue_statuses_df)} statuses"
    )

    # =====================================================
    # Calculate CFD data (90 days back)
    # =====================================================
    context.log.info("Calculating CFD data for last 90 days...")
    cfd_df = cfd_logic.calculate_cumulative_flow_diagram(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        issue_statuses_df=issue_statuses_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        days_back=90,
    )

    if cfd_df.is_empty():
        context.log.warning(
            "⚠️ No CFD data calculated. Check that issues have status history."
        )
        return {
            "status": "warning",
            "message": "No CFD data - no issues found",
            "fact_rows": 0,
        }

    context.log.info(f"Calculated CFD for {len(cfd_df)} date-status combinations")

    # Write CFD facts to database
    context.log.info("Writing to metrics.fact_cfd...")
    write_table(cfd_df, engine, table="fact_cfd", schema="metrics")

    # =====================================================
    # Calculate CFD Slices
    # =====================================================
    context.log.info("Calculating CFD slices...")
    from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules

    rules_df = get_slice_rules(engine, target_metric_table="fact_cfd")

    def cfd_slice_calc(df_subset):
        # We need issues from df_subset and potentially their changelog
        subset_ids = df_subset.select("id")
        subset_changelog = status_changelog_df.join(
            subset_ids, left_on="issue_id", right_on="id"
        )

        return cfd_logic.calculate_cumulative_flow_diagram(
            issues_df=df_subset,
            status_changelog_df=subset_changelog,
            issue_statuses_df=issue_statuses_df,
            boards_df=boards_df,
            board_columns_df=board_columns_df,
            days_back=90,
        )

    # Join type name for slicing
    issues_with_type = issues_df.join(
        issue_types_df.select(["id", "name"]),
        left_on="type_id",
        right_on="id",
        how="left",
    ).rename({"name": "issue_type"})

    slice_df = apply_slicing(
        issues_with_type, rules_df, cfd_slice_calc, base_columns=["project_id", "date"]
    )

    if not slice_df.is_empty():
        # Remove empty date-status pairs for slices to save space and avoid showing unused types
        # CFD is a density plot, so 0-count statuses for a slice (e.g. Bugs) are just noise.
        slice_df = slice_df.filter(pl.col("issue_count") > 0)

    if not slice_df.is_empty():
        context.log.info(f"Writing {len(slice_df)} rows to metrics.fact_cfd_slices...")
        write_table(slice_df, engine, table="fact_cfd_slices", schema="metrics")

    # =====================================================
    # Return summary statistics
    # =====================================================
    unique_dates = len(cfd_df["date"].unique())
    unique_statuses = len(cfd_df["status_name"].unique())

    context.log.info(
        f"✅ CFD calculation complete: "
        f"{unique_dates} days × {unique_statuses} statuses"
    )

    return {
        "status": "success",
        "total_days": unique_dates,
        "total_statuses": unique_statuses,
        "fact_rows": len(cfd_df),
    }
