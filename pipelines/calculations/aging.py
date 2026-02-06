"""
Work Item Aging Calculation (Python/Polars Implementation)

This module calculates the "Aging" of currently active work items.
It helps answer: "How long has this ticket been in progress?"

Key Metrics:
- Current Age: Time since commitment start (in days)
- Age in Status: Time spent in the current status
- Service Level Expectation (SLE) health check (e.g. is it past the 85th percentile?)

Business Rules:
1. Only considers issues that are currently "In Progress" (between Start and End points).
2. Age is calculated from `commitment_start_at` until `now()`.
3. If an issue moves backward or is paused, the total age typically continues counting
   unless specific "Hold" rules are applied (simple version counts wall-clock time).
"""

from datetime import datetime, timezone

import polars as pl

from pipelines.calculations.lead_time import identify_commitment_points


def calculate_aging_work(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate aging metrics for currently active issues.

    Args:
        issues_df: Issue details (id, project_id, key, type_name, jira_created_at, current_status_id)
        status_changelog_df: Status change history (issue_id, from_status_id, to_status_id, changed_at)
        boards_df: Board definitions
        board_columns_df: Board column configuration

    Returns:
        DataFrame: [id, project_id, key, summary, issue_type, current_status,
                    commitment_start_at, age_days, age_in_status_days]
    """
    if issues_df.is_empty():
        return _empty_aging_df()

    # 1. Identify "In Progress" scope
    points = identify_commitment_points(boards_df, board_columns_df)
    middle_status_ids = points.get("middle_status_ids", [])
    start_status_ids = points.get("start_status_ids", [])

    # Active items are those currently in "Start" or "Middle" statuses
    # (assuming "End" statuses are Done/Closed)
    active_status_ids = start_status_ids + middle_status_ids

    if not active_status_ids:
        return _empty_aging_df()

    # Filter for currently active issues
    active_issues = issues_df.filter(
        pl.col("current_status_id").is_in(active_status_ids)
    )

    if active_issues.is_empty():
        return _empty_aging_df()

    # 2. Calculate Commitment Start (First entry to In Progress) for these active issues

    # Get all transitions to In Progress statuses
    start_transitions = status_changelog_df.filter(
        pl.col("to_status_id").is_in(active_status_ids)
        & pl.col("issue_id").is_in(active_issues["id"])
    )

    # Find the FIRST time each issue entered an active status
    # Note: A more robust version might look for the first time it entered *any* status
    # mapped to a column >= Start Column. For now, we use the set of active statuses.
    start_events = start_transitions.group_by("issue_id").agg(
        pl.col("changed_at").min().alias("start_at_changelog")
    )

    # Join back to active issues to Determine Start Date & Current Age
    now = datetime.now(timezone.utc)

    aging_df = (
        active_issues.join(start_events, left_on="id", right_on="issue_id", how="left")
        .with_columns(
            [
                # Start date: Changelog OR Created date fallback
                pl.coalesce([pl.col("start_at_changelog"), pl.col("jira_created_at")])
                .cast(pl.Datetime("us", "UTC"))
                .alias("commitment_start_at")
            ]
        )
        .with_columns(
            [
                # Total Age
                (
                    (
                        pl.lit(now).cast(pl.Datetime("us", "UTC"))
                        - pl.col("commitment_start_at")
                    ).dt.total_seconds()
                    / 86400.0
                ).alias("age_days")
            ]
        )
    )

    # 3. Calculate "Age in Current Status"
    # Find the LAST transition to the current status
    last_transition = (
        status_changelog_df.sort("changed_at", descending=True)
        .unique(subset=["issue_id"], keep="first")
        .select(["issue_id", "changed_at", "to_status_id"])
        .rename({"changed_at": "last_status_change_at"})
    )

    aging_df = (
        aging_df.join(
            last_transition,
            left_on=["id", "current_status_id"],
            right_on=["issue_id", "to_status_id"],
            how="left",
        )
        .with_columns(
            [
                # If we have a last transition, age = now - last_change
                # If no transition (issue created in this status), age = now - created
                pl.coalesce(
                    [pl.col("last_status_change_at"), pl.col("jira_created_at")]
                )
                .cast(pl.Datetime("us", "UTC"))
                .alias("status_start_date")
            ]
        )
        .with_columns(
            [
                (
                    (
                        pl.lit(now).cast(pl.Datetime("us", "UTC"))
                        - pl.col("status_start_date")
                    ).dt.total_seconds()
                    / 86400.0
                ).alias("age_in_status_days")
            ]
        )
        .select(
            [
                pl.col("id").alias("issue_id"),
                pl.col("project_id"),
                pl.col("key").alias("issue_key"),
                pl.col("type_name").alias("issue_type"),
                pl.col("current_status_id"),
                pl.col("commitment_start_at"),
                pl.col("age_days"),
                pl.col("age_in_status_days"),
            ]
        )
    )

    return aging_df


def _empty_aging_df() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "id": pl.Utf8,
            "project_id": pl.Utf8,
            "issue_key": pl.Utf8,
            "issue_type": pl.Utf8,
            "current_status_id": pl.Utf8,
            "commitment_start_at": pl.Datetime,
            "age_days": pl.Float64,
            "age_in_status_days": pl.Float64,
        }
    )
