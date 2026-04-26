import polars as pl

from pipelines.calculations.velocity import (
    determine_story_points_at_date,
    extract_story_points,
)
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import resolve_unit_field
from pipelines.utils.polars_db import read_table


def main() -> None:
    db = DatabaseResource()
    engine = db.get_engine()

    sprints_df = read_table(
        engine,
        """
        SELECT s.id, s.project_id, s.name, s.start_date, s.end_date, s.complete_date
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id=s.project_id
        WHERE p.external_key='TWMOB' AND s.name='Sprint 34'
        """,
    )
    sprint_id = sprints_df[0, "id"]
    project_id = sprints_df[0, "project_id"]

    issue_row = read_table(
        engine,
        "SELECT id FROM clean_jira.issues WHERE external_key='TWMOB-2017'",
    )
    issue_id = issue_row[0, "id"]

    issues_df = read_table(
        engine,
        f"""
        SELECT i.id, it.name AS type_name
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON it.id=i.type_id
        WHERE i.project_id='{project_id}'
        """,
    )

    field_keys_df = read_table(
        engine,
        f"SELECT id, external_key, name FROM clean_jira.field_keys WHERE project_id='{project_id}'",
    )
    field_values_df = read_table(
        engine,
        f"""
        SELECT fv.issue_id, fv.field_key_id, fv.json_value::text AS json_value
        FROM clean_jira.field_values fv
        JOIN clean_jira.issues i ON i.id=fv.issue_id
        WHERE i.project_id='{project_id}'
        """,
    )
    field_value_changelog_df = read_table(
        engine,
        f"""
        SELECT fvc.issue_id, fvc.field_key_id, fvc.old_value::text AS old_value,
               fvc.new_value::text AS new_value, fvc.changed_at
        FROM clean_jira.field_value_changelog fvc
        JOIN clean_jira.issues i ON i.id=fvc.issue_id
        WHERE i.project_id='{project_id}'
        """,
    )

    unit = resolve_unit_field(engine, project_id, "story_points")
    sp_override = (
        [str(unit["source_field_id"])] if unit and unit.get("source_field_id") else None
    )

    current_sp_df = extract_story_points(
        issues_df, field_values_df, field_keys_df, sp_override
    )

    sprints_eff = sprints_df.with_columns(
        pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
    )
    scope_one = pl.DataFrame({"issue_id": [issue_id], "sprint_id": [sprint_id]})

    out = determine_story_points_at_date(
        scope_one,
        sprints_eff,
        current_sp_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="effective_end_date",
        sp_field_key_ids_override=sp_override,
    )

    print("sp_override", sp_override)
    print(out)


if __name__ == "__main__":
    main()
