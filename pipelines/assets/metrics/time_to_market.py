"""
Time to Market Metrics Dagster Asset (Generic Long Metric Store)
TTM is now calculated using the same logic as Lead Time, but filtered by issue type.
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import lead_time as lead_time_logic
from pipelines.calculations import time_to_market as ttm_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    identify_commitment_points_heuristic,
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


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Time to Market facts and write to generic fact_values",
    compute_kind="python",
)
def calculate_time_to_market(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()
    def_id = get_definition_id(engine, "ttm")
    calc_id = get_calculation_id(engine, "ttm_days")

    # 1. Load issues with type info
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

    project_agg_map = {
        pid: get_project_agg_id(engine, pid) for pid in issues_df["project_id"].unique()
    }

    # 2. Load changelog, boards, board_columns
    status_changelog_df = read_table(
        engine,
        "SELECT issue_id, from_status_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
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

    # 3. Load commitment rules for ttm_days; fall back to lead_time_days rules
    ttm_rules = load_commitment_rules_for_calc(engine, "ttm_days")
    if not ttm_rules:
        ttm_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    # 4. For each board, apply type filter and calculate lead time
    all_ttm = []

    # Cache for issue type filters per project
    type_filter_cache = {}

    for board in boards_df.to_dicts():
        b_id = board["id"]
        p_id = board["project_id"]

        # Project-specific type filter (may differ per project)
        if p_id not in type_filter_cache:
            type_filter_cache[p_id] = ttm_logic.load_issue_type_filter(
                engine, "ttm_days", project_id=p_id
            )

        type_filter = type_filter_cache[p_id]

        # Resolve commitment points
        rule = resolve_rule_from_cache(ttm_rules, p_id, b_id)
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

        # Filter issues: project AND type
        project_issues = issues_df.filter(
            (pl.col("project_id") == p_id) & (pl.col("type_name").is_in(type_filter))
        )
        if project_issues.is_empty():
            continue

        # Calculate using the SAME function as lead_time
        ttm_df = lead_time_logic.calculate_lead_time_per_issue(
            project_issues,
            status_changelog_df,
            points["middle_status_ids"],
            points["end_status_ids"],
        )

        if not ttm_df.is_empty():
            ttm_df = ttm_df.with_columns(
                pl.lit(points.get("commitment_rule_id"))
                .cast(pl.Utf8)
                .alias("commitment_rule_id")
            )
            all_ttm.append(ttm_df)

    if not all_ttm:
        return {"status": "no_data"}

    ttm_wide = pl.concat(all_ttm).unique(subset=["issue_id"])

    # 5. Transform to fact_values
    def transform_to_fact_values(
        df_wide, slice_rule_id=None, slice_value_col=None, slice_value=None
    ):
        if df_wide.is_empty():
            return pl.DataFrame()

        facts = df_wide.with_columns(
            [
                pl.lit(calc_id).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # completion_end_at -> time_id (YYYYMMDD)
                pl.col("commitment_end_at")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.col("lead_time_days").alias("value"),
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
                pl.col("commitment_start_at")
                .cast(pl.Datetime("us", "UTC"))
                .alias("event_start_at"),
                pl.col("commitment_end_at")
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

    # 6. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    # For slicing, we need the original issues attributes (like type_name alias as issue_type)
    # But since ttm_wide already has it as issue_type (from lead_time_logic), we can reuse it.

    def ttm_slice_calc(df_subset):
        subset_ids = df_subset["id"].unique().to_list()
        return ttm_wide.filter(pl.col("issue_id").is_in(subset_ids))

    all_facts = [base_facts]

    if not rules_df.is_empty():
        # Slicing source: issues filtered by TTM type filter
        # (we only slice issues that ARE considered TTM)
        ttm_issue_ids = ttm_wide["issue_id"].unique().to_list()
        issues_for_slicing = issues_df.filter(
            pl.col("id").is_in(ttm_issue_ids)
        ).with_columns(pl.col("type_name").alias("issue_type"))

        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                ttm_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                facts = transform_to_fact_values(
                    sliced_wide, slice_rule_id=rule_id, slice_value_col="slice_value"
                )
                all_facts.append(facts)

    final_df = pl.concat(all_facts)

    # 7. Write to DB
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
