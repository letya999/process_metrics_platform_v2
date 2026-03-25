"""
Flow Efficiency Calculation (Python/Polars Implementation)

Calculates Active vs Wait time for completed issues.
Flow Efficiency % = (Active Time / (Active Time + Wait Time)) * 100
"""

from typing import List

import polars as pl


def calculate_flow_efficiency_per_issue(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    active_status_ids: List[str],
    wait_status_ids: List[str],
    end_status_ids: List[str],
) -> pl.DataFrame:
    """
    Calculate flow efficiency for each issue.
    """
    if issues_df.is_empty() or status_changelog_df.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "active_days": pl.Float64,
                "wait_days": pl.Float64,
                "efficiency_pct": pl.Float64,
                "completion_date": pl.Datetime,
            }
        )

    # 1. Identify issues that reached END status
    completed_events = (
        status_changelog_df.filter(pl.col("to_status_id").is_in(end_status_ids))
        .sort("changed_at", descending=False)
        .unique(subset=["issue_id"], keep="first")
    )

    if completed_events.is_empty():
        return pl.DataFrame()

    # 2. Get full history for these issues
    target_ids = completed_events["issue_id"].unique().to_list()
    history = status_changelog_df.filter(pl.col("issue_id").is_in(target_ids)).sort(
        ["issue_id", "changed_at"]
    )

    # Restrict intervals to the first completion window per issue.
    history = history.join(
        completed_events.select(
            ["issue_id", pl.col("changed_at").alias("completion_date")]
        ),
        on="issue_id",
        how="inner",
    )

    # 3. Calculate time in each status
    # Add next_changed_at by shifting
    history = history.with_columns(
        [pl.col("changed_at").shift(-1).over("issue_id").alias("next_changed_at")]
    )

    # Duration in status
    history = history.with_columns(
        [
            pl.when(pl.col("next_changed_at").is_null())
            .then(pl.col("completion_date"))
            .otherwise(pl.min_horizontal(["next_changed_at", "completion_date"]))
            .alias("interval_end_at")
        ]
    ).filter(pl.col("changed_at") < pl.col("completion_date"))

    history = history.with_columns(
        [
            (
                (pl.col("interval_end_at") - pl.col("changed_at")).dt.total_seconds()
                / 86400.0
            ).alias("duration_days")
        ]
    ).filter(pl.col("duration_days") > 0)

    # 4. Map statuses to Active/Wait
    active_set = set(active_status_ids)
    wait_set = set(wait_status_ids)

    history = history.with_columns(
        [
            pl.when(pl.col("to_status_id").is_in(active_set))
            .then(pl.lit("active"))
            .when(pl.col("to_status_id").is_in(wait_set))
            .then(pl.lit("wait"))
            .otherwise(pl.lit("other"))
            .alias("status_type")
        ]
    )

    # 5. Aggregate
    agg = history.group_by("issue_id").agg(
        [
            pl.col("duration_days")
            .filter(pl.col("status_type") == "active")
            .sum()
            .alias("active_days"),
            pl.col("duration_days")
            .filter(pl.col("status_type") == "wait")
            .sum()
            .alias("wait_days"),
        ]
    )

    # 6. Final Join
    result = (
        completed_events.select(
            ["issue_id", pl.col("changed_at").alias("completion_date")]
        )
        .join(agg, on="issue_id", how="inner")
        .join(
            issues_df.select(["id", "project_id", "key"]),
            left_on="issue_id",
            right_on="id",
        )
        .rename({"key": "issue_key"})
    )

    result = result.with_columns(
        [
            (
                pl.col("active_days")
                / (pl.col("active_days") + pl.col("wait_days")).clip_min(0.0001)
                * 100.0
            )
            .round(2)
            .alias("efficiency_pct")
        ]
    )

    return result.select(
        [
            "issue_id",
            "project_id",
            "issue_key",
            "active_days",
            "wait_days",
            "efficiency_pct",
            "completion_date",
        ]
    )
