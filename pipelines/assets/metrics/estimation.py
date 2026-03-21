import logging
from datetime import date

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import estimation as estimation_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_field_value_changelog",
        "clean_jira_field_values",
        "clean_jira_field_keys",
    ],
    description="Calculate Estimation metrics",
    compute_kind="python",
)
def calculate_estimation_metrics(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()
    today_id = int(date.today().strftime("%Y%m%d"))

    # 1. Load Data
    issues_df = read_table(
        engine, "SELECT id, project_id, issue_key FROM clean_jira.issues"
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

    # 2. Resolve IDs
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    calc_id_volatility = get_calculation_id(engine, "estimate_volatility_abs")

    # SP field key (heuristic)
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None

    if not sp_field_key_id:
        return {"status": "skipped", "reason": "No Story Points field found"}

    # 3. Calculation
    volatility = estimation_logic.calculate_estimate_volatility(
        issues_df, field_value_changelog_df, field_values_df, sp_field_key_id
    )

    if volatility.is_empty():
        return {"status": "no_data"}

    # 4. Transform to Long Format
    facts = volatility.select(
        [
            pl.lit(calc_id_volatility).alias("metric_id"),
            pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
            pl.lit(today_id).cast(pl.Int32).alias("time_id"),
            pl.col("volatility").alias("value"),
            pl.lit("issue").alias("entity_type"),
            pl.col("issue_id").alias("entity_id"),
        ]
    )

    # 5. Write to DB
    rows_written = write_fact_values(
        facts,
        engine,
        metric_id=calc_id_volatility,
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
