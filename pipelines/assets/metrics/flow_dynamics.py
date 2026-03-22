import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import flow_dynamics as flow_dynamics_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
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
    ],
    description="Calculate Flow Dynamics metrics",
    compute_kind="python",
)
def calculate_flow_dynamics(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()

    # 1. Load Data
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

    # 2. Resolve IDs
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    all_facts = []

    # A. Daily Status Entry (Parameterized)
    calc_id_status_entry = get_calculation_id(engine, "daily_status_entry_count")
    settings_entry = read_table(
        engine,
        """
        SELECT * FROM metrics.calculation_settings
        WHERE target_calculation_id = :calc_id AND enabled = true
    """,
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
                s_subset, sprint_issues_df, issue_status_changelog_df, target_status
            )

            if not daily_entry.is_empty():
                facts_entry = daily_entry.select(
                    [
                        pl.lit(calc_id_status_entry).alias("metric_id"),
                        pl.col("project_id")
                        .replace(project_agg_map)
                        .alias("project_agg_id"),
                        pl.col("time_date")
                        .dt.strftime("%Y%m%d")
                        .cast(pl.Int32)
                        .alias("time_id"),
                        pl.col("entry_count").alias("value"),
                        pl.lit("sprint").alias("entity_type"),
                        pl.col("iteration_id").alias("entity_id"),
                        pl.lit(setting["id"]).alias("settings_id"),
                    ]
                )
                all_facts.append(facts_entry)

    # B. Field Change Count (Parameterized)
    calc_id_field_change = get_calculation_id(engine, "field_change_count")
    settings_change = read_table(
        engine,
        """
        SELECT * FROM metrics.calculation_settings
        WHERE target_calculation_id = :calc_id AND enabled = true
    """,
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
                s_subset, sprint_issues_df, field_value_changelog_df, field_key_id
            )

            if not field_changes.is_empty():
                facts_change = field_changes.select(
                    [
                        pl.lit(calc_id_field_change).alias("metric_id"),
                        pl.col("project_id")
                        .replace(project_agg_map)
                        .alias("project_agg_id"),
                        pl.col("start_date")
                        .dt.strftime("%Y%m%d")
                        .cast(pl.Int32)
                        .alias("time_id"),
                        pl.col("change_count").alias("value"),
                        pl.lit("sprint").alias("entity_type"),
                        pl.col("iteration_id").alias("entity_id"),
                        pl.lit(setting["id"]).alias("settings_id"),
                    ]
                )
                all_facts.append(facts_change)

    # 4. Write to DB
    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(
        [f for f in all_facts if not f.is_empty()], how="diagonal_relaxed"
    )

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
