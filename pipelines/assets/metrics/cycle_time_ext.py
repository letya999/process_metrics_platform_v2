"""
Extended Cycle Time Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import cycle_time_ext as cycle_logic
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
        "clean_jira_issues",
        "clean_jira_issue_status_changelog",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_types",
    ],
    description="Calculate Extended Cycle Time metrics",
    compute_kind="python",
)
def calculate_cycle_time_extended(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "cycle_time")
    calc_id_lifetime = get_calculation_id(engine, "issue_lifetime_days")
    calc_id_custom = get_calculation_id(engine, "cycle_time_custom")
    calc_id_epic = get_calculation_id(engine, "epic_delivery_time")

    context.log.info("Loading data for Extended Cycle Time metrics...")

    # Load Data
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key as issue_key,
               i.jira_created_at as created_at, it.name as type_name,
               i.type_id as issue_type_id, i.parent_id
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
    boards_df = read_table(engine, "SELECT * FROM clean_jira.boards")

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")
    custom_cycle_rules = load_commitment_rules_for_calc(engine, "cycle_time_custom")
    epic_rules = load_commitment_rules_for_calc(engine, "epic_delivery_time")
    if not epic_rules:
        epic_rules = lead_time_rules

    # 2. Calculation functions
    def calculate_base_facts(df_subset, sub_status_changelog):
        results = []
        p_ids = df_subset["project_id"].unique().to_list()

        # A. Issue Lifetime
        lifetime_results = []
        for p_id in p_ids:
            p_boards = boards_df.filter(pl.col("project_id") == p_id)["id"].to_list()
            all_done_ids = []
            for b_id in p_boards:
                rule = resolve_rule_from_cache(lead_time_rules, p_id, b_id)
                if rule:
                    points = identify_commitment_points_from_rule(
                        rule, board_columns_df.filter(pl.col("board_id") == b_id)
                    )
                    all_done_ids.extend(points.get("end_status_ids", []))
            if all_done_ids:
                lifetime = cycle_logic.calculate_issue_lifetime(
                    df_subset.filter(pl.col("project_id") == p_id),
                    sub_status_changelog,
                    list(set(all_done_ids)),
                )
                if not lifetime.is_empty():
                    lifetime_results.append(lifetime)
        if lifetime_results:
            results.append(
                pl.concat(lifetime_results).with_columns(
                    pl.lit(calc_id_lifetime).alias("calc_id")
                )
            )

        # B. Cycle Time Custom
        custom_results = []
        for board in boards_df.to_dicts():
            p_id = board["project_id"]
            b_id = board["id"]
            if p_id not in p_ids:
                continue
            rule = resolve_rule_from_cache(custom_cycle_rules, p_id, b_id)
            if not rule:
                continue
            board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
            points = identify_commitment_points_from_rule(rule, board_cols)
            start_ids, end_ids = points.get("start_status_ids", []), points.get(
                "end_status_ids", []
            )
            if start_ids and end_ids:
                custom_cycle = cycle_logic.calculate_cycle_time_custom(
                    df_subset.filter(pl.col("project_id") == p_id),
                    sub_status_changelog,
                    start_ids[0],
                    end_ids[0],
                )
                if not custom_cycle.is_empty():
                    custom_results.append(custom_cycle)
        if custom_results:
            results.append(
                pl.concat(custom_results).with_columns(
                    pl.lit(calc_id_custom).alias("calc_id")
                )
            )

        # C. Epic Delivery Time
        epic_results = []
        for board in boards_df.to_dicts():
            p_id = board["project_id"]
            b_id = board["id"]
            if p_id not in p_ids:
                continue
            rule = resolve_rule_from_cache(epic_rules, p_id, b_id)
            if not rule:
                continue
            board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
            points = identify_commitment_points_from_rule(rule, board_cols)
            start_ids, end_ids = points.get("start_status_ids", []), points.get(
                "end_status_ids", []
            )
            if start_ids and end_ids:
                epic_delivery = cycle_logic.calculate_epic_delivery_time(
                    df_subset.filter(pl.col("project_id") == p_id),
                    sub_status_changelog,
                    start_ids,
                    end_ids,
                )
                if not epic_delivery.is_empty():
                    epic_results.append(epic_delivery)
        if epic_results:
            results.append(
                pl.concat(epic_results).with_columns(
                    pl.lit(calc_id_epic).alias("calc_id")
                )
            )

        return results

    def transform_to_fact_values(
        wide_results, slice_rule_id=None, slice_value_col=None
    ):
        facts_list = []
        for df_wide in wide_results:
            cid = df_wide["calc_id"][0]
            val_col = (
                "lifetime_days"
                if cid == calc_id_lifetime
                else ("cycle_days" if cid == calc_id_custom else "delivery_days")
            )
            time_col = (
                "done_date"
                if cid == calc_id_lifetime
                else ("end_at" if cid == calc_id_custom else "epic_end")
            )
            ent_id_col = "epic_id" if cid == calc_id_epic else "id"

            facts = df_wide.with_columns(
                [
                    pl.lit(cid).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col(time_col)
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col(val_col).alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col(ent_id_col).alias("entity_id"),
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

    def cycle_extended_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_changelog = issue_status_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        res_list = calculate_base_facts(df_subset, sub_changelog)
        if not res_list:
            return pl.DataFrame()

        # Unify columns for apply_slicing
        for i, df in enumerate(res_list):
            cid = df["calc_id"][0]
            val_col = (
                "lifetime_days"
                if cid == calc_id_lifetime
                else ("cycle_days" if cid == calc_id_custom else "delivery_days")
            )
            time_col = (
                "done_date"
                if cid == calc_id_lifetime
                else ("end_at" if cid == calc_id_custom else "epic_end")
            )
            ent_id_col = "epic_id" if cid == calc_id_epic else "id"
            res_list[i] = df.rename(
                {
                    val_col: "value",
                    time_col: "time_id_src",
                    ent_id_col: "entity_id_src",
                }
            )
        return pl.concat(res_list)

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                cycle_extended_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                for cid in [calc_id_lifetime, calc_id_custom, calc_id_epic]:
                    sub_sliced = sliced_wide.filter(pl.col("calc_id") == cid)
                    if not sub_sliced.is_empty():
                        facts = sub_sliced.with_columns(
                            [
                                pl.lit(cid).alias("metric_id"),
                                pl.col("project_id")
                                .replace(project_agg_map)
                                .alias("project_agg_id"),
                                pl.col("time_id_src")
                                .dt.strftime("%Y%m%d")
                                .cast(pl.Int32)
                                .alias("time_id"),
                                pl.col("value").alias("value"),
                                pl.lit("issue").alias("entity_type"),
                                pl.col("entity_id_src").alias("entity_id"),
                                pl.lit(rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                                pl.col("slice_value")
                                .cast(pl.Utf8)
                                .alias("slice_value"),
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


@asset_check(asset=calculate_cycle_time_extended)
def cycle_time_ext_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "issue_lifetime_days")
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
