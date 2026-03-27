"""
Throughput Metrics Dagster Asset (Generic Long Metric Store)
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import throughput as throughput_logic
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
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Throughput facts and write to generic fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="python",
)
def calculate_throughput(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "throughput")
    calc_id = get_calculation_id(engine, "throughput_count")

    context.log.info("Loading data from clean_jira schema...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.jira_created_at, i.jira_resolved_at, p.external_key AS project_key
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
        "SELECT issue_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
    )

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bc.position, bcs.status_id
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    # 2. Calculate BASE throughput facts
    throughput_wide = throughput_logic.calculate_weekly_throughput(
        issues_df=issues_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
    )

    if throughput_wide.is_empty():
        return {"status": "no_data"}

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(df_wide, slice_rule_id=None, slice_value=None):
        if df_wide.is_empty():
            return pl.DataFrame()

        facts = df_wide.with_columns(
            [
                pl.lit(calc_id).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # week_start_date -> time_id (YYYYMMDD)
                pl.col("week_start_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.col("issues_completed").alias("value"),
                pl.lit("week").alias("entity_type"),
                pl.col("week_start_date").dt.strftime("%Y-%m-%d").alias("entity_id"),
                pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                (
                    pl.lit(slice_value).cast(pl.Utf8).alias("slice_value")
                    if slice_value is not None
                    else pl.lit(None).cast(pl.Utf8).alias("slice_value")
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
        ).drop_nulls(subset=["value"])

    base_facts = transform_to_fact_values(throughput_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def throughput_slice_calc(df_subset):
        return throughput_logic.calculate_generic_throughput(
            issues_df=df_subset,
            status_changelog_df=status_changelog_df,
            boards_df=boards_df,
            board_columns_df=board_columns_df,
            group_by=["issue_type"],
        )

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                throughput_slice_calc,
                engine=engine,
            )

            if sliced_wide.is_empty():
                continue

            if "slice_value" in sliced_wide.columns:
                groups = sliced_wide.partition_by(["slice_value"])
                for group_df in groups:
                    slice_val = group_df["slice_value"][0]
                    filtered_group = group_df.filter(pl.col("issues_completed") > 0)
                    if not filtered_group.is_empty():
                        facts = transform_to_fact_values(
                            filtered_group,
                            slice_rule_id=rule_id,
                            slice_value=str(slice_val),
                        )
                        all_facts.append(facts)
            else:
                filtered_group = sliced_wide.filter(pl.col("issues_completed") > 0)
                if not filtered_group.is_empty():
                    facts = transform_to_fact_values(
                        filtered_group,
                        slice_rule_id=rule_id,
                        slice_value=None,
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
        "weeks_processed": len(throughput_wide["week_start_date"].unique()),
        "metric_ids": [calc_id],
    }


@asset_check(asset=calculate_throughput)
def throughput_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "throughput_count")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
