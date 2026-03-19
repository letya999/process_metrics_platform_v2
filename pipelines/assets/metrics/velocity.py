"""
Velocity Metrics Dagster Asset (Generic Long Metric Store)
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import velocity as velocity_logic
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
        "clean_jira_sprints",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_sprint_issues",
        "clean_jira_sprint_issues_changelog",
        "clean_jira_issue_status_changelog",
        "clean_jira_field_values",
        "clean_jira_field_keys",
    ],
    description="Calculate Velocity facts and write to generic fact_values",
    compute_kind="python",
)
def calculate_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "velocity")
    calc_map = {
        "planned_story_points": get_calculation_id(engine, "velocity_planned_sp"),
        "completed_story_points": get_calculation_id(engine, "velocity_completed_sp"),
        "planned_issues": get_calculation_id(engine, "velocity_planned_count"),
        "completed_issues": get_calculation_id(engine, "velocity_completed_count"),
    }
    metric_ids = list(calc_map.values())

    context.log.info("Loading data from clean_jira schema...")

    # Load data (keeping queries same as before but optimizing where possible)
    sprints_df = read_table(
        engine,
        """
        SELECT DISTINCT s.id, s.project_id, s.name, s.start_date, s.end_date, s.complete_date, p.project_key
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON s.project_id = p.id
        INNER JOIN clean_jira.sprint_issues si ON si.sprint_id = s.id
        INNER JOIN clean_jira.issues i ON i.id = si.issue_id
        INNER JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE s.start_date IS NOT NULL
          AND it.name NOT ILIKE '%%sub%%'
        """,
    )

    if sprints_df.is_empty():
        return {"status": "skipped", "reason": "No sprints found"}

    # Map project_agg_ids
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    sprint_issues_df = read_table(
        engine,
        """
        SELECT DISTINCT si.issue_id, si.sprint_id
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE it.name NOT ILIKE '%%sub%%'
        """,
    )

    sprint_changelog_df = read_table(
        engine,
        "SELECT issue_id, sprint_id, action, changed_at FROM clean_jira.sprint_issues_changelog",
    )

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name, i.status_id,
               i.jira_created_at, i.jira_resolved_at
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    field_keys_df = read_table(
        engine, "SELECT id, external_key, name FROM clean_jira.field_keys"
    )

    # Resolve unit fields per project
    # We override field_keys_df in the logic if specific fields are configured in metrics.units
    # For now, we'll let extract_story_points do its heuristic but we COULD pass it the field_id.

    field_values_df = read_table(
        engine,
        "SELECT issue_id, field_key_id, json_value::text AS json_value FROM clean_jira.field_values",
    )

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

    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id,
               old_value::text as old_value,
               new_value::text as new_value,
               changed_at
        FROM clean_jira.field_value_changelog
        """,
    )

    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )

    # 2. Calculate BASE velocity facts
    velocity_wide = velocity_logic.calculate_velocity_facts(
        sprints_df=sprints_df,
        sprint_issues_df=sprint_issues_df,
        sprint_changelog_df=sprint_changelog_df,
        issues_df=issues_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        field_value_changelog_df=field_value_changelog_df,
        issue_statuses_df=issue_statuses_df,
    )

    if velocity_wide.is_empty():
        return {"status": "no_data"}

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(df_wide, slice_rule_id=None, slice_value_col=None):
        melted = df_wide.melt(
            id_vars=["project_id", "iteration_id", "end_date"]
            + ([slice_value_col] if slice_value_col else []),
            value_vars=[
                "planned_story_points",
                "completed_story_points",
                "planned_issues",
                "completed_issues",
            ],
            variable_name="calc_code",
            value_name="value",
        )

        # Map IDs
        melted = melted.with_columns(
            [
                pl.col("calc_code").replace(calc_map).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # end_date -> time_id (YYYYMMDD)
                pl.col("end_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.lit("sprint").alias("entity_type"),
                pl.col("iteration_id").cast(pl.Utf8).alias("entity_id"),
                pl.lit(slice_rule_id).alias("slice_rule_id"),
                pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                if slice_value_col
                else pl.lit(None).alias("slice_value"),
                pl.lit(None).alias("commitment_rule_id"),
                pl.lit(None).alias("event_start_at"),
                pl.lit(None).alias("event_end_at"),
            ]
        )

        return melted.select(
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

    base_facts = transform_to_fact_values(velocity_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    # Heuristic for default rules: alias type_name
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def velocity_slice_calc(df_subset):
        return velocity_logic.calculate_velocity_facts(
            sprints_df=sprints_df,
            sprint_issues_df=sprint_issues_df,
            sprint_changelog_df=sprint_changelog_df,
            issues_df=df_subset,
            field_values_df=field_values_df,
            field_keys_df=field_keys_df,
            status_changelog_df=status_changelog_df,
            boards_df=boards_df,
            board_columns_df=board_columns_df,
            field_value_changelog_df=field_value_changelog_df,
            issue_statuses_df=issue_statuses_df,
        )

    # apply_slicing returns a concatenated DF of slices
    # We need to process each slice individually to get the rule info
    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]

            # Apply slicing for ONE rule at a time to keep it manageable
            one_rule_df = rules_df.filter(pl.col("slice_rule_id") == rule_id)
            sliced_wide = apply_slicing(
                issues_for_slicing, one_rule_df, velocity_slice_calc
            )

            if not sliced_wide.is_empty():
                # Filter zeros
                sliced_wide = sliced_wide.filter(
                    (pl.col("planned_issues") > 0) | (pl.col("completed_issues") > 0)
                )
                if not sliced_wide.is_empty():
                    facts = transform_to_fact_values(
                        sliced_wide,
                        slice_rule_id=rule_id,
                        slice_value_col="slice_value",
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
        "sprints_processed": len(velocity_wide),
        "metric_ids": metric_ids,
    }


@asset_check(asset=calculate_velocity)
def velocity_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "velocity_completed_sp")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
