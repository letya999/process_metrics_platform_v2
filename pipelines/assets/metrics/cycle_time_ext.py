import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import cycle_time_ext as cycle_logic
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
):
    engine = database.get_engine()

    # 1. Load Data
    issues_df = read_table(
        engine,
        "SELECT id, project_id, external_key as issue_key, jira_created_at as created_at, type_id as issue_type_id, parent_id FROM clean_jira.issues",
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

    # 2. Resolve IDs and Rules
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")
    custom_cycle_rules = load_commitment_rules_for_calc(engine, "cycle_time_custom")
    epic_rules = load_commitment_rules_for_calc(engine, "epic_delivery_time")
    if not epic_rules:
        epic_rules = lead_time_rules

    all_facts = []

    # 3. Calculations

    # A. Issue Lifetime
    calc_id_lifetime = get_calculation_id(engine, "issue_lifetime_days")
    # For lifetime, we need done_status_ids
    # We aggregate done_status_ids across all boards for a project
    for p_id in project_ids:
        p_boards = boards_df.filter(pl.col("project_id") == p_id)["id"].to_list()
        all_done_ids = []
        for b_id in p_boards:
            rule = resolve_rule_from_cache(lead_time_rules, p_id, b_id)
            if rule:
                points = identify_commitment_points_from_rule(
                    rule, board_columns_df.filter(pl.col("board_id") == b_id)
                )
                all_done_ids.extend(points.get("end_status_ids", []))

        if not all_done_ids:
            continue

        lifetime = cycle_logic.calculate_issue_lifetime(
            issues_df.filter(pl.col("project_id") == p_id),
            issue_status_changelog_df,
            list(set(all_done_ids)),
        )

        if not lifetime.is_empty():
            facts = lifetime.select(
                [
                    pl.lit(calc_id_lifetime).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("done_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("lifetime_days").alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col("id").alias("entity_id"),
                ]
            )
            all_facts.append(facts)

    # B. Cycle Time Custom
    calc_id_custom = get_calculation_id(engine, "cycle_time_custom")
    for board in boards_df.to_dicts():
        p_id = board["project_id"]
        b_id = board["id"]
        rule = resolve_rule_from_cache(custom_cycle_rules, p_id, b_id)
        if not rule:
            continue

        board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
        points = identify_commitment_points_from_rule(rule, board_cols)
        start_ids = points.get("start_status_ids", [])
        end_ids = points.get("end_status_ids", [])

        if not start_ids or not end_ids:
            continue

        custom_cycle = cycle_logic.calculate_cycle_time_custom(
            issues_df.filter(pl.col("project_id") == p_id),
            issue_status_changelog_df,
            start_ids[0],
            end_ids[0],
        )

        if not custom_cycle.is_empty():
            facts = custom_cycle.select(
                [
                    pl.lit(calc_id_custom).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("end_at")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("cycle_days").alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col("id").alias("entity_id"),
                ]
            )
            all_facts.append(facts)

    # C. Epic Delivery Time
    calc_id_epic = get_calculation_id(engine, "epic_delivery_time")
    for board in boards_df.to_dicts():
        p_id = board["project_id"]
        b_id = board["id"]
        rule = resolve_rule_from_cache(epic_rules, p_id, b_id)
        if not rule:
            continue

        board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
        points = identify_commitment_points_from_rule(rule, board_cols)
        start_ids = points.get("start_status_ids", [])
        end_ids = points.get("end_status_ids", [])

        if not start_ids or not end_ids:
            continue

        epic_delivery = cycle_logic.calculate_epic_delivery_time(
            issues_df.filter(pl.col("project_id") == p_id),
            issue_status_changelog_df,
            start_ids,
            end_ids,
        )

        if not epic_delivery.is_empty():
            facts = epic_delivery.select(
                [
                    pl.lit(calc_id_epic).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("epic_end")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("delivery_days").alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col("epic_id").alias("entity_id"),
                ]
            )
            all_facts.append(facts)

    # 4. Write to DB
    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat([f for f in all_facts if not f.is_empty()])

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
