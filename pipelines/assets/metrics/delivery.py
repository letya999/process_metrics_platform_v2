import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import delivery as delivery_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    load_commitment_rules_for_calc,
    resolve_rule_from_cache,
)
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_status_changelog",
        "clean_jira_field_values",
        "clean_jira_field_keys",
        "clean_jira_field_value_changelog",
        "clean_jira_boards",
        "clean_jira_board_columns",
    ],
    description="Calculate Delivery metrics",
    compute_kind="python",
)
def calculate_delivery_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()

    # 1. Load Data
    issues_df = read_table(
        engine,
        "SELECT id, project_id, jira_created_at as created_at FROM clean_jira.issues",
    )
    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    issue_status_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.issue_status_changelog"
    )
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
    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
    """,
    )
    boards_df = read_table(engine, "SELECT * FROM clean_jira.boards")

    # Release scope: map issues to release/version names via release_issues + releases.
    fix_versions_df = read_table(
        engine,
        """
        SELECT ri.issue_id, r.name as version_name
        FROM clean_jira.release_issues ri
        JOIN clean_jira.releases r ON r.id = ri.release_id
    """,
    )

    # 2. Resolve IDs
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    calc_id_scope = get_calculation_id(engine, "release_burnup_scope_sp")
    calc_id_done = get_calculation_id(engine, "release_burnup_done_sp")

    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    all_facts = []

    # 3. Calculation per project
    for board in boards_df.to_dicts():
        p_id = board["project_id"]
        b_id = board["id"]

        board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
        rule = resolve_rule_from_cache(lead_time_rules, p_id, b_id)

        if not rule or board_cols.is_empty():
            continue

        points = identify_commitment_points_from_rule(rule, board_cols)
        done_status_ids = points.get("end_status_ids", [])

        if not done_status_ids:
            continue

        burnup = delivery_logic.calculate_release_burnup(
            issues_df.filter(pl.col("project_id") == p_id),
            issue_status_changelog_df,
            done_status_ids,
            field_values_df,
            field_keys_df,
            field_value_changelog_df,
            fix_versions_df,
        )

        if not burnup.is_empty():
            # Scope facts
            facts_scope = burnup.select(
                [
                    pl.lit(calc_id_scope).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("time_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("scope_sp").alias("value"),
                    pl.lit("version").alias("entity_type"),
                    pl.col("version_name").alias("entity_id"),
                ]
            )
            all_facts.append(facts_scope)

            # Done facts
            facts_done = burnup.select(
                [
                    pl.lit(calc_id_done).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("time_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("done_sp").alias("value"),
                    pl.lit("version").alias("entity_type"),
                    pl.col("version_name").alias("entity_id"),
                ]
            )
            all_facts.append(facts_done)

    # 4. Write to DB
    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(all_facts)

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


@asset_check(asset=calculate_delivery_metrics)
def delivery_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "release_burnup_scope_sp")
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
