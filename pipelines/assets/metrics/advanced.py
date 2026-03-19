"""
Advanced Metrics Dagster Asset (Generic Long Metric Store)
"""

import datetime
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import aging as aging_logic
from pipelines.calculations import flow_efficiency as flow_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_project_agg_id,
)
from pipelines.utils.polars_db import read_table, write_fact_values


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
    description="Calculate Aging and Flow Efficiency facts",
    compute_kind="python",
)
def calculate_advanced_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    aging_calc_id = get_calculation_id(engine, "aging_days")
    flow_map = {
        "active_days": get_calculation_id(engine, "flow_active_days"),
        "wait_days": get_calculation_id(engine, "flow_wait_days"),
        "efficiency_pct": get_calculation_id(engine, "flow_efficiency_pct"),
    }

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

    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    status_changelog_df = read_table(
        engine,
        "SELECT issue_id, from_status_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
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

    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )

    # 2. Calculate Work Item Aging
    aging_wide = aging_logic.calculate_work_item_aging_facts(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        issue_statuses_df=issue_statuses_df,
    )

    # 3. Calculate Flow Efficiency
    # Map statuses to types
    active_statuses = issue_statuses_df.filter(pl.col("category") == "indeterminate")[
        "id"
    ].to_list()
    wait_statuses = issue_statuses_df.filter(pl.col("category") == "todo")[
        "id"
    ].to_list()
    end_statuses = issue_statuses_df.filter(pl.col("category") == "done")[
        "id"
    ].to_list()

    flow_wide = flow_logic.calculate_flow_efficiency_per_issue(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        active_status_ids=active_statuses,
        wait_status_ids=wait_statuses,
        end_status_ids=end_statuses,
    )

    all_facts = []

    # Process Aging
    if not aging_wide.is_empty():
        today_id = int(datetime.date.today().strftime("%Y%m%d"))
        aging_facts = aging_wide.with_columns(
            [
                pl.lit(aging_calc_id).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                pl.lit(today_id).alias("time_id"),
                pl.col("age_days").alias("value"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_key").alias("entity_id"),
                pl.lit(None).alias("slice_rule_id"),
                pl.lit(None).alias("slice_value"),
                pl.lit(None).alias("commitment_rule_id"),
                pl.col("commitment_start_at").alias("event_start_at"),
                pl.lit(None).cast(pl.Datetime).alias("event_end_at"),
            ]
        ).select(
            [
                "metric_id",
                "project_agg_id",
                "time_id",
                "value",
                "entity_type",
                "entity_id",
                "slice_rule_id",
                "slice_value",
                "commitment_rule_id",
                "event_start_at",
                "event_end_at",
            ]
        )
        all_facts.append(aging_facts)

    # Process Flow Efficiency
    if not flow_wide.is_empty():
        melted_flow = flow_wide.melt(
            id_vars=["project_id", "issue_key", "completion_date"],
            value_vars=["active_days", "wait_days", "efficiency_pct"],
            variable_name="calc_source",
            value_name="value",
        )
        flow_facts = melted_flow.with_columns(
            [
                pl.col("calc_source").replace(flow_map).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                pl.col("completion_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_key").alias("entity_id"),
                pl.lit(None).alias("slice_rule_id"),
                pl.lit(None).alias("slice_value"),
                pl.lit(None).alias("commitment_rule_id"),
                pl.lit(None).cast(pl.Datetime).alias("event_start_at"),
                pl.col("completion_date").alias("event_end_at"),
            ]
        ).select(
            [
                "metric_id",
                "project_agg_id",
                "time_id",
                "value",
                "entity_type",
                "entity_id",
                "slice_rule_id",
                "slice_value",
                "commitment_rule_id",
                "event_start_at",
                "event_end_at",
            ]
        )
        all_facts.append(flow_facts)

    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(all_facts)

    # Write to DB
    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()
    metric_ids = final_df["metric_id"].unique().to_list()
    project_agg_ids = list(project_agg_map.values())

    rows_written = write_fact_values(
        final_df,
        engine,
        metric_ids=metric_ids,
        project_agg_ids=project_agg_ids,
        time_id_start=time_id_start,
        time_id_end=time_id_end,
    )

    return {
        "status": "success",
        "rows_written": rows_written,
        "aging_issues": len(aging_wide) if not aging_wide.is_empty() else 0,
        "flow_issues": len(flow_wide) if not flow_wide.is_empty() else 0,
    }


@asset_check(asset=calculate_advanced_metrics)
def advanced_metrics_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "aging_days")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"aging_row_count": count})
