"""
Sprint Health Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import sprint_health as sprint_health_logic
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
        "clean_jira_sprints",
        "clean_jira_sprint_issues",
        "clean_jira_sprint_issues_changelog",
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_field_values",
        "clean_jira_field_keys",
        "clean_jira_issue_status_changelog",
        "clean_jira_board_columns",
        "clean_jira_boards",
    ],
    description="Calculate Sprint Health metrics",
    compute_kind="python",
)
def calculate_sprint_health(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "sprint_health")
    calc_id_added_count = get_calculation_id(engine, "sprint_added_issues_count")
    calc_id_added_sp = get_calculation_id(engine, "sprint_added_sp_sum")
    calc_id_removed_count = get_calculation_id(engine, "sprint_removed_issues_count")
    calc_id_removed_sp = get_calculation_id(engine, "sprint_removed_sp_sum")
    calc_id_spillover = get_calculation_id(engine, "sprint_spillover_count")
    calc_id_burndown = get_calculation_id(engine, "sprint_burndown_remaining_sp")
    calc_id_activation = get_calculation_id(engine, "activation_velocity_pct")
    calc_id_unestimated = get_calculation_id(engine, "unestimated_closed_count")
    calc_id_field_pct = get_calculation_id(engine, "field_value_sprint_pct")

    context.log.info("Loading data for Sprint Health metrics...")

    # Load Data
    sprints_df = read_table(
        engine,
        "SELECT * FROM clean_jira.sprints WHERE status IN ('closed', 'active') AND start_date IS NOT NULL",
    )
    if sprints_df.is_empty():
        return {"status": "skipped", "reason": "No sprints found"}

    sprint_issues_df = read_table(engine, "SELECT * FROM clean_jira.sprint_issues")
    sprint_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.sprint_issues_changelog"
    )
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key as issue_key, i.jira_created_at as created_at,
               i.jira_updated_at as updated_at, i.jira_resolved_at, i.status_id,
               i.type_id as issue_type_id, it.name as type_name
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
    """,
    )
    field_keys_df = read_table(engine, "SELECT * FROM clean_jira.field_keys")
    field_values_df = read_table(
        engine,
        "SELECT issue_id, field_key_id, json_value::text as json_value FROM clean_jira.field_values",
    )
    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id, old_value::text as old_value, new_value::text as new_value, changed_at
        FROM clean_jira.field_value_changelog
    """,
    )
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
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # SP field key
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None

    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")
    activation_rules = (
        load_commitment_rules_for_calc(engine, "activation_velocity_pct")
        or lead_time_rules
    )

    # 2. Calculation functions
    def calculate_base_facts(
        sub_issues,
        sub_sprint_issues,
        sub_sprint_changelog,
        sub_status_changelog,
        sub_field_values,
        sub_field_changelog,
    ):
        results = []
        p_ids = sub_issues["project_id"].unique().to_list()
        sub_sprints = sprints_df.filter(pl.col("project_id").is_in(p_ids))
        if sub_sprints.is_empty():
            return results

        # A. Scope Changes
        scope_changes = sprint_health_logic.calculate_sprint_scope_changes(
            sub_sprints,
            sub_sprint_changelog,
            sub_issues,
            sub_field_values,
            field_keys_df,
            sub_field_changelog,
        )
        if not scope_changes.is_empty():
            for col, cid in {
                "added_count": calc_id_added_count,
                "added_sp": calc_id_added_sp,
                "removed_count": calc_id_removed_count,
                "removed_sp": calc_id_removed_sp,
            }.items():
                results.append(
                    scope_changes.select(
                        [
                            "project_id",
                            pl.col("start_date").alias("time_date"),
                            pl.col(col).alias("value"),
                            pl.lit("sprint").alias("entity_type"),
                            pl.col("iteration_id").alias("entity_id"),
                            pl.lit(cid).alias("calc_id"),
                        ]
                    )
                )

        # B. Spillover
        spillover = sprint_health_logic.calculate_sprint_spillover(
            sub_sprints, sub_sprint_issues
        )
        if not spillover.is_empty():
            results.append(
                spillover.select(
                    [
                        "project_id",
                        pl.col("start_date").alias("time_date"),
                        pl.col("spillover_count").alias("value"),
                        pl.lit("sprint").alias("entity_type"),
                        pl.col("iteration_id").alias("entity_id"),
                        pl.lit(calc_id_spillover).alias("calc_id"),
                    ]
                )
            )

        # C. Burndown & Activation
        for sprint in sub_sprints.to_dicts():
            p_id, s_id = sprint["project_id"], sprint["id"]
            s_df = sub_sprints.filter(pl.col("id") == s_id)
            b_id = (
                boards_df.filter(pl.col("project_id") == p_id).select("id").to_series()
            )
            b_id = b_id[0] if not b_id.is_empty() else None
            if not b_id:
                continue

            board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
            rule = resolve_rule_from_cache(lead_time_rules, p_id, b_id)
            if not rule:
                continue
            points = identify_commitment_points_from_rule(rule, board_cols)
            done_ids = points.get("end_status_ids", [])

            # Burndown
            burndown = sprint_health_logic.calculate_sprint_burndown(
                s_df,
                sub_sprint_issues,
                sub_sprint_changelog,
                sub_status_changelog,
                done_ids,
                sub_issues,
                sub_field_values,
                field_keys_df,
                sub_field_changelog,
            )
            if not burndown.is_empty():
                results.append(
                    burndown.select(
                        [
                            "project_id",
                            pl.col("time_date"),
                            pl.col("remaining_sp").alias("value"),
                            pl.lit("sprint").alias("entity_type"),
                            pl.col("iteration_id").alias("entity_id"),
                            pl.lit(calc_id_burndown).alias("calc_id"),
                        ]
                    )
                )

            # Activation
            act_rule = resolve_rule_from_cache(activation_rules, p_id, b_id)
            if act_rule:
                act_pts = identify_commitment_points_from_rule(act_rule, board_cols)
                if act_pts.get("start_status_ids"):
                    activation = sprint_health_logic.calculate_activation_velocity(
                        s_df,
                        sub_sprint_issues,
                        sub_sprint_changelog,
                        sub_status_changelog,
                        sub_issues,
                        sub_field_values,
                        field_keys_df,
                        sub_field_changelog,
                        act_pts["start_status_ids"][0],
                    )
                    if not activation.is_empty():
                        results.append(
                            activation.select(
                                [
                                    "project_id",
                                    pl.col("time_date"),
                                    pl.col("activation_pct").alias("value"),
                                    pl.lit("sprint").alias("entity_type"),
                                    pl.col("iteration_id").alias("entity_id"),
                                    pl.lit(calc_id_activation).alias("calc_id"),
                                ]
                            )
                        )

            # D. Unestimated
            if sp_field_key_id:
                unest = sprint_health_logic.calculate_unestimated_closed(
                    s_df,
                    sub_sprint_issues,
                    sub_sprint_changelog,
                    sub_issues,
                    sub_status_changelog,
                    done_ids,
                    sub_field_values,
                    sp_field_key_id,
                )
                if not unest.is_empty():
                    results.append(
                        unest.select(
                            [
                                "project_id",
                                pl.col("start_date").alias("time_date"),
                                pl.col("unestimated_count").alias("value"),
                                pl.lit("sprint").alias("entity_type"),
                                pl.col("iteration_id").alias("entity_id"),
                                pl.lit(calc_id_unestimated).alias("calc_id"),
                            ]
                        )
                    )

        # E. Field Value Pct
        settings_df = read_table(
            engine,
            "SELECT * FROM metrics.calculation_settings WHERE target_calculation_id = :cid AND enabled = true",
            params={"cid": calc_id_field_pct},
        )
        for setting in settings_df.to_dicts():
            f_name, f_val, tp_id = (
                setting["settings_json"].get("field_name"),
                setting["settings_json"].get("field_value"),
                setting["project_id"],
            )
            if not f_name or not f_val:
                continue
            ss_sprints = (
                sub_sprints.filter(pl.col("project_id") == tp_id)
                if tp_id
                else sub_sprints
            )
            if ss_sprints.is_empty():
                continue
            field_pct = sprint_health_logic.calculate_field_value_sprint_pct(
                ss_sprints,
                sub_sprint_issues,
                sub_issues,
                f_name,
                f_val,
                sub_field_values,
                field_keys_df,
            )
            if not field_pct.is_empty():
                results.append(
                    field_pct.select(
                        [
                            "project_id",
                            pl.col("start_date").alias("time_date"),
                            pl.col("field_pct").alias("value"),
                            pl.lit("sprint").alias("entity_type"),
                            pl.col("iteration_id").alias("entity_id"),
                            pl.lit(calc_id_field_pct).alias("calc_id"),
                            pl.lit(setting["id"]).alias("settings_id"),
                        ]
                    )
                )
        return results

    def transform_to_fact_values(
        wide_results, slice_rule_id=None, slice_value_col=None
    ):
        facts_list = []
        for df_wide in wide_results:
            facts = df_wide.with_columns(
                [
                    pl.col("calc_id").alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("time_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
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
                        pl.col("settings_id")
                        if "settings_id" in facts.columns
                        else pl.lit(None).cast(pl.Utf8).alias("settings_id"),
                    ]
                )
            )
        return facts_list

    # 3. BASE calculation
    base_wide_list = calculate_base_facts(
        issues_df,
        sprint_issues_df,
        sprint_changelog_df,
        issue_status_changelog_df,
        field_values_df,
        field_value_changelog_df,
    )
    all_facts = transform_to_fact_values(base_wide_list)

    # 4. Sliced calculation
    rules_df = get_slice_rules(engine, target_definition_id=def_id)
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def sprint_health_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_si = sprint_issues_df.filter(pl.col("issue_id").is_in(subset_ids))
        sub_sc = sprint_changelog_df.filter(pl.col("issue_id").is_in(subset_ids))
        sub_st = issue_status_changelog_df.filter(pl.col("issue_id").is_in(subset_ids))
        sub_fv = field_values_df.filter(pl.col("issue_id").is_in(subset_ids))
        sub_fc = field_value_changelog_df.filter(pl.col("issue_id").is_in(subset_ids))

        res_list = calculate_base_facts(
            df_subset, sub_si, sub_sc, sub_st, sub_fv, sub_fc
        )
        if not res_list:
            return pl.DataFrame()
        return pl.concat(res_list, how="diagonal_relaxed")

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                sprint_health_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                for cid in sliced_wide["calc_id"].unique().to_list():
                    sub_sliced = sliced_wide.filter(pl.col("calc_id") == cid)
                    facts = sub_sliced.with_columns(
                        [
                            pl.col("calc_id").alias("metric_id"),
                            pl.col("project_id")
                            .replace(project_agg_map)
                            .alias("project_agg_id"),
                            pl.col("time_date")
                            .dt.strftime("%Y%m%d")
                            .cast(pl.Int32)
                            .alias("time_id"),
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
                            pl.col("settings_id")
                            if "settings_id" in sub_sliced.columns
                            else pl.lit(None).cast(pl.Utf8).alias("settings_id"),
                        ]
                    )
                    all_facts.append(facts)

    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(all_facts, how="diagonal_relaxed")

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

    return {
        "status": "success",
        "rows_written": rows_written,
        "metrics_calculated": len(metric_ids),
    }


@asset_check(asset=calculate_sprint_health)
def sprint_health_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_codes = [
        "sprint_added_issues_count",
        "sprint_added_sp_sum",
        "sprint_removed_issues_count",
        "sprint_removed_sp_sum",
        "sprint_spillover_count",
        "sprint_burndown_remaining_sp",
    ]
    for code in calc_codes:
        calc_id = get_calculation_id(engine, code)
        df = read_table(
            engine,
            "SELECT COUNT(*) as cnt FROM metrics.fact_values WHERE metric_id = :calc_id AND value < 0",
            params={"calc_id": calc_id},
        )
        if not df.is_empty() and df[0, "cnt"] > 0:
            return AssetCheckResult(
                passed=False, metadata={"error": f"Negative values found for {code}"}
            )
    return AssetCheckResult(passed=True)
