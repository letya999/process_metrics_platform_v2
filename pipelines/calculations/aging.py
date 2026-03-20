"""
Work Item Aging Calculation (Python/Polars Implementation)

This module calculates Work Item Aging for active (unresolved) issues.
Aging = Now - Commitment Start (Entry to "In Progress").
"""

from datetime import datetime, timezone

import polars as pl

from pipelines.calculations.lead_time import identify_commitment_points


def calculate_work_item_aging_facts(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate Work Item Aging for all ACTIVE (unresolved) issues.

    Args:
        issues_df: Issues [id, project_id, external_key, type_name, status_id, jira_created_at]
        status_changelog_df: Status history [issue_id, to_status_id, changed_at]
        boards_df: Boards
        board_columns_df: Board columns with status mapping
        issue_statuses_df: Status definitions [id, category, name]

    Returns:
        DataFrame: [issue_id, project_id, issue_key, issue_type, current_status,
                    commitment_start_at, age_days, age_in_status_days]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "issue_type": pl.Utf8,
                "current_status": pl.Utf8,
                "commitment_start_at": pl.Datetime,
                "age_days": pl.Float64,
                "age_in_status_days": pl.Float64,
            }
        )

    # 1. Join issues with statuses to get category and name
    issues_with_status = issues_df.join(
        issue_statuses_df.select(["id", "category", "name"]),
        left_on="status_id",
        right_on="id",
        how="inner",
    ).rename({"name": "current_status"})

    # 2. Filter to UNRESOLVED (active) issues
    # We define "active" as anything not in "done" category
    active_issues = issues_with_status.filter(pl.col("category") != "done")

    if active_issues.is_empty():
        return pl.DataFrame()

    # 3. Identify commitment points (In Progress)
    points = identify_commitment_points(boards_df, board_columns_df)
    middle_status_ids = points["middle_status_ids"]

    # 4. Find commitment start for each active issue
    if not status_changelog_df.is_empty() and middle_status_ids:
        # FIRST entry to any column between "In Progress" and "Done"
        start_transitions = status_changelog_df.filter(
            pl.col("to_status_id").is_in(middle_status_ids)
        )

        start_events = start_transitions.group_by("issue_id").agg(
            pl.col("changed_at").min().alias("start_at_from_changelog")
        )

        active_issues = active_issues.join(
            start_events, left_on="id", right_on="issue_id", how="left"
        )
    else:
        active_issues = active_issues.with_columns(
            pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("start_at_from_changelog")
        )

    now = datetime.now(timezone.utc)

    # 5. Calculate metrics
    aging_df = active_issues.with_columns(
        [
            # commitment_start_at = COALESCE(start_at_from_changelog, jira_created_at)
            pl.coalesce(
                [pl.col("start_at_from_changelog"), pl.col("jira_created_at")]
            ).alias("commitment_start_at")
        ]
    ).with_columns(
        [
            # Total Age in days
            ((pl.lit(now) - pl.col("commitment_start_at")).dt.total_seconds() / 86400.0)
            .round(2)
            .alias("age_days")
        ]
    )

    # 6. Calculate age in current status
    if not status_changelog_df.is_empty():
        # Last entry to CURRENT status
        # Note: This is a simplification. Ideally check if it's entry to the EXACT current_status_id
        last_status_entry = status_changelog_df.group_by("issue_id").agg(
            pl.col("changed_at").max().alias("last_status_change_at")
        )

        aging_df = aging_df.join(
            last_status_entry, left_on="id", right_on="issue_id", how="left"
        )

        aging_df = aging_df.with_columns(
            [
                pl.coalesce(
                    [pl.col("last_status_change_at"), pl.col("jira_created_at")]
                ).alias("status_entry_at")
            ]
        ).with_columns(
            [
                ((pl.lit(now) - pl.col("status_entry_at")).dt.total_seconds() / 86400.0)
                .round(2)
                .alias("age_in_status_days")
            ]
        )
    else:
        aging_df = aging_df.with_columns(pl.lit(0.0).alias("age_in_status_days"))

    return aging_df.select(
        [
            pl.col("id").alias("issue_id"),
            pl.col("project_id"),
            pl.col("key").alias("issue_key"),
            pl.col("type_name").alias("issue_type"),
            "current_status",
            "commitment_start_at",
            "age_days",
            "age_in_status_days",
        ]
    )
