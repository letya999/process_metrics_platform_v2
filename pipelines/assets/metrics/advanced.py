"""
Advanced Metrics Dagster Assets

This asset calculates Pro/Advanced metrics using Python/Polars logic:
- Work Item Aging
- Flow Efficiency
- Control Chart
- Lead Time Trends
"""

from typing import Any

import polars as pl
from dagster import AssetExecutionContext, asset

from pipelines.calculations import (
    aging as aging_logic,
)
from pipelines.calculations import (
    control_chart as control_chart_logic,
)
from pipelines.calculations import (
    flow_efficiency as flow_efficiency_logic,
)
from pipelines.calculations import (
    lead_time as lead_time_logic,  # Needed for base lead time data
)
from pipelines.calculations import (
    lead_time_trend as trend_logic,
)
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
        "clean_jira_projects",
        "clean_jira_statuses",  # Needed for wait status detection
    ],
    description="Calculate Advanced/Pro metrics (Aging, Flow Efficiency, etc.)",
    compute_kind="python",
)
def calculate_advanced_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate generic 'Pro' metrics that augment base lead time/velocity.

    This unified asset handles:
    1. Work Item Aging (fact_work_item_aging)
    2. Flow Efficiency (fact_flow_efficiency)
    3. Control Chart Stats (fact_control_chart)
    4. Lead Time Trends (fact_lead_time_trend)
    """
    engine = database.get_engine()
    context.log.info("Loading data for Advanced Metrics...")

    # 1. Load Data
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, i.summary, i.type_id, i.status_id,
               it.name AS type_name, i.jira_created_at, i.jira_resolved_at,
               i.status_id AS current_status_id -- Important for Aging
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

    statuses_df = read_table(
        engine, "SELECT id, project_id, name, category FROM clean_jira.issue_statuses"
    )

    context.log.info(f"Loaded {len(issues_df)} issues for processing")

    # =====================================================
    # 1. WORK ITEM AGING
    # =====================================================
    context.log.info("Calculating Work Item Aging...")
    aging_df = aging_logic.calculate_aging_work(
        issues_df, status_changelog_df, boards_df, board_columns_df
    )

    if not aging_df.is_empty():
        # Ensure column names match DB exact spec if needed, usually logic matches
        write_table(aging_df, engine, table="fact_work_item_aging", schema="metrics")
        context.log.info(f"Written {len(aging_df)} aging records")
    else:
        context.log.info("No active aging items found")

    # =====================================================
    # 2. FLOW EFFICIENCY
    # =====================================================
    context.log.info("Calculating Flow Efficiency...")

    # Heuristic for wait statuses if not strictly defined in DB
    # In a real app, this should come from a config table
    wait_status_ids = []
    if not statuses_df.is_empty():
        # Case-insensitive check for 'blocked', 'hold', 'wait'
        wait_pattern = "(?i)blocked|hold|wait|review"
        wait_statuses = statuses_df.filter(pl.col("name").str.contains(wait_pattern))
        if not wait_statuses.is_empty():
            wait_status_ids = wait_statuses["id"].to_list()
            context.log.info(
                f"Using wait statuses ids: {wait_status_ids} ({len(wait_status_ids)} found)"
            )

    efficiency_df = flow_efficiency_logic.calculate_flow_efficiency(
        issues_df, status_changelog_df, boards_df, board_columns_df, wait_status_ids
    )

    if not efficiency_df.is_empty():
        write_table(
            efficiency_df, engine, table="fact_flow_efficiency", schema="metrics"
        )
        context.log.info(f"Written {len(efficiency_df)} flow efficiency records")

    # =====================================================
    # 3. CONTROL CHART & 4. TRENDS (Require Lead Time Base)
    # =====================================================
    # We recalculate base lead time in-memory to ensure we have the latest data
    # without depending strictly on the DB state of another asset, primarily for robustness
    lt_df = lead_time_logic.calculate_lead_time_facts(
        issues_df, status_changelog_df, boards_df, board_columns_df
    )

    if not lt_df.is_empty():
        # Control Chart
        context.log.info("Calculating Control Chart Stats...")
        cc_df = control_chart_logic.calculate_control_chart_stats(lt_df)
        if not cc_df.is_empty():
            # Select only DB columns
            cc_write = cc_df.select(
                [
                    "project_id",
                    "issue_id",
                    "commitment_end_at",
                    "lead_time_days",
                    "rolling_mean",
                    "rolling_std",
                    "ucl_2sigma",
                    "ucl_3sigma",
                    "is_outlier",
                ]
            )
            write_table(cc_write, engine, table="fact_control_chart", schema="metrics")
            context.log.info(f"Written {len(cc_write)} control chart records")

        # Lead Time Trends
        context.log.info("Calculating Lead Time Trends...")
        trend_df = trend_logic.calculate_lead_time_trends(lt_df, period="1w")
        if not trend_df.is_empty():
            # Add implicit columns
            # logic returns: [period_start, count, p50, p85, p95, trend_p85]
            # DB needs: project_id, period_type
            # CAUTION: trend logic groups by period, but if we have multiple projects,
            # we must process per project or the logic must handle it.
            # Current logic in lead_time_trend.py aggregates EVERYTHING passed to it.
            # So we must loop by project.

            project_ids = lt_df["project_id"].unique().to_list()
            all_trends = []

            for pid in project_ids:
                proj_lt_df = lt_df.filter(pl.col("project_id") == pid)
                p_trend = trend_logic.calculate_lead_time_trends(
                    proj_lt_df, period="1w"
                )
                if not p_trend.is_empty():
                    p_trend = p_trend.with_columns(
                        [
                            pl.lit(pid).alias("project_id"),
                            pl.lit("weekly").alias("period_type"),
                        ]
                    )
                    all_trends.append(p_trend)

            if all_trends:
                final_trend_df = pl.concat(all_trends)
                write_table(
                    final_trend_df,
                    engine,
                    table="fact_lead_time_trend",
                    schema="metrics",
                )
                context.log.info(f"Written {len(final_trend_df)} trend records")

    return {
        "status": "success",
        "aging_records": len(aging_df),
        "flow_records": len(efficiency_df),
    }
