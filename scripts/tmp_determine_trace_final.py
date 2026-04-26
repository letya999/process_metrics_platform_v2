import polars as pl

from pipelines.calculations.velocity import extract_story_points
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import resolve_unit_field
from pipelines.utils.polars_db import read_table


def main() -> None:
    db = DatabaseResource()
    engine = db.get_engine()

    sprints_df = read_table(
        engine,
        """
        SELECT s.id, s.project_id, COALESCE(s.complete_date,s.end_date) AS effective_end_date
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id=s.project_id
        WHERE p.external_key='TWMOB' AND s.name='Sprint 34'
        """,
    )
    sprint_id = sprints_df[0, "id"]
    project_id = sprints_df[0, "project_id"]

    issue_id = read_table(
        engine, "SELECT id FROM clean_jira.issues WHERE external_key='TWMOB-2017'"
    )[0, "id"]

    issues_df = read_table(
        engine,
        f"SELECT i.id, it.name AS type_name FROM clean_jira.issues i LEFT JOIN clean_jira.issue_types it ON it.id=i.type_id WHERE i.project_id='{project_id}'",
    )
    field_keys_df = read_table(
        engine,
        f"SELECT id,external_key,name FROM clean_jira.field_keys WHERE project_id='{project_id}'",
    )
    field_values_df = read_table(
        engine,
        f"SELECT fv.issue_id,fv.field_key_id,fv.json_value::text AS json_value FROM clean_jira.field_values fv JOIN clean_jira.issues i ON i.id=fv.issue_id WHERE i.project_id='{project_id}'",
    )
    changelog_df = read_table(
        engine,
        f"SELECT fvc.issue_id,fvc.field_key_id,fvc.old_value::text AS old_value,fvc.new_value::text AS new_value,fvc.changed_at FROM clean_jira.field_value_changelog fvc JOIN clean_jira.issues i ON i.id=fvc.issue_id WHERE i.project_id='{project_id}'",
    )

    unit = resolve_unit_field(engine, project_id, "story_points")
    sp_ids = [str(unit["source_field_id"])]

    current_sp_df = extract_story_points(
        issues_df, field_values_df, field_keys_df, sp_ids
    )

    scope_df = pl.DataFrame({"issue_id": [issue_id], "sprint_id": [sprint_id]})
    target_dates = sprints_df.select(["id", "effective_end_date"]).rename(
        {"id": "sprint_id", "effective_end_date": "target_date"}
    )
    scope_with_dates = scope_df.join(
        target_dates, on="sprint_id", how="left", coalesce=True
    )

    changes = changelog_df.filter(pl.col("field_key_id").is_in(sp_ids))
    relevant_issues = scope_df.select("issue_id").unique()
    changes_filtered = changes.join(relevant_issues, on="issue_id", how="inner")
    joined = scope_with_dates.join(
        changes_filtered, on="issue_id", how="left", coalesce=True
    )

    corrections_after = (
        joined.filter(
            pl.col("changed_at").is_not_null()
            & (pl.col("changed_at") > pl.col("target_date"))
        )
        .sort("changed_at", descending=False)
        .unique(subset=["issue_id", "sprint_id"], keep="first")
        .select(["issue_id", "sprint_id", "old_value"])
        .with_columns(
            pl.when(
                pl.col("old_value").is_not_null()
                & pl.col("old_value")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.contains(r"^-?[0-9]+\.?[0-9]*$")
            )
            .then(
                pl.col("old_value")
                .cast(pl.Utf8)
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            .otherwise(None)
            .alias("historic_sp_after")
        )
        .select(["issue_id", "sprint_id", "historic_sp_after"])
    )

    corrections_before = (
        joined.filter(
            pl.col("changed_at").is_not_null()
            & (pl.col("changed_at") <= pl.col("target_date"))
        )
        .sort("changed_at", descending=True)
        .unique(subset=["issue_id", "sprint_id"], keep="first")
        .select(["issue_id", "sprint_id", "new_value"])
        .with_columns(
            pl.when(
                pl.col("new_value").is_not_null()
                & pl.col("new_value")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.contains(r"^-?[0-9]+\.?[0-9]*$")
            )
            .then(
                pl.col("new_value")
                .cast(pl.Utf8)
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            .otherwise(None)
            .alias("historic_sp_before")
        )
        .select(["issue_id", "sprint_id", "historic_sp_before"])
    )

    init_sp = scope_df.join(current_sp_df, on="issue_id", how="left", coalesce=True)
    final = (
        init_sp.join(
            corrections_after, on=["issue_id", "sprint_id"], how="left", coalesce=True
        )
        .join(
            corrections_before, on=["issue_id", "sprint_id"], how="left", coalesce=True
        )
        .with_columns(
            pl.coalesce(["historic_sp_after", "historic_sp_before", "story_points"])
            .fill_null(0.0)
            .alias("story_points")
        )
        .select(
            [
                "issue_id",
                "sprint_id",
                "historic_sp_after",
                "historic_sp_before",
                "story_points",
            ]
        )
    )

    print("init_sp")
    print(init_sp)
    print("corrections_after")
    print(corrections_after)
    print("corrections_before")
    print(corrections_before)
    print("final")
    print(final)


if __name__ == "__main__":
    main()
