"""
Lead Time Metrics Dagster Asset (Generic Long Metric Store)
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import lead_time as lead_time_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    identify_commitment_points_heuristic,
    resolve_commitment_columns,
)
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
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Lead Time facts and write to generic fact_values",
    compute_kind="python",
)
def calculate_lead_time(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "lead_time")
    calc_id = get_calculation_id(engine, "lead_time_days")

    context.log.info("Loading data from clean_jira schema...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.jira_created_at, i.jira_resolved_at, p.project_key
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

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    # 2. Calculate BASE lead time facts
    # Lead time is board-specific. We need to iterate over boards or projects.
    all_lead_times = []

    for board in boards_df.to_dicts():
        b_id = board["id"]
        p_id = board["project_id"]

        # Resolve commitment columns for this board
        rule = resolve_commitment_columns(engine, p_id, b_id, "lead_time_days")
        if rule:
            points = identify_commitment_points_from_rule(
                rule, board_columns_df.filter(pl.col("board_id") == b_id)
            )
        else:
            points = identify_commitment_points_heuristic(
                board_columns_df.filter(pl.col("board_id") == b_id)
            )

        if not points["middle_status_ids"] or not points["end_status_ids"]:
            continue

        # Calculate for issues in this project
        project_issues = issues_df.filter(pl.col("project_id") == p_id)
        if project_issues.is_empty():
            continue

        lt_df = lead_time_logic.calculate_lead_time_per_issue(
            project_issues,
            status_changelog_df,
            points["middle_status_ids"],
            points["end_status_ids"],
        )

        if not lt_df.is_empty():
            # Add commitment_rule_id to result
            lt_df = lt_df.with_columns(
                pl.lit(points.get("commitment_rule_id")).alias("commitment_rule_id")
            )
            all_lead_times.append(lt_df)

    if not all_lead_times:
        return {"status": "no_data"}

    base_lt_wide = pl.concat(all_lead_times).unique(subset=["issue_id"])

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(df_wide, slice_rule_id=None, slice_value_col=None):
        facts = df_wide.with_columns(
            [
                pl.lit(calc_id).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # completion date -> time_id (YYYYMMDD)
                pl.col("commitment_end_at")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.col("lead_time_days").alias("value"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_key").alias("entity_id"),
                pl.lit(slice_rule_id).alias("slice_rule_id"),
                pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                if slice_value_col
                else pl.lit(None).alias("slice_value"),
                pl.col("commitment_rule_id").cast(pl.Utf8).alias("commitment_rule_id"),
                pl.col("commitment_start_at").alias("event_start_at"),
                pl.col("commitment_end_at").alias("event_end_at"),
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

    base_facts = transform_to_fact_values(base_lt_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    # Heuristic for default rules: alias type_name
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def lead_time_slice_calc(df_subset):
        # We need to re-run the board-specific logic but only for the subset of issues
        # Actually, we can just filter the base_lt_wide if it contains issue_id
        # But apply_slicing expects a function that takes a subset of the source (issues)
        subset_ids = df_subset["id"].unique().to_list()
        return base_lt_wide.filter(pl.col("issue_id").is_in(subset_ids))

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                lead_time_slice_calc,
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
        metric_ids=[calc_id],
        project_agg_ids=project_agg_ids,
        time_id_start=time_id_start,
        time_id_end=time_id_end,
    )

    return {
        "status": "success",
        "rows_written": rows_written,
        "issues_processed": len(base_lt_wide),
    }


@asset_check(asset=calculate_lead_time)
def lead_time_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "lead_time_days")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
