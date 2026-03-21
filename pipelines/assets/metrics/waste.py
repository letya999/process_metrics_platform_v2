import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import waste as waste_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issue_status_changelog",
        "clean_jira_issues",
        "clean_jira_boards",
        "clean_jira_board_columns",
    ],
    description="Calculate Waste metrics",
    compute_kind="python",
)
def calculate_waste_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()

    # 1. Load Data
    issues_df = read_table(engine, "SELECT id, project_id FROM clean_jira.issues")
    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    issue_status_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.issue_status_changelog"
    )
    issue_statuses_df = read_table(
        engine, "SELECT id, name FROM clean_jira.issue_statuses"
    )

    # 2. Resolve IDs and Rules
    calc_id_waste = get_calculation_id(engine, "cancellation_rate_weekly")
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # Load settings
    settings_df = read_table(
        engine,
        """
        SELECT * FROM metrics.calculation_settings
        WHERE target_calculation_id = :calc_id AND enabled = true
    """,
        params={"calc_id": calc_id_waste},
    )

    all_facts = []

    for p_id in project_ids:
        # Resolve cancelled_status_ids for this project
        p_setting = settings_df.filter(pl.col("project_id") == p_id)
        if p_setting.is_empty():
            p_setting = settings_df.filter(pl.col("project_id").is_null())

        cancelled_ids = []
        if not p_setting.is_empty():
            cancelled_ids = p_setting[0, "settings_json"].get(
                "cancelled_status_ids", []
            )

        if not cancelled_ids:
            # Auto-detect from names
            cancelled_ids = issue_statuses_df.filter(
                pl.col("name")
                .str.to_lowercase()
                .str.contains(r"cancel|reject|won't fix|duplicate")
            )["id"].to_list()

        if not cancelled_ids:
            continue

        waste = waste_logic.calculate_cancellation_rate_weekly(
            issue_status_changelog_df,
            cancelled_ids,
            issues_df.filter(pl.col("project_id") == p_id),
        )

        if not waste.is_empty():
            facts = waste.select(
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
                ]
            )
            all_facts.append(facts)

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
