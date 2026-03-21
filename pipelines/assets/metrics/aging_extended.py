import logging
from datetime import datetime, timezone

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import aging as aging_logic
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
        "clean_jira_field_value_changelog",
        "clean_jira_field_keys",
        "clean_jira_boards",
        "clean_jira_board_columns",
    ],
    description="Calculate Extended Aging metrics (blocked time, stale days)",
    compute_kind="python",
)
def calculate_aging_extended(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()
    now = datetime.now(timezone.utc)

    # 1. Load Data
    issues_df = read_table(
        engine,
        "SELECT id, project_id, external_key as key, status_id, updated_at FROM clean_jira.issues",
    )
    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    issue_status_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.issue_status_changelog"
    )
    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id, old_value::text as old_value, new_value::text as new_value, changed_at as change_time
        FROM clean_jira.field_value_changelog
    """,
    )
    field_keys_df = read_table(engine, "SELECT * FROM clean_jira.field_keys")
    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
    """,
    )
    boards_df = read_table(engine, "SELECT * FROM clean_jira.boards")

    # 2. Resolve IDs
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    calc_id_blocked = get_calculation_id(engine, "blocked_time_total")
    calc_id_stale = get_calculation_id(engine, "stale_days")

    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    all_facts = []

    # 3. Calculations

    # A. Blocked Time
    # Resolve blocked field key
    blocked_fields = field_keys_df.filter(
        (pl.col("external_key") == "blocked")
        | (pl.col("name").str.to_lowercase().str.contains("blocked"))
    )
    if not blocked_fields.is_empty():
        blocked_field_key_id = blocked_fields["id"][0]
        blocked_time = aging_logic.calculate_blocked_time(
            issues_df, field_value_changelog_df, blocked_field_key_id, now
        )

        if not blocked_time.is_empty():
            facts_blocked = blocked_time.select(
                [
                    pl.lit(calc_id_blocked).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.lit(int(now.strftime("%Y%m%d"))).cast(pl.Int32).alias("time_id"),
                    pl.col("blocked_hours").alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col("issue_id").alias("entity_id"),
                ]
            )
            all_facts.append(facts_blocked)

    # B. Stale Days
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

        stale = aging_logic.calculate_stale_days(
            issues_df.filter(pl.col("project_id") == p_id),
            issue_status_changelog_df,
            list(set(all_done_ids)),
            now,
        )

        if not stale.is_empty():
            facts_stale = stale.select(
                [
                    pl.lit(calc_id_stale).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.lit(int(now.strftime("%Y%m%d"))).cast(pl.Int32).alias("time_id"),
                    pl.col("stale_days").alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col("issue_id").alias("entity_id"),
                ]
            )
            all_facts.append(facts_stale)

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


@asset_check(asset=calculate_aging_extended)
def aging_extended_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "stale_days")
    df = read_table(
        engine,
        "SELECT COUNT(*) as cnt FROM metrics.fact_values WHERE metric_id = :calc_id AND value < 0",
        params={"calc_id": calc_id},
    )
    if not df.is_empty() and df[0, "cnt"] > 0:
        return AssetCheckResult(
            passed=False, metadata={"error": "Negative stale days found"}
        )
    return AssetCheckResult(passed=True)
