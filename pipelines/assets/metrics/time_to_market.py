"""
Time to Market Metrics Dagster Asset (Generic Long Metric Store)
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import time_to_market as ttm_logic
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
)
from pipelines.utils.polars_db import read_table, write_fact_values


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_releases",
        "clean_jira_release_issues",
        "clean_jira_issue_status_changelog",
        "clean_jira_board_columns",
    ],
    description="Calculate Time to Market facts and write to generic fact_values",
    compute_kind="python",
)
def calculate_time_to_market(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "ttm")
    calc_id = get_calculation_id(engine, "ttm_days")

    context.log.info("Loading data from clean_jira schema...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, i.type_id,
               i.jira_created_at, i.jira_resolved_at, p.external_key AS project_key
        FROM clean_jira.issues i
        JOIN clean_jira.projects p ON i.project_id = p.id
        """,
    )

    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    issue_types_df = read_table(
        engine, "SELECT id, name, hierarchy_level FROM clean_jira.issue_types"
    )

    releases_df = read_table(
        engine,
        "SELECT id, project_id, name, release_date, is_released FROM clean_jira.releases",
    )

    issue_fix_versions_df = read_table(
        engine,
        "SELECT issue_id, release_id AS version_id FROM clean_jira.release_issues WHERE is_active = true",
    )

    status_changelog_df = read_table(
        engine,
        "SELECT issue_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
    )

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bc.position, bcs.status_id
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    # 2. Calculate BASE TTM facts
    ttm_wide = ttm_logic.calculate_time_to_market(
        issues_df=issues_df,
        issue_types_df=issue_types_df,
        releases_df=releases_df,
        issue_fix_versions_df=issue_fix_versions_df,
        status_changelog_df=status_changelog_df,
        board_columns_df=board_columns_df,
    )

    if ttm_wide.is_empty():
        return {"status": "no_data"}

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(
        df_wide, slice_rule_id=None, slice_value_col=None, slice_value=None
    ):
        if df_wide.is_empty():
            return pl.DataFrame()

        facts = df_wide.with_columns(
            [
                pl.lit(calc_id).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # release date -> time_id (YYYYMMDD)
                pl.col("released_at")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.col("time_to_market_days").alias("value"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_key").cast(pl.Utf8).alias("entity_id"),
                pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                if slice_value_col
                else (
                    pl.lit(slice_value).cast(pl.Utf8).alias("slice_value")
                    if slice_value is not None
                    else pl.lit(None).cast(pl.Utf8).alias("slice_value")
                ),
                pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                pl.col("jira_created_at")
                .cast(pl.Datetime("us", "UTC"))
                .alias("event_start_at"),
                pl.col("released_at")
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

    base_facts = transform_to_fact_values(ttm_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]

            # Use ttm_wide as source for slicing (no expensive recalculation needed).
            def ttm_slice_identity(df_subset):
                return df_subset

            sliced_wide = apply_slicing(
                ttm_wide,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                ttm_slice_identity,
            )

            if not sliced_wide.is_empty():
                facts = transform_to_fact_values(
                    sliced_wide, slice_rule_id=rule_id, slice_value_col="slice_value"
                )
                all_facts.append(facts)

    final_df = pl.concat(all_facts)

    # 5. Write to DB
    if final_df.is_empty():
        return {"status": "no_data"}

    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()
    project_agg_ids = list(project_agg_map.values())

    rows_written = write_fact_values(
        final_df,
        engine,
        metric_ids=[calc_id],
        project_agg_ids=project_agg_ids,
        time_id_start=time_id_start,
        time_id_end=time_id_end,
    )

    return {
        "status": "success",
        "rows_written": rows_written,
        "issues_processed": len(ttm_wide),
        "metric_ids": [calc_id],
    }


@asset_check(asset=calculate_time_to_market)
def ttm_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "ttm_days")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
