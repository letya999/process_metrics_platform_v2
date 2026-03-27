"""
Estimation Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from datetime import date
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import estimation as estimation_logic
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
    resolve_unit_field,
)
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_field_value_changelog",
        "clean_jira_field_values",
        "clean_jira_field_keys",
    ],
    description="Calculate Estimation metrics",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="python",
)
def calculate_estimation_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()
    today_id = int(date.today().strftime("%Y%m%d"))

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "estimation")
    calc_id_volatility = get_calculation_id(engine, "estimate_volatility_abs")

    context.log.info("Loading data for Estimation metrics...")

    # Load Data
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key as issue_key, it.name as type_name
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )
    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    field_keys_df = read_table(engine, "SELECT * FROM clean_jira.field_keys")
    field_values_df = read_table(
        engine,
        "SELECT issue_id, field_key_id, json_value::text as json_value FROM clean_jira.field_values",
    )
    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id, old_value::text as old_value, new_value::text as new_value, changed_at as change_time
        FROM clean_jira.field_value_changelog
    """,
    )

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # Try metrics.units unit binding first, fall back to heuristic.
    sp_field_key_id: str | None = None

    # Use first project as representative for global binding lookup
    _sample_pid = project_ids[0] if project_ids else None
    if _sample_pid:
        unit_info = resolve_unit_field(engine, _sample_pid, "story_points")
        if unit_info and unit_info.get("source_field_id"):
            sp_field_key_id = str(unit_info["source_field_id"])
            context.log.info(
                "story_points field resolved from metrics.units: %s", sp_field_key_id
            )

    if not sp_field_key_id:
        # Fallback to heuristic
        sp_fields = field_keys_df.filter(
            (
                pl.col("external_key").is_in(
                    ["customfield_10036", "customfield_10016", "story_points"]
                )
            )
            | (pl.col("name").str.to_lowercase().str.contains("story point"))
        )
        sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None
        if sp_field_key_id:
            context.log.info(
                "story_points field resolved via heuristic: %s", sp_field_key_id
            )

    if not sp_field_key_id:
        return {"status": "skipped", "reason": "No Story Points field found"}

    # 2. Transform function
    def transform_to_fact_values(
        df_wide, slice_rule_id=None, slice_value_col=None, slice_value=None
    ):
        if df_wide.is_empty():
            return pl.DataFrame()

        facts = df_wide.with_columns(
            [
                pl.lit(calc_id_volatility).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                pl.lit(today_id).cast(pl.Int32).alias("time_id"),
                pl.col("volatility").alias("value"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_id").alias("entity_id"),
                pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                (
                    pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                    if slice_value_col
                    else (
                        pl.lit(slice_value).cast(pl.Utf8).alias("slice_value")
                        if slice_value is not None
                        else pl.lit(None).cast(pl.Utf8).alias("slice_value")
                    )
                ),
                pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_start_at"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_end_at"),
            ]
        )

        return facts.select(
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

    # 3. BASE calculation
    volatility_wide = estimation_logic.calculate_estimate_volatility(
        issues_df, field_value_changelog_df, field_values_df, sp_field_key_id
    )
    base_facts = transform_to_fact_values(volatility_wide)

    # 4. Sliced calculation
    rules_df = get_slice_rules(engine, target_definition_id=def_id)
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def estimation_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        sub_field_values = field_values_df.filter(pl.col("issue_id").is_in(subset_ids))
        sub_field_changelog = field_value_changelog_df.filter(
            pl.col("issue_id").is_in(subset_ids)
        )
        return estimation_logic.calculate_estimate_volatility(
            df_subset, sub_field_changelog, sub_field_values, sp_field_key_id
        )

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                estimation_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                facts = transform_to_fact_values(
                    sliced_wide, slice_rule_id=rule_id, slice_value_col="slice_value"
                )
                all_facts.append(facts)

    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(all_facts)

    # 5. Write to DB
    rows_written = write_fact_values(
        final_df,
        engine,
        metric_ids=[calc_id_volatility],
        project_agg_ids=list(project_agg_map.values()),
        time_id_start=today_id,
        time_id_end=today_id,
    )

    return {"status": "success", "rows_written": rows_written}


@asset_check(asset=calculate_estimation_metrics)
def estimation_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "estimate_volatility_abs")
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
