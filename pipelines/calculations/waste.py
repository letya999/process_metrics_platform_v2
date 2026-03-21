from typing import List

import polars as pl


def calculate_cancellation_rate_weekly(
    issue_status_changelog_df: pl.DataFrame,
    cancelled_status_ids: List[str],
    issues_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Count issues entering a cancelled status per week.
    """
    if issue_status_changelog_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "iso_week_start_date": pl.Date,
                "cancellation_count": pl.Int64,
            }
        )

    # Filter transitions to cancelled status
    entries = issue_status_changelog_df.filter(
        pl.col("to_status_id")
        .cast(pl.Utf8)
        .str.to_lowercase()
        .is_in([s.lower() for s in cancelled_status_ids])
    )

    # Join with issues to get project_id
    entries = entries.join(
        issues_df.select(["id", "project_id"]),
        left_on="issue_id",
        right_on="id",
        how="inner",
    )

    # Group by week and project
    agg = (
        entries.with_columns(
            (pl.col("changed_at").dt.date().dt.truncate("1w")).alias(
                "iso_week_start_date"
            )
        )
        .group_by(["project_id", "iso_week_start_date"])
        .agg(pl.col("issue_id").n_unique().alias("cancellation_count"))
    )

    return agg
