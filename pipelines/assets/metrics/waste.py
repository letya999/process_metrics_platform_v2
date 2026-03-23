"""
Waste Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import waste as waste_logic
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
        "clean_jira_issue_statuses",
    ],
    description="Calculate Waste metrics",
    compute_kind="python",
)
def calculate_waste_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "waste")
    calc_id_waste = get_calculation_id(engine, "cancellation_rate_weekly")

    context.log.info("Loading data for Waste metrics...")

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
    issue_statuses_df = read_table(
        engine, "SELECT id, name FROM clean_jira.issue_statuses"
    )

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # Load settings
    settings_df = read_table(
        engine,
        "SELECT * FROM metrics.calculation_settings WHERE target_calculation_id = :calc_id AND enabled = true",
        params={"calc_id": calc_id_waste},
    )

    # 2. Calculation functions
    def calculate_base_facts(df_subset, sub_status_changelog):
        results = []
        p_ids = df_subset["project_id"].unique().to_list()

        for p_id in p_ids:
            p_setting = settings_df.filter(pl.col("project_id") == p_id)
            if p_setting.is_empty():
                p_setting = settings_df.filter(pl.col("project_id").is_null())

            cancelled_ids = []
            if not p_setting.is_empty():
                cancelled_ids = p_setting[0, "settings_json"].get(
                    "cancelled_status_ids", []
                )

            if not cancelled_ids:
                cancelled_ids = issue_statuses_df.filter(
                    pl.col("name")
                    .str.to_lowercase()
                    .str.contains(r"cancel|reject|won't fix|duplicate")
                )["id"].to_list()

            if not cancelled_ids:
                continue

            waste = waste_logic.calculate_cancellation_rate_weekly(
                sub_status_changelog,
                cancelled_ids,
                df_subset.filter(pl.col("project_id") == p_id),
            )

            if not waste.is_empty():
                results.append(waste)
        return results

    def transform_to_fact_values(
        wide_results, slice_rule_id=None, slice_value_col=None
    ):
        facts_list = []
        for df_wide in wide_results:
            facts = df_wide.with_columns(
                [
                    pl.lit(calc_id_waste).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("iso_week_start_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("cancellation_count").alias("value"),
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

    def waste_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_status_changelog = issue_status_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        res_list = calculate_base_facts(df_subset, sub_status_changelog)
        if not res_list:
            return pl.DataFrame()

        for i, df in enumerate(res_list):
            df.rename(
                {"cancellation_count": "value", "iso_week_start_date": "time_id_src"},
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
                waste_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                facts = sliced_wide.with_columns(
                    [
                        pl.lit(calc_id_waste).alias("metric_id"),
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


@asset_check(asset=calculate_waste_metrics)
def waste_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "cancellation_rate_weekly")
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
