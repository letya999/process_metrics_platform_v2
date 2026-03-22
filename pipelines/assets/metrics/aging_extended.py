"""
Extended Aging Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from datetime import datetime, timezone
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import aging as aging_logic
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
) -> dict[str, Any]:
    engine = database.get_engine()
    now = datetime.now(timezone.utc)

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "aging")
    calc_id_blocked = get_calculation_id(engine, "blocked_time_total")
    calc_id_stale = get_calculation_id(engine, "stale_days")

    context.log.info("Loading data for Extended Aging metrics...")

    # Load Data
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key as key, it.name as type_name,
               i.status_id, i.updated_at
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
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

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    # 2. Calculation functions for base and slices
    def calculate_base_facts(df_subset, sub_status_changelog, sub_field_changelog):
        results = []

        # A. Blocked Time
        blocked_fields = field_keys_df.filter(
            (pl.col("external_key") == "blocked")
            | (pl.col("name").str.to_lowercase().str.contains("blocked"))
        )
        if not blocked_fields.is_empty():
            blocked_field_key_id = blocked_fields["id"][0]
            blocked_time = aging_logic.calculate_blocked_time(
                df_subset, sub_field_changelog, blocked_field_key_id, now
            )
            if not blocked_time.is_empty():
                results.append(
                    blocked_time.with_columns(pl.lit(calc_id_blocked).alias("calc_id"))
                )

        # B. Stale Days
        # This requires board-specific "done" statuses
        stale_results = []
        p_ids = df_subset["project_id"].unique().to_list()
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
                stale = aging_logic.calculate_stale_days(
                    df_subset.filter(pl.col("project_id") == p_id),
                    sub_status_changelog,
                    list(set(all_done_ids)),
                    now,
                )
                if not stale.is_empty():
                    stale_results.append(stale)

        if stale_results:
            results.append(
                pl.concat(stale_results).with_columns(
                    pl.lit(calc_id_stale).alias("calc_id")
                )
            )

        return results

    def transform_to_fact_values(
        wide_results, slice_rule_id=None, slice_value_col=None
    ):
        facts_list = []
        time_id = int(now.strftime("%Y%m%d"))

        for df_wide in wide_results:
            val_col = (
                "blocked_hours" if "blocked_hours" in df_wide.columns else "stale_days"
            )
            cid = df_wide["calc_id"][0]

            facts = df_wide.with_columns(
                [
                    pl.lit(cid).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.lit(time_id).cast(pl.Int32).alias("time_id"),
                    pl.col(val_col).alias("value"),
                    pl.lit("issue").alias("entity_type"),
                    pl.col("issue_id").alias("entity_id"),
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
    base_wide_list = calculate_base_facts(
        issues_df, issue_status_changelog_df, field_value_changelog_df
    )
    all_facts = transform_to_fact_values(base_wide_list)

    # 4. Sliced calculation
    rules_df = get_slice_rules(engine, target_definition_id=def_id)
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def aging_extended_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_status_changelog = issue_status_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        sub_field_changelog = field_value_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )

        # apply_slicing expects a single DataFrame return, but we have multiple metrics.
        # We'll return a concatenated DF with a metric indicator.
        res_list = calculate_base_facts(
            df_subset, sub_status_changelog, sub_field_changelog
        )
        if not res_list:
            return pl.DataFrame()

        # Prepare for concat by renaming value columns
        for df in res_list:
            vcol = "blocked_hours" if "blocked_hours" in df.columns else "stale_days"
            df.rename({vcol: "value"}, in_place=True)

        return pl.concat(res_list)

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                aging_extended_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                # Split back by calc_id
                for cid in [calc_id_blocked, calc_id_stale]:
                    sub_sliced = sliced_wide.filter(pl.col("calc_id") == cid)
                    if not sub_sliced.is_empty():
                        # Transform to fact values
                        # We need to rename "value" back or handle it in transform
                        time_id = int(now.strftime("%Y%m%d"))
                        facts = sub_sliced.with_columns(
                            [
                                pl.lit(cid).alias("metric_id"),
                                pl.col("project_id")
                                .replace(project_agg_map)
                                .alias("project_agg_id"),
                                pl.lit(time_id).cast(pl.Int32).alias("time_id"),
                                pl.col("value").alias("value"),
                                pl.lit("issue").alias("entity_type"),
                                pl.col("issue_id").alias("entity_id"),
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
