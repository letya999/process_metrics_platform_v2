import polars as pl

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
        engine,
        "SELECT id FROM clean_jira.issues WHERE external_key='TWMOB-2017'",
    )[0, "id"]

    fvc = read_table(
        engine,
        f"""
        SELECT issue_id, field_key_id, old_value::text AS old_value,
               new_value::text AS new_value, changed_at
        FROM clean_jira.field_value_changelog
        WHERE issue_id='{issue_id}'
        """,
    )

    unit = resolve_unit_field(engine, project_id, "story_points")
    sp_ids = [str(unit["source_field_id"])]

    scope_df = pl.DataFrame({"issue_id": [issue_id], "sprint_id": [sprint_id]})
    target_dates = sprints_df.select(["id", "effective_end_date"]).rename(
        {"id": "sprint_id", "effective_end_date": "target_date"}
    )
    scope_with_dates = scope_df.join(
        target_dates, on="sprint_id", how="left", coalesce=True
    )

    changes = fvc.filter(pl.col("field_key_id").is_in(sp_ids))
    changes_filtered = changes.join(
        scope_df.select("issue_id").unique(), on="issue_id", how="inner"
    )
    joined = scope_with_dates.join(
        changes_filtered, on="issue_id", how="left", coalesce=True
    )

    corrections_before = (
        joined.filter(
            pl.col("changed_at").is_not_null()
            & (pl.col("changed_at") <= pl.col("target_date"))
        )
        .sort("changed_at", descending=True)
        .unique(subset=["issue_id", "sprint_id"], keep="first")
        .select(["issue_id", "sprint_id", "new_value", "target_date", "changed_at"])
    )

    parsed = corrections_before.with_columns(
        [
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
            .otherwise(0.0)
            .alias("historic_sp_before")
        ]
    )

    print("sp_ids", sp_ids)
    print("fvc")
    print(fvc)
    print("scope_with_dates")
    print(scope_with_dates)
    print("changes")
    print(changes)
    print("joined")
    print(joined)
    print("corrections_before")
    print(corrections_before)
    print("parsed")
    print(parsed)


if __name__ == "__main__":
    main()
