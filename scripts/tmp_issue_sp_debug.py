import polars as pl

from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table


def main() -> None:
    db = DatabaseResource()
    engine = db.get_engine()

    issue_key = "TWMOB-2017"

    s = read_table(
        engine,
        """
        SELECT s.id, s.start_date, COALESCE(s.complete_date,s.end_date) AS effective_end_date
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id=s.project_id
        WHERE p.external_key='TWMOB' AND s.name='Sprint 34'
        """,
    )
    target = s[0, "effective_end_date"]

    issue_id = read_table(
        engine, f"SELECT id FROM clean_jira.issues WHERE external_key='{issue_key}'"
    )[0, "id"]

    fk_id = read_table(
        engine,
        """
        SELECT fk.id
        FROM clean_jira.field_keys fk
        JOIN clean_jira.projects p ON p.id=fk.project_id
        WHERE p.external_key='TWMOB' AND fk.external_key='customfield_10036'
        LIMIT 1
        """,
    )[0, "id"]

    ch = read_table(
        engine,
        f"""
        SELECT issue_id, field_key_id, old_value::text AS old_value,
               new_value::text AS new_value, changed_at
        FROM clean_jira.field_value_changelog
        WHERE issue_id='{issue_id}' AND field_key_id='{fk_id}'
        ORDER BY changed_at
        """,
    )

    print("target", target)
    print("changelog")
    print(ch)

    if ch.is_empty():
        return

    parsed = ch.with_columns(
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
            .alias("parsed_new"),
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
            .otherwise(0.0)
            .alias("parsed_old"),
        ]
    )
    print("parsed")
    print(parsed)

    before = (
        parsed.filter(pl.col("changed_at") <= pl.lit(target))
        .sort("changed_at", descending=True)
        .head(1)
    )
    print("before-target row")
    print(before)


if __name__ == "__main__":
    main()
