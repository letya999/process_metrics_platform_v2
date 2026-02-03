"""
Time to Market Metrics Dagster Asset

This asset calculates Time to Market (TTM) - time from creation to release/deployment.
"""

from typing import Any

from dagster import AssetExecutionContext, asset

from pipelines.calculations import time_to_market as ttm_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_releases",
        "clean_jira_release_issues",
        "clean_jira_issue_status_changelog",
        "clean_jira_board_columns",
    ],
    description="Calculate Time to Market metrics (creation to release)",
    compute_kind="python",
)
def calculate_time_to_market(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Time to Market (TTM) metrics.

    This asset calculates:
    - Time to market for features/epics
    - TTM aggregates (avg, median, P90)
    - Release cadence metrics

    Outputs:
    - metrics.fact_time_to_market (per-issue TTM)
    - metrics.fact_ttm_aggregates (summary statistics)
    - metrics.fact_release_cadence (release frequency)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load required tables into Polars DataFrames
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, i.type_id,
               i.jira_created_at, i.jira_resolved_at
        FROM clean_jira.issues i
        """,
    )

    issue_types_df = read_table(
        engine,
        """
        SELECT id, name, hierarchy_level
        FROM clean_jira.issue_types
        """,
    )

    releases_df = read_table(
        engine,
        """
        SELECT id, project_id, external_id, name, release_date, is_released
        FROM clean_jira.releases
        """,
    )

    issue_fix_versions_df = read_table(
        engine,
        """
        SELECT issue_id, release_id AS version_id
        FROM clean_jira.release_issues
        WHERE is_active = true
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

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bc.position, bcs.status_id
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    context.log.info(f"Loaded {len(issues_df)} issues, {len(releases_df)} releases")

    # =====================================================
    # Calculate Time to Market facts
    # =====================================================
    context.log.info("Calculating time to market metrics...")
    ttm_df = ttm_logic.calculate_time_to_market(
        issues_df=issues_df,
        issue_types_df=issue_types_df,
        releases_df=releases_df,
        issue_fix_versions_df=issue_fix_versions_df,
        status_changelog_df=status_changelog_df,
        board_columns_df=board_columns_df,
    )

    if ttm_df.is_empty():
        context.log.warning(
            "⚠️ No TTM data calculated. Check that high-level issues "
            "(Epics/Stories) have release or completion dates."
        )
        return {
            "status": "warning",
            "message": "No TTM data - no completed high-level issues found",
            "fact_rows": 0,
        }

    context.log.info(f"Calculated TTM for {len(ttm_df)} high-level issues")

    # Write TTM facts to database
    context.log.info("Writing to metrics.fact_time_to_market...")
    write_table(ttm_df, engine, table="fact_time_to_market", schema="metrics")

    # =====================================================
    # Calculate TTM aggregates
    # =====================================================
    context.log.info("Calculating TTM aggregates...")
    aggregates_df = ttm_logic.calculate_ttm_aggregates(ttm_df)

    context.log.info(f"Calculated {len(aggregates_df)} aggregate rows")

    # Write aggregates to database
    context.log.info("Writing to metrics.fact_ttm_aggregates...")
    write_table(aggregates_df, engine, table="fact_ttm_aggregates", schema="metrics")

    # =====================================================
    # Calculate release cadence
    # =====================================================
    context.log.info("Calculating release cadence...")
    cadence_df = ttm_logic.calculate_release_cadence(
        releases_df=releases_df,
        days_back=180,
    )

    if not cadence_df.is_empty():
        context.log.info(f"Calculated cadence for {len(cadence_df)} projects")

        # Write cadence to database
        context.log.info("Writing to metrics.fact_release_cadence...")
        write_table(cadence_df, engine, table="fact_release_cadence", schema="metrics")
    else:
        context.log.info("No release cadence data (no releases found)")

    # =====================================================
    # Return summary statistics
    # =====================================================
    avg_ttm = (
        float(ttm_df["time_to_market_days"].mean()) if not ttm_df.is_empty() else 0.0
    )
    median_ttm = (
        float(ttm_df["time_to_market_days"].quantile(0.5))
        if not ttm_df.is_empty()
        else 0.0
    )

    context.log.info(
        f"✅ Time to Market calculation complete: "
        f"{len(ttm_df)} issues, avg {avg_ttm:.1f} days, median {median_ttm:.1f} days"
    )

    return {
        "status": "success",
        "total_issues": len(ttm_df),
        "avg_ttm_days": round(avg_ttm, 2),
        "median_ttm_days": round(median_ttm, 2),
        "aggregate_rows": len(aggregates_df),
        "cadence_rows": len(cadence_df) if not cadence_df.is_empty() else 0,
    }
