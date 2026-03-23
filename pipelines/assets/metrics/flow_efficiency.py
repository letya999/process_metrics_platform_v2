"""
Flow Efficiency Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import flow_efficiency as flow_logic
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
        "clean_jira_issue_types",
        "clean_jira_issue_statuses",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Flow Efficiency facts and write to generic fact_values",
    compute_kind="python",
)
def calculate_flow_efficiency(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "flow_efficiency")
    flow_map = {
        "active_days": get_calculation_id(engine, "flow_active_days"),
        "wait_days": get_calculation_id(engine, "flow_wait_days"),
        "efficiency_pct": get_calculation_id(engine, "flow_efficiency_pct"),
    }
    metric_ids = list(flow_map.values())

    context.log.info("Loading data for Flow Efficiency metrics...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.status_id, i.jira_created_at, p.external_key AS project_key
        FROM clean_jira.issues i
        JOIN clean_jira.projects p ON i.project_id = p.id
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    status_changelog_df = read_table(
        engine,
        "SELECT issue_id, from_status_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
    )

    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )

    # Resolve status types
    active_statuses = issue_statuses_df.filter(pl.col("category") == "indeterminate")[
        "id"
    ].to_list()
    wait_statuses = issue_statuses_df.filter(pl.col("category") == "todo")[
        "id"
    ].to_list()
    end_statuses = issue_statuses_df.filter(pl.col("category") == "done")[
        "id"
    ].to_list()

    # 2. Calculate BASE Flow Efficiency facts
    flow_wide = flow_logic.calculate_flow_efficiency_per_issue(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        active_status_ids=active_statuses,
        wait_status_ids=wait_statuses,
        end_status_ids=end_statuses,
    )

    if flow_wide.is_empty():
        return {"status": "no_data"}

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(
        df_wide, slice_rule_id=None, slice_value_col=None, slice_value=None
    ):
        if df_wide.is_empty():
            return pl.DataFrame()

        melted_flow = df_wide.melt(
            id_vars=["project_id", "issue_key", "completion_date"]
            + ([slice_value_col] if slice_value_col else []),
            value_vars=["active_days", "wait_days", "efficiency_pct"],
            variable_name="calc_source",
            value_name="value",
        )

        facts = melted_flow.with_columns(
            [
                pl.col("calc_source").replace(flow_map).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # completion date -> time_id (YYYYMMDD)
                pl.col("completion_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_key").alias("entity_id"),
                pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                if slice_value_col
                else (
                    pl.lit(slice_value).cast(pl.Utf8).alias("slice_value")
                    if slice_value is not None
                    else pl.lit(None).cast(pl.Utf8).alias("slice_value")
                ),
                pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_start_at"),
                pl.col("completion_date")
                .cast(pl.Datetime("us", "UTC"))
                .alias("event_end_at"),
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
        ).drop_nulls(subset=["value"])

    base_facts = transform_to_fact_values(flow_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    # Slicing source: use type_name alias for default rule compatibility
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def flow_slice_calc(df_subset):
        # Filter status_changelog for only these issues
        subset_ids = df_subset["id"].unique().to_list()
        sub_changelog = status_changelog_df.filter(pl.col("issue_id").is_in(subset_ids))

        return flow_logic.calculate_flow_efficiency_per_issue(
            issues_df=df_subset,
            status_changelog_df=sub_changelog,
            active_status_ids=active_statuses,
            wait_status_ids=wait_statuses,
            end_status_ids=end_statuses,
        )

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                flow_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                facts = transform_to_fact_values(
                    sliced_wide, slice_rule_id=rule_id, slice_value_col="slice_value"
                )
                all_facts.append(facts)

    final_df = pl.concat(all_facts)

    # 5. Write to DB
    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()
    project_agg_ids = list(project_agg_map.values())

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
        "issues_processed": len(flow_wide),
        "metric_ids": metric_ids,
    }


@asset_check(asset=calculate_flow_efficiency)
def flow_efficiency_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "flow_efficiency_pct")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
