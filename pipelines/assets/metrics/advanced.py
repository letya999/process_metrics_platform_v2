"""
Advanced Metrics Dagster Asset

This asset calculates Advanced / Pro metrics, currently implementing
Work Item Aging and its slices. Logic for Flow Efficiency and
Control Chart will be added here subsequently.
"""

from typing import Any

from dagster import AssetExecutionContext, asset

from pipelines.calculations import aging as aging_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_issue_statuses",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Advanced metrics (Work Item Aging)",
    compute_kind="python",
)
def calculate_advanced_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Advanced metrics (Work Item Aging, etc.).

    Outputs:
    - metrics.fact_work_item_aging
    - metrics.fact_work_item_aging_slices
    """
    engine = database.get_engine()

    context.log.info("Loading data for advanced metrics...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.status_id, i.jira_created_at
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

    boards_df = read_table(engine, "SELECT id, project_id FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bc.position, bcs.status_id
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    issue_statuses_df = read_table(
        engine, "SELECT id, category, name FROM clean_jira.issue_statuses"
    )

    # 1. Calculate Work Item Aging
    context.log.info("Calculating Work Item Aging...")
    aging_df = aging_logic.calculate_work_item_aging_facts(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        issue_statuses_df=issue_statuses_df,
    )

    if not aging_df.is_empty():
        context.log.info(
            f"Writing {len(aging_df)} rows to metrics.fact_work_item_aging..."
        )
        write_table(aging_df, engine, table="fact_work_item_aging", schema="metrics")

        # Calculate slices
        from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules

        rules_df = get_slice_rules(engine, target_metric_table="fact_work_item_aging")

        def aging_slice_identity(df_subset):
            return df_subset  # raw rows

        slice_df = apply_slicing(
            aging_df.rename(
                {"issue_type": "type_name"}
            ),  # apply_slicing might expect type_name or issue_type
            rules_df,
            aging_slice_identity,
        )
        # Fix back column name if rename happened
        if "type_name" in aging_df.columns:
            pass  # it was issue_type in aging_df result

        if not slice_df.is_empty():
            context.log.info(
                f"Writing {len(slice_df)} rows to metrics.fact_work_item_aging_slices..."
            )
            write_table(
                slice_df, engine, table="fact_work_item_aging_slices", schema="metrics"
            )
    else:
        context.log.warning("No aging data calculated.")

    return {
        "status": "success",
        "aging_rows": len(aging_df) if not aging_df.is_empty() else 0,
        "aging_slices": len(slice_df)
        if "slice_df" in locals() and not slice_df.is_empty()
        else 0,
    }
