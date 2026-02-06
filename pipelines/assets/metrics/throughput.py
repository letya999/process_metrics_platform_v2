"""
Throughput Metrics Dagster Asset

This asset calculates Weekly Throughput metrics using Python/Polars logic.
"""

from typing import Any

from dagster import AssetExecutionContext, asset

from pipelines.calculations import throughput as throughput_logic
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
    description="Calculate Weekly Throughput metrics using Python/Polars logic",
    compute_kind="python",
)
def calculate_throughput(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Weekly Throughput metrics (issues completed per week).

    This asset calculates:
    - Weekly throughput (issues completed per week by type)
    - Average lead time for completed issues

    Outputs:
    - metrics.fact_throughput (weekly throughput facts)
    - metrics.fact_throughput_aggregates (summary statistics)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load required tables into Polars DataFrames
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.jira_created_at, i.jira_resolved_at
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    status_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, to_status_id, changed_at
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
        f"Loaded {len(issues_df)} issues, {len(status_changelog_df)} status changes"
    )

    # =====================================================
    # Calculate weekly throughput facts
    # =====================================================
    context.log.info("Calculating weekly throughput...")
    throughput_df = throughput_logic.calculate_weekly_throughput(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
    )

    if throughput_df.is_empty():
        context.log.warning(
            "⚠️ No throughput data calculated. Check that issues have completion dates."
        )
        return {
            "status": "warning",
            "message": "No throughput data - no completed issues found",
            "fact_rows": 0,
        }

    context.log.info(f"Calculated throughput for {len(throughput_df)} week-type pairs")

    # Write throughput facts to database
    context.log.info("Writing to metrics.fact_throughput...")
    write_table(throughput_df, engine, table="fact_throughput", schema="metrics")

    # =====================================================
    # Return summary statistics
    # =====================================================
    total_issues = (
        int(throughput_df["issues_completed"].sum())
        if not throughput_df.is_empty()
        else 0
    )
    total_weeks = len(throughput_df["week_start_date"].unique())

    context.log.info(
        f"✅ Throughput calculation complete: "
        f"{total_issues} issues across {total_weeks} weeks"
    )

    return {
        "status": "success",
        "total_issues_completed": total_issues,
        "total_weeks": total_weeks,
        "fact_rows": len(throughput_df),
    }
