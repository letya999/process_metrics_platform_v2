"""
Velocity Metrics Dagster Asset

This asset calculates Velocity metrics using Python/Polars logic
(replacing the old SQL Materialized View approach).
"""

from typing import Any

from dagster import AssetExecutionContext, asset

from pipelines.calculations import velocity as velocity_logic
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_sprints",
        "clean_jira_boards",
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
    sprints_df = read_table(
        engine,
        """
        SELECT id, project_id, name, start_date, end_date, complete_date
        FROM clean_jira.sprints
        WHERE start_date IS NOT NULL
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
        SELECT issue_id, to_status_id, changed_at
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
    )

    context.log.info(f"Calculated velocity for {len(velocity_df)} sprints")

    # Write base facts to database
    context.log.info("Writing to metrics.fact_velocity...")
    write_table(velocity_df, engine, table="fact_velocity", schema="metrics")

    # =====================================================
    # Calculate SLICED velocity facts (by issue type)
    # =====================================================
    context.log.info("Calculating velocity slices by issue type...")
    velocity_slice_df = velocity_logic.calculate_velocity_slice_by_issue_type(
        sprint_issues_df=sprint_issues_df,
        sprint_changelog_df=sprint_changelog_df,
        issues_df=issues_df,
        sprints_df=sprints_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        field_value_changelog_df=field_value_changelog_df,
    )

    context.log.info(f"Calculated {len(velocity_slice_df)} velocity slice rows")

    # Write slices to database
    context.log.info("Writing to metrics.fact_velocity_slice...")
    write_table(
        velocity_slice_df, engine, table="fact_velocity_slice", schema="metrics"
    )

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
        "slice_rows": len(velocity_slice_df),
    }
