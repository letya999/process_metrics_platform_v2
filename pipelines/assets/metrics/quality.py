import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import quality as quality_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_sprints",
        "clean_jira_sprint_issues",
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_issue_status_changelog",
        "clean_jira_boards",
        "clean_jira_board_columns",
    ],
    description="Calculate Quality metrics",
    compute_kind="python",
)
def calculate_quality_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()

    # 1. Load Data
    sprints_df = read_table(
        engine,
        "SELECT * FROM clean_jira.sprints WHERE state IN ('closed', 'active') AND start_date IS NOT NULL",
    )
    if sprints_df.is_empty():
        return {"status": "skipped", "reason": "No sprints found"}

    sprint_issues_df = read_table(engine, "SELECT * FROM clean_jira.sprint_issues")
    issues_df = read_table(
        engine, "SELECT id, project_id, type_id as issue_type_id FROM clean_jira.issues"
    )
    issue_types_df = read_table(engine, "SELECT * FROM clean_jira.issue_types")
    issue_status_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.issue_status_changelog"
    )
    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, array_agg(bcs.status_id) as status_ids, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        GROUP BY bc.id, bc.board_id, bc.name, bc.position
    """,
    )
    # Note: board_columns_df status_ids is already an array in this query

    # 2. Resolve IDs
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    all_facts = []

    # A. Defect Density (Parameterized)
    calc_id_density = get_calculation_id(engine, "defect_density_by_type")
    settings_density = read_table(
        engine,
        """
        SELECT * FROM metrics.calculation_settings
        WHERE target_calculation_id = :calc_id AND enabled = true
    """,
        params={"calc_id": calc_id_density},
    )

    if not settings_density.is_empty():
        for setting in settings_density.to_dicts():
            num_type = setting["settings_json"].get("numerator_type")
            den_type = setting["settings_json"].get("denominator_type")
            if not num_type or not den_type:
                continue

            p_id = setting["project_id"]
            s_subset = sprints_df
            if p_id:
                s_subset = sprints_df.filter(pl.col("project_id") == p_id)
            if s_subset.is_empty():
                continue

            density = quality_logic.calculate_defect_density(
                s_subset,
                sprint_issues_df,
                issues_df,
                issue_types_df,
                num_type,
                den_type,
            )

            if not density.is_empty():
                facts = density.select(
                    [
                        pl.lit(calc_id_density).alias("metric_id"),
                        pl.col("project_id")
                        .replace(project_agg_map)
                        .alias("project_agg_id"),
                        pl.col("start_date")
                        .dt.strftime("%Y%m%d")
                        .cast(pl.Int32)
                        .alias("time_id"),
                        pl.col("density_ratio").alias("value"),
                        pl.lit("sprint").alias("entity_type"),
                        pl.col("iteration_id").alias("entity_id"),
                        pl.lit(setting["id"]).alias("settings_id"),
                    ]
                )
                all_facts.append(facts)

    # B. Backflow Rate
    calc_id_backflow = get_calculation_id(engine, "backflow_column_rate")
    backflow = quality_logic.calculate_backflow_rate(
        sprints_df, sprint_issues_df, issue_status_changelog_df, board_columns_df
    )
    if not backflow.is_empty():
        facts_backflow = backflow.select(
            [
                pl.lit(calc_id_backflow).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                pl.col("start_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.col("backflow_pct").alias("value"),
                pl.lit("sprint").alias("entity_type"),
                pl.col("iteration_id").alias("entity_id"),
            ]
        )
        all_facts.append(facts_backflow)

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

    return {"status": "success", "rows_written": rows_written}


@asset_check(asset=calculate_quality_metrics)
def quality_data_quality_check(database: DatabaseResource):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "backflow_column_rate")
    df = read_table(
        engine,
        "SELECT COUNT(*) as cnt FROM metrics.fact_values WHERE metric_id = :calc_id AND (value < 0 OR value > 100)",
        params={"calc_id": calc_id},
    )
    if not df.is_empty() and df[0, "cnt"] > 0:
        return AssetCheckResult(
            passed=False, metadata={"error": "Invalid percent values found"}
        )
    return AssetCheckResult(passed=True)
