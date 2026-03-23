"""
Input Flow Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import input_flow as input_flow_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    load_commitment_rules_for_calc,
    resolve_rule_from_cache,
)
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
)
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issue_status_changelog",
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_boards",
        "clean_jira_board_columns",
    ],
    description="Calculate Input Flow metrics",
    compute_kind="python",
)
def calculate_input_flow(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "throughput")
    calc_id_input_flow = get_calculation_id(engine, "input_flow_weekly")

    context.log.info("Loading data for Input Flow metrics...")

    # Load Data
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, it.name as type_name
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )
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

    # Resolve Rules
    commitment_rules = load_commitment_rules_for_calc(engine, "input_flow_weekly")
    if not commitment_rules:
        commitment_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # 2. Calculation functions
    def calculate_base_facts(df_subset, sub_status_changelog):
        results = []
        p_ids = df_subset["project_id"].unique().to_list()

        for board in boards_df.to_dicts():
            p_id = board["project_id"]
            b_id = board["id"]
            if p_id not in p_ids:
                continue

            board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
            rule = resolve_rule_from_cache(commitment_rules, p_id, b_id)

            if not rule or board_cols.is_empty():
                continue

            points = identify_commitment_points_from_rule(rule, board_cols)
            start_status_ids = points.get("start_status_ids", [])

            if not start_status_ids:
                continue

            input_flow = input_flow_logic.calculate_input_flow_weekly(
                sub_status_changelog,
                start_status_ids,
                df_subset.filter(pl.col("project_id") == p_id),
            )

            if not input_flow.is_empty():
                results.append(input_flow)
        return results

    def transform_to_fact_values(
        wide_results, slice_rule_id=None, slice_value_col=None
    ):
        facts_list = []
        for df_wide in wide_results:
            facts = df_wide.with_columns(
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
                    pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                    pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                    if slice_value_col
                    else pl.lit(None).cast(pl.Utf8).alias("slice_value"),
                    pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                    pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_start_at"),
                    pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_end_at"),
                ]
            )
            facts_list.append(
                facts.select(
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
            )
        return facts_list

    # 3. BASE calculation
    base_wide_list = calculate_base_facts(issues_df, issue_status_changelog_df)
    all_facts = transform_to_fact_values(base_wide_list)

    # 4. Sliced calculation
    rules_df = get_slice_rules(engine, target_definition_id=def_id)
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def input_flow_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_status_changelog = issue_status_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        res_list = calculate_base_facts(df_subset, sub_status_changelog)
        if not res_list:
            return pl.DataFrame()

        for i, df in enumerate(res_list):
            df.rename(
                {"flow_count": "value", "iso_week_start_date": "time_id_src"},
                in_place=True,
            )
            res_list[i] = df
        return pl.concat(res_list)

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                input_flow_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                facts = sliced_wide.with_columns(
                    [
                        pl.lit(calc_id_input_flow).alias("metric_id"),
                        pl.col("project_id")
                        .replace(project_agg_map)
                        .alias("project_agg_id"),
                        pl.col("time_id_src")
                        .dt.strftime("%Y%m%d")
                        .cast(pl.Int32)
                        .alias("time_id"),
                        pl.col("value").alias("value"),
                        pl.lit("project").alias("entity_type"),
                        pl.col("project_id").alias("entity_id"),
                        pl.lit(rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                        pl.col("slice_value").cast(pl.Utf8).alias("slice_value"),
                        pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                        pl.lit(None)
                        .cast(pl.Datetime("us", "UTC"))
                        .alias("event_start_at"),
                        pl.lit(None)
                        .cast(pl.Datetime("us", "UTC"))
                        .alias("event_end_at"),
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
                all_facts.append(facts)

    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(all_facts)

    # 5. Write to DB
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
