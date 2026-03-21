import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import input_flow as input_flow_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    load_commitment_rules_for_calc,
    resolve_rule_from_cache,
)
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issue_status_changelog",
        "clean_jira_issues",
        "clean_jira_boards",
        "clean_jira_board_columns",
    ],
    description="Calculate Input Flow metrics",
    compute_kind="python",
)
def calculate_input_flow(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()

    # 1. Load Data
    issues_df = read_table(engine, "SELECT id, project_id FROM clean_jira.issues")
    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    issue_status_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.issue_status_changelog"
    )
    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
    """,
    )
    boards_df = read_table(engine, "SELECT id, project_id FROM clean_jira.boards")

    # 2. Resolve IDs and Rules
    calc_id_input_flow = get_calculation_id(engine, "input_flow_weekly")
    commitment_rules = load_commitment_rules_for_calc(engine, "input_flow_weekly")
    if commitment_rules.is_empty():
        # Fallback to lead_time_days rules
        commitment_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    all_facts = []

    # 3. Calculation per project/board
    for board in boards_df.to_dicts():
        p_id = board["project_id"]
        b_id = board["id"]

        board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
        rule = resolve_rule_from_cache(commitment_rules, p_id, b_id)

        if not rule or board_cols.is_empty():
            continue

        points = identify_commitment_points_from_rule(rule, board_cols)
        start_status_ids = points.get("start_status_ids", [])

        if not start_status_ids:
            continue

        input_flow = input_flow_logic.calculate_input_flow_weekly(
            issue_status_changelog_df,
            start_status_ids,
            issues_df.filter(pl.col("project_id") == p_id),
        )

        if not input_flow.is_empty():
            facts = input_flow.select(
                [
                    pl.lit(calc_id_input_flow).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("iso_week_start_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("flow_count").alias("value"),
                    pl.lit("project").alias("entity_type"),
                    pl.col("project_id").alias("entity_id"),
                ]
            )
            all_facts.append(facts)

    # 4. Write to DB
    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(all_facts)

    metric_ids = final_df["metric_id"].unique().to_list()
    project_agg_ids = final_df["project_agg_id"].unique().to_list()
    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()

    rows_written = write_fact_values(
        final_df,
        engine,
        metric_ids=metric_ids,
        project_agg_ids=project_agg_ids,
        time_id_start=time_id_start,
        time_id_end=time_id_end,
    )

    return {"status": "success", "rows_written": rows_written}


@asset_check(asset=calculate_input_flow)
def input_flow_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "input_flow_weekly")
    df = read_table(
        engine,
        "SELECT COUNT(*) as cnt FROM metrics.fact_values WHERE metric_id = :calc_id AND value < 0",
        params={"calc_id": calc_id},
    )
    if not df.is_empty() and df[0, "cnt"] > 0:
        return AssetCheckResult(
            passed=False, metadata={"error": "Negative values found"}
        )
    return AssetCheckResult(passed=True)
