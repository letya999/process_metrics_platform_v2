import polars as pl


def calculate_daily_status_entry(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    target_status_id: str,
) -> pl.DataFrame:
    """
    Count issues entering a target status per day.
    """
    if issue_status_changelog_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "iteration_id": pl.Utf8,
                "time_date": pl.Date,
                "entry_count": pl.Int64,
            }
        )

    # Filter changes to target status
    # BUG-1: Slim changelog to avoid 'id' collision in cross-join
    entries = issue_status_changelog_df.select(
        ["issue_id", "to_status_id", "changed_at"]
    ).filter(
        pl.col("to_status_id").cast(pl.Utf8).str.to_lowercase()
        == target_status_id.lower()
    )

    # Map to sprints
    entries_with_sprints = entries.join(
        sprints_df.select(["id", "project_id", "start_date", "end_date"]), how="cross"
    ).filter(
        (pl.col("changed_at") > pl.col("start_date"))
        & (pl.col("changed_at") <= pl.col("end_date"))
    )

    # Ensure issues were in the sprint
    entries_with_sprints = entries_with_sprints.join(
        sprint_issues_df,
        left_on=["issue_id", "id"],
        right_on=["issue_id", "sprint_id"],
        how="inner",
    )

    if entries_with_sprints.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "iteration_id": pl.Utf8,
                "time_date": pl.Date,
                "entry_count": pl.Int64,
            }
        )

    agg = (
        entries_with_sprints.with_columns(
            pl.col("changed_at").dt.date().alias("time_date")
        )
        .group_by(["project_id", "id", "time_date"])
        .agg(pl.col("issue_id").count().alias("entry_count"))
        .rename({"id": "iteration_id"})
    )

    return agg


def calculate_field_change_count(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    field_key_id: str,
) -> pl.DataFrame:
    """
    Count changes to a specific field per sprint.
    """
    if field_value_changelog_df.is_empty():
        return sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        ).with_columns(pl.lit(0).alias("change_count"))

    # Filter changelog by field
    # BUG-1: Slim changelog to avoid 'id' collision in cross-join
    changes = field_value_changelog_df.select(
        ["issue_id", "field_key_id", "change_time"]
    ).filter(pl.col("field_key_id") == field_key_id)

    # Join with sprint dates
    changes_with_sprints = changes.join(
        sprints_df.select(["id", "project_id", "start_date", "end_date"]), how="cross"
    ).filter(
        (pl.col("change_time") > pl.col("start_date"))
        & (pl.col("change_time") <= pl.col("end_date"))
    )

    # Ensure issues in sprint
    changes_with_sprints = changes_with_sprints.join(
        sprint_issues_df,
        left_on=["issue_id", "id"],
        right_on=["issue_id", "sprint_id"],
        how="inner",
    )

    agg = (
        changes_with_sprints.group_by("id")
        .agg(pl.col("issue_id").count().alias("change_count"))
        .rename({"id": "iteration_id"})
    )

    result = (
        sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        )
        .join(agg, on="iteration_id", how="left")
        .with_columns(pl.col("change_count").fill_null(0))
    )

    return result
