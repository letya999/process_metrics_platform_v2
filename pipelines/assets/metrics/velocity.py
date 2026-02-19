"""
Velocity Metrics Dagster Asset

This asset calculates Velocity metrics using Python/Polars logic
(replacing the old SQL Materialized View approach).
"""

from typing import Any

import polars as pl
from dagster import AssetExecutionContext, asset

from pipelines.calculations import velocity as velocity_logic
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


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
    description="Calculate Velocity facts using Python/Polars logic",
    compute_kind="python",
)
def calculate_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Velocity metrics (Plan vs Fact) for all sprints.

    This asset replaces the SQL Materialized View with Python/Polars logic,
    providing debuggable, testable metrics calculation.

    Outputs:
    - metrics.fact_velocity (base facts)
    - metrics.fact_velocity_slice (sliced by issue type)
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load all required tables into Polars DataFrames
    # IMPORTANT: Only load sprints that have at least one associated issue (excluding Sub-tasks)
    # This prevents duplicate sprints across projects with empty data
    sprints_df = read_table(
        engine,
        """
        SELECT DISTINCT s.id, s.project_id, s.name, s.start_date, s.end_date, s.complete_date
        FROM clean_jira.sprints s
        INNER JOIN clean_jira.sprint_issues si ON si.sprint_id = s.id
        INNER JOIN clean_jira.issues i ON i.id = si.issue_id
        INNER JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE s.start_date IS NOT NULL
          AND it.name NOT ILIKE '%%sub%%'
        """,
    )

    sprint_issues_df = read_table(
        engine,
        """
        SELECT DISTINCT si.issue_id, si.sprint_id
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        -- Exclude Sub-tasks by name (hierarchy_level may be incorrect in data)
        WHERE it.name NOT ILIKE '%%sub%%'
        """,
    )

    sprint_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, sprint_id, action, changed_at
        FROM clean_jira.sprint_issues_changelog
        """,
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

    field_values_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id, json_value::text AS json_value
        FROM clean_jira.field_values
        """,
    )

    field_keys_df = read_table(
        engine,
        """
        SELECT id, external_key, name
        FROM clean_jira.field_keys
        """,
    )

    status_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, from_status_id, to_status_id, changed_at
        FROM clean_jira.issue_status_changelog
        """,
    )

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id
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

    context.log.info(
        f"Loaded {len(sprints_df)} sprints, {len(issues_df)} issues, "
        f"{len(sprint_issues_df)} sprint-issue memberships"
    )

    # =====================================================
    # Calculate BASE velocity facts
    # =====================================================
    context.log.info("Calculating velocity facts...")
    velocity_df = velocity_logic.calculate_velocity_facts(
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

    context.log.info(f"Calculated velocity for {len(velocity_df)} sprints")

    # Write base facts to database
    context.log.info("Writing to metrics.fact_velocity...")
    write_table(velocity_df, engine, table="fact_velocity", schema="metrics")

    # =====================================================
    # Calculate SLICED velocity facts (Generic)
    # =====================================================
    context.log.info("Calculating velocity slices...")

    rules_df = get_slice_rules(engine, target_metric_table="fact_velocity")

    # Alias type_name to issue_type for the default rule
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def velocity_slice_calc(df_subset):
        # Calculate velocity using ONLY the subset of issues
        # calculate_velocity_facts handles filtering commitment/completion based on issues_df provided
        return velocity_logic.calculate_velocity_facts(
            sprints_df=sprints_df,
            sprint_issues_df=sprint_issues_df,
            sprint_changelog_df=sprint_changelog_df,
            issues_df=df_subset,  # Pass filtered issues
            field_values_df=field_values_df,
            field_keys_df=field_keys_df,
            status_changelog_df=status_changelog_df,
            boards_df=boards_df,
            board_columns_df=board_columns_df,
            field_value_changelog_df=field_value_changelog_df,
            issue_statuses_df=issue_statuses_df,
        )

    slice_df = apply_slicing(
        issues_for_slicing, rules_df, velocity_slice_calc, base_columns=["project_id"]
    )

    if not slice_df.is_empty():
        # Remove "spooky zeros": rows where there was NO plan AND NO completion for this slice
        slice_df = slice_df.filter(
            (pl.col("planned_issues") > 0)
            | (pl.col("completed_issues") > 0)
            | (pl.col("planned_story_points") > 0)
            | (pl.col("completed_story_points") > 0)
        )

    if not slice_df.is_empty():
        context.log.info(
            f"Writing {len(slice_df)} rows to metrics.fact_velocity_slices..."
        )

        # Match schema: project_id, iteration_id, slice_rule_name, slice_value, iteration_name, start_date, end_date, planned_issues, completed_issues, planned_story_points, completed_story_points
        # The slice_df already has these from velocity_slice_calc, we just need to select/verify.
        write_table(slice_df, engine, table="fact_velocity_slices", schema="metrics")

    # =====================================================
    # Return summary statistics
    # =====================================================
    total_planned = (
        int(velocity_df["planned_issues"].sum()) if not velocity_df.is_empty() else 0
    )
    total_completed = (
        int(velocity_df["completed_issues"].sum()) if not velocity_df.is_empty() else 0
    )

    context.log.info(
        f"✅ Velocity calculation complete: "
        f"{total_planned} planned issues, {total_completed} completed issues"
    )

    return {
        "status": "success",
        "sprints_processed": len(velocity_df),
        "total_planned_issues": total_planned,
        "total_completed_issues": total_completed,
        "slice_rows": len(slice_df) if not slice_df.is_empty() else 0,
    }
