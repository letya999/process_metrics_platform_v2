from typing import List

import polars as pl


def calculate_issue_lifetime(
    issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
) -> pl.DataFrame:
    """
    Calculate days from creation to first completion.
    """
    # Find first completion for each issue
    completions = (
        issue_status_changelog_df.filter(
            pl.col("to_status_id")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .is_in([s.lower() for s in done_status_ids])
        )
        .sort("changed_at")
        .unique(subset="issue_id", keep="first")
        .select(["issue_id", pl.col("changed_at").alias("done_date")])
    )

    # Join with issues
    issues_with_done = issues_df.select(
        ["id", "issue_key", "project_id", "created_at"]
    ).join(completions, left_on="id", right_on="issue_id", how="inner")

    # Calculate lifetime
    result = issues_with_done.with_columns(
        ((pl.col("done_date") - pl.col("created_at")).dt.total_seconds() / (24 * 3600))
        .ceil()
        .alias("lifetime_days")
    ).filter(pl.col("lifetime_days") >= 0)

    return result


def calculate_cycle_time_custom(
    issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    start_status_id: str,
    end_status_id: str,
) -> pl.DataFrame:
    """
    Calculate cycle time between two specific statuses.
    """
    # Find first entry into start status
    starts = (
        issue_status_changelog_df.filter(
            pl.col("to_status_id").cast(pl.Utf8).str.to_lowercase()
            == start_status_id.lower()
        )
        .sort("changed_at")
        .unique(subset="issue_id", keep="first")
        .select(["issue_id", pl.col("changed_at").alias("start_at")])
    )

    # Find first entry into end status AFTER start_at
    # This requires a join and filter
    joined = starts.join(issue_status_changelog_df, on="issue_id", how="inner")

    ends = (
        joined.filter(
            (
                pl.col("to_status_id").cast(pl.Utf8).str.to_lowercase()
                == end_status_id.lower()
            )
            & (pl.col("changed_at") > pl.col("start_at"))
        )
        .sort("changed_at")
        .unique(subset="issue_id", keep="first")
        .select(["issue_id", "start_at", pl.col("changed_at").alias("end_at")])
    )

    # Join with issues
    result = issues_df.select(["id", "issue_key", "project_id"]).join(
        ends, left_on="id", right_on="issue_id", how="inner"
    )

    result = result.with_columns(
        ((pl.col("end_at") - pl.col("start_at")).dt.total_seconds() / (24 * 3600))
        .ceil()
        .alias("cycle_days")
    )

    return result


def calculate_epic_delivery_time(
    issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    commitment_start_status_ids: List[str],
    done_status_ids: List[str],
) -> pl.DataFrame:
    """
    Calculate epic delivery time: min(child starts) to max(child dones).
    """
    if "parent_id" not in issues_df.columns:
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "epic_id": pl.Utf8,
                "epic_key": pl.Utf8,
                "epic_start": pl.Datetime,
                "epic_end": pl.Datetime,
                "delivery_days": pl.Float64,
            }
        )

    # Find start and end times for all issues
    starts = (
        issue_status_changelog_df.filter(
            pl.col("to_status_id")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .is_in([s.lower() for s in commitment_start_status_ids])
        )
        .sort("changed_at")
        .unique(subset="issue_id", keep="first")
        .select(["issue_id", pl.col("changed_at").alias("issue_start")])
    )

    ends = (
        issue_status_changelog_df.filter(
            pl.col("to_status_id")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .is_in([s.lower() for s in done_status_ids])
        )
        .sort("changed_at")
        .unique(subset="issue_id", keep="last")
        .select(["issue_id", pl.col("changed_at").alias("issue_end")])
    )

    # Group issues by parent (epic)
    children = issues_df.filter(pl.col("parent_id").is_not_null()).select(
        ["id", "parent_id", "project_id"]
    )

    children_with_times = children.join(
        starts, left_on="id", right_on="issue_id", how="left"
    ).join(ends, left_on="id", right_on="issue_id", how="left")

    # Aggregate by epic
    epic_times = (
        children_with_times.group_by("parent_id")
        .agg(
            [
                pl.col("project_id").first(),
                pl.col("issue_start").min().alias("epic_start"),
                pl.col("issue_end").max().alias("epic_end"),
            ]
        )
        .filter(pl.col("epic_start").is_not_null() & pl.col("epic_end").is_not_null())
    )

    # Join with epic details
    epics = issues_df.select(["id", "issue_key"]).rename(
        {"id": "epic_id", "issue_key": "epic_key"}
    )

    result = epics.join(
        epic_times, left_on="epic_id", right_on="parent_id", how="inner"
    )

    result = result.with_columns(
        ((pl.col("epic_end") - pl.col("epic_start")).dt.total_seconds() / (24 * 3600))
        .ceil()
        .alias("delivery_days")
    ).filter(pl.col("delivery_days") >= 0)

    return result
