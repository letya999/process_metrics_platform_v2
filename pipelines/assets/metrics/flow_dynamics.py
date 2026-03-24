"""
Flow Dynamics Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import flow_dynamics as flow_dynamics_logic
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
        "clean_jira_issue_status_changelog",
        "clean_jira_field_value_changelog",
        "clean_jira_field_keys",
        "clean_jira_issues",
        "clean_jira_issue_types",
    ],
    description="Calculate Flow Dynamics metrics",
    compute_kind="python",
)
def calculate_flow_dynamics(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "flow_dynamics")
    calc_id_status_entry = get_calculation_id(engine, "daily_status_entry_count")
    calc_id_field_change = get_calculation_id(engine, "field_change_count")

    context.log.info("Loading data for Flow Dynamics metrics...")

    # Load Data
    sprints_df = read_table(
        engine,
        "SELECT * FROM clean_jira.sprints WHERE status IN ('closed', 'active') AND start_date IS NOT NULL",
    )
    if sprints_df.is_empty():
        return {"status": "skipped", "reason": "No sprints found"}

    sprint_issues_df = read_table(engine, "SELECT * FROM clean_jira.sprint_issues")
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

    # Need issues for slicing
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, it.name as type_name
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    # Map project_agg_ids
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # 2. Calculation functions
    def calculate_base_facts(
        sub_sprint_issues, sub_status_changelog, sub_field_changelog
    ):
        results = []

        # A. Daily Status Entry (Parameterized)
        settings_entry = read_table(
            engine,
            "SELECT * FROM metrics.calculation_settings WHERE target_calculation_id = :calc_id AND enabled = true",
            params={"calc_id": calc_id_status_entry},
        )

        if not settings_entry.is_empty():
            for setting in settings_entry.to_dicts():
                target_status = setting["settings_json"].get("target_status")
                if not target_status:
                    continue
                p_id = setting["project_id"]
                s_subset = sprints_df
                if p_id:
                    s_subset = sprints_df.filter(pl.col("project_id") == p_id)
                if s_subset.is_empty():
                    continue

                daily_entry = flow_dynamics_logic.calculate_daily_status_entry(
                    s_subset, sub_sprint_issues, sub_status_changelog, target_status
                )
                if not daily_entry.is_empty():
                    results.append(
                        daily_entry.with_columns(
                            [
                                pl.lit(calc_id_status_entry).alias("calc_id"),
                                pl.lit(setting["id"]).alias("settings_id"),
                            ]
                        )
                    )

        # B. Field Change Count (Parameterized)
        settings_change = read_table(
            engine,
            "SELECT * FROM metrics.calculation_settings WHERE target_calculation_id = :calc_id AND enabled = true",
            params={"calc_id": calc_id_field_change},
        )

        if not settings_change.is_empty():
            for setting in settings_change.to_dicts():
                field_key_id = setting["settings_json"].get("field_key_id")
                if not field_key_id:
                    continue
                p_id = setting["project_id"]
                s_subset = sprints_df
                if p_id:
                    s_subset = sprints_df.filter(pl.col("project_id") == p_id)
                if s_subset.is_empty():
                    continue

                field_changes = flow_dynamics_logic.calculate_field_change_count(
                    s_subset, sub_sprint_issues, sub_field_changelog, field_key_id
                )
                if not field_changes.is_empty():
                    results.append(
                        field_changes.with_columns(
                            [
                                pl.lit(calc_id_field_change).alias("calc_id"),
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
            cid = df_wide["calc_id"][0]
            val_col = "entry_count" if cid == calc_id_status_entry else "change_count"
            time_col = "time_date" if cid == calc_id_status_entry else "start_date"

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
                    pl.lit("sprint").alias("entity_type"),
                    pl.col("iteration_id").alias("entity_id"),
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
                        "settings_id",
                    ]
                )
            )
        return facts_list

    # 3. BASE calculation
    base_wide_list = calculate_base_facts(
        sprint_issues_df, issue_status_changelog_df, field_value_changelog_df
    )
    all_facts = transform_to_fact_values(base_wide_list)

    # 4. Sliced calculation
    rules_df = get_slice_rules(engine, target_definition_id=def_id)
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def flow_dynamics_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_sprint_issues = sprint_issues_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        sub_status_changelog = issue_status_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        sub_field_changelog = field_value_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )

        res_list = calculate_base_facts(
            sub_sprint_issues, sub_status_changelog, sub_field_changelog
        )
        if not res_list:
            return pl.DataFrame()

        for i, df in enumerate(res_list):
            cid = df["calc_id"][0]
            val_col = "entry_count" if cid == calc_id_status_entry else "change_count"
            time_col = "time_date" if cid == calc_id_status_entry else "start_date"
            res_list[i] = df.rename({val_col: "value", time_col: "time_id_src"})
        return pl.concat(res_list, how="diagonal_relaxed")

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                flow_dynamics_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                for cid in [calc_id_status_entry, calc_id_field_change]:
                    sub_sliced = sliced_wide.filter(pl.col("calc_id") == cid)
                    if not sub_sliced.is_empty():
                        time_col = "time_id_src"
                        facts = sub_sliced.with_columns(
                            [
                                pl.lit(cid).alias("metric_id"),
                                pl.col("project_id")
                                .replace(project_agg_map)
                                .alias("project_agg_id"),
                                pl.col(time_col)
                                .dt.strftime("%Y%m%d")
                                .cast(pl.Int32)
                                .alias("time_id"),
                                pl.col("value").alias("value"),
                                pl.lit("sprint").alias("entity_type"),
                                pl.col("iteration_id").alias("entity_id"),
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
                                "settings_id",
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


@asset_check(asset=calculate_flow_dynamics)
def flow_dynamics_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "daily_status_entry_count")
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
