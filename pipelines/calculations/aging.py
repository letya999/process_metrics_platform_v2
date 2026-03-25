"""
Work Item Aging Calculation (Python/Polars Implementation)

This module calculates Work Item Aging for active (unresolved) issues.
Aging = Now - Commitment Start (Entry to "In Progress").
"""

from datetime import datetime, timezone
from typing import List

import polars as pl

from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_heuristic,
)


def _to_utc_datetime(value: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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

    # 3. Resolve commitment points per project to avoid cross-project status leakage.
    # Fall back to global heuristic only for projects without board metadata.
    start_events_by_project = []
    if not status_changelog_df.is_empty():
        active_project_ids = active_issues["project_id"].unique().to_list()

        for project_id in active_project_ids:
            project_issue_ids = active_issues.filter(
                pl.col("project_id") == project_id
            )["id"].to_list()
            if not project_issue_ids:
                continue

            project_board_ids = boards_df.filter(pl.col("project_id") == project_id)[
                "id"
            ].to_list()
            project_middle_status_ids = []
            project_end_status_ids = []

            for board_id in project_board_ids:
                points = identify_commitment_points_heuristic(
                    board_columns_df.filter(pl.col("board_id") == board_id)
                )
                project_middle_status_ids.extend(points.get("middle_status_ids", []))
                project_end_status_ids.extend(points.get("end_status_ids", []))

            if not project_middle_status_ids and not project_end_status_ids:
                fallback = identify_commitment_points_heuristic(board_columns_df)
                project_middle_status_ids = fallback.get("middle_status_ids", [])
                project_end_status_ids = fallback.get("end_status_ids", [])

            project_middle_status_ids = list(set(project_middle_status_ids))
            project_end_status_ids = list(set(project_end_status_ids))

            if not project_middle_status_ids:
                continue

            project_changelog = status_changelog_df.filter(
                pl.col("issue_id").is_in(project_issue_ids)
            )
            if project_changelog.is_empty():
                continue

            # a. Find LAST time issue LEFT the "Done" column (to handle Done -> In Progress)
            # Note: from_status_id may be NULL (e.g. 30% of Jira changelog for initial status)
            last_left_done = (
                project_changelog.filter(
                    pl.col("from_status_id").is_in(project_end_status_ids)
                    & ~pl.col("to_status_id").is_in(project_end_status_ids)
                )
                .group_by("issue_id")
                .agg(pl.col("changed_at").max().alias("last_left_done_at"))
            )

            # b. Find FIRST entry to In Progress (middle) AFTER that exit
            start_transitions = project_changelog.filter(
                pl.col("to_status_id").is_in(project_middle_status_ids)
            )

            if not last_left_done.is_empty():
                start_transitions = start_transitions.join(
                    last_left_done, on="issue_id", how="left"
                ).filter(
                    pl.col("last_left_done_at").is_null()
                    | (pl.col("changed_at") > pl.col("last_left_done_at"))
                )

            start_events = start_transitions.group_by("issue_id").agg(
                pl.col("changed_at").min().alias("start_at_from_changelog")
            )
            if not start_events.is_empty():
                start_events_by_project.append(start_events)

    if start_events_by_project:
        active_issues = active_issues.join(
            pl.concat(start_events_by_project),
            left_on="id",
            right_on="issue_id",
            how="left",
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


def calculate_blocked_time(
    issues_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    blocked_field_key_id: str,
    now_date: datetime = None,
) -> pl.DataFrame:
    """
    Calculate total hours an issue was in "blocked" state.
    """
    if now_date is None:
        now_date = datetime.now(timezone.utc)
    now_date = _to_utc_datetime(now_date)

    if field_value_changelog_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "blocked_hours": pl.Float64,
            }
        )

    # Get changes for blocked field
    changes = field_value_changelog_df.filter(
        pl.col("field_key_id") == blocked_field_key_id
    ).sort(["issue_id", "change_time"])

    if changes.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "blocked_hours": pl.Float64,
            }
        )

    # Find intervals where value is 'true'
    # We need to pair 'true' with subsequent change
    def is_blocked_val(val):
        if val is None:
            return False
        v = str(val).lower()
        return v in ["true", "1", "yes", "blocked"]

    # We iterate over issues to find intervals
    issue_ids = changes["issue_id"].unique().to_list()
    all_results = []

    for issue_id in issue_ids:
        issue_changes = changes.filter(pl.col("issue_id") == issue_id).to_dicts()
        total_seconds = 0.0
        blocked_since = None

        for change in issue_changes:
            change_time = _to_utc_datetime(change["change_time"])
            new_val_blocked = is_blocked_val(change["new_value"])
            old_val_blocked = is_blocked_val(change["old_value"])

            if new_val_blocked and not old_val_blocked:
                # Started being blocked
                blocked_since = change_time
            elif not new_val_blocked and old_val_blocked:
                # Stopped being blocked
                if blocked_since:
                    total_seconds += (change_time - blocked_since).total_seconds()
                    blocked_since = None

        # If still blocked
        if blocked_since:
            total_seconds += (now_date - blocked_since).total_seconds()

        all_results.append(
            {"issue_id": issue_id, "blocked_hours": round(total_seconds / 3600.0, 2)}
        )

    result = pl.DataFrame(all_results)

    # Join with issues to get project_id and key
    issues = issues_df.select(["id", "project_id", "key"]).rename(
        {"id": "issue_id", "key": "issue_key"}
    )
    result = issues.join(result, on="issue_id", how="inner")

    return result


def calculate_stale_days(
    issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    now_date: datetime = None,
) -> pl.DataFrame:
    """
    Calculate days since last update for open issues.
    """
    _ = issue_status_changelog_df  # Reserved for future stale logic based on status transitions.
    if now_date is None:
        now_date = datetime.now(timezone.utc)
    now_date = _to_utc_datetime(now_date)

    # Filter issues: not in done category
    # We need issue_statuses to know category, but if not available, use done_status_ids
    open_issues = issues_df.filter(
        ~pl.col("status_id")
        .cast(pl.Utf8)
        .str.to_lowercase()
        .is_in([s.lower() for s in done_status_ids])
    )

    if open_issues.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "current_status_id": pl.Utf8,
                "stale_days": pl.Float64,
            }
        )

    result = (
        open_issues.with_columns(
            pl.col("updated_at")
            .map_elements(_to_utc_datetime, return_dtype=pl.Datetime("us", None))
            .cast(pl.Datetime("us", "UTC"))
            .alias("updated_at_utc")
        )
        .with_columns(
            ((pl.lit(now_date) - pl.col("updated_at_utc")).dt.total_seconds() / 86400.0)
            .round(2)
            .alias("stale_days")
        )
        .rename(
            {"id": "issue_id", "key": "issue_key", "status_id": "current_status_id"}
        )
    )

    return result.select(
        ["project_id", "issue_id", "issue_key", "current_status_id", "stale_days"]
    )
