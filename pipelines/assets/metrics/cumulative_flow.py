"""
Cumulative Flow Diagram (CFD) Dagster Asset (Generic Long Metric Store)
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import cumulative_flow as cfd_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values


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
    description="Calculate CFD facts and write to generic fact_values",
    compute_kind="python",
)
def calculate_cumulative_flow_diagram(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    calc_id = get_calculation_id(engine, "cfd_count")

    context.log.info("Loading data from clean_jira schema...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.type_id, i.status_id, i.jira_created_at, p.project_key
        FROM clean_jira.issues i
        JOIN clean_jira.projects p ON i.project_id = p.id
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

    issue_statuses_df = read_table(
        engine,
        "SELECT id, project_id, name, category FROM clean_jira.issue_statuses",
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

    # 2. Calculate BASE CFD facts
    cfd_wide = cfd_logic.calculate_cumulative_flow_diagram(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        issue_statuses_df=issue_statuses_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        days_back=90,
    )

    if cfd_wide.is_empty():
        return {"status": "no_data"}

    # 3. Transform to Long Format (fact_values)
    # CFD uses board_column_id as entity_id. If NULL, use status_id.
    facts = cfd_wide.with_columns(
        [
            pl.lit(calc_id).alias("metric_id"),
            pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
            # date -> time_id (YYYYMMDD)
            pl.col("date").dt.strftime("%Y%m%d").cast(pl.Int32).alias("time_id"),
            pl.col("issue_count").cast(pl.Float64).alias("value"),
            pl.lit("board_column").alias("entity_type"),
            pl.coalesce([pl.col("column_id"), pl.col("status_id")])
            .cast(pl.Utf8)
            .alias("entity_id"),
            pl.lit(None).alias("slice_rule_id"),
            pl.lit(None).alias("slice_value"),
            pl.lit(None).alias("commitment_rule_id"),
            pl.lit(None).alias("event_start_at"),
            pl.lit(None).alias("event_end_at"),
        ]
    )

    final_df = facts.select(
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

    # 5. Write to DB
    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()
    project_agg_ids = list(project_agg_map.values())

    rows_written = write_fact_values(
        final_df,
        engine,
        metric_ids=[calc_id],
        project_agg_ids=project_agg_ids,
        time_id_start=time_id_start,
        time_id_end=time_id_end,
    )

    return {
        "status": "success",
        "rows_written": rows_written,
        "days_processed": len(cfd_wide["date"].unique()),
    }


@asset_check(asset=calculate_cumulative_flow_diagram)
def cfd_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "cfd_count")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
