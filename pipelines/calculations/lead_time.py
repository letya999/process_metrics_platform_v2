"""
Lead Time Metrics Calculation (Python/Polars Implementation)

This module contains the business logic for calculating Lead Time metrics.
It replaces the complex SQL Materialized View logic with debuggable Python code.

Key Metrics:
- Lead Time: Time from "In Progress" to "Done" (in calendar days, ceiling-rounded)
- Commitment points: When issue enters "In Progress" (start) and "Done" (end)
- Histogram bins: Distribution of lead times

Business Rules:
1. commitment_start = FIRST time issue entered columns between "In Progress" and "Done"
   - Must be AFTER the last time the issue left the "Done" column (handles Done→To Do→Done cycles)
   - Issues without any actual commitment zone transition are EXCLUDED (no jira_created_at fallback)
   - This matches Jira Metrics behavior: issues never going through "In Progress" have Lead Time = 0
2. commitment_end = FIRST time issue entered "Done" column (after leaving it last time)
   - Handles cases where issue moved Done → In Progress → Done again
   - Fallback: Use issue.jira_resolved_at if no transition found
3. Lead Time = CEIL(end - start) in whole calendar days
   - Ceiling rounding matches Jira Metrics calendar-day counting
4. Only issues with actual commitment zone transitions are included
"""

from typing import List

import polars as pl


def calculate_lead_time_per_issue(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    middle_status_ids: List[str],
    end_status_ids: List[str],
) -> pl.DataFrame:
    """
    Calculate Lead Time (commitment_start → commitment_end) for each issue.

    Business Rules:
    1. commitment_end:
       - Find LAST time each issue LEFT "Done" column (last_left_done_at)
       - Find FIRST time issue entered "Done" column AFTER last_left_done_at
       - Fallback: Use issue.jira_resolved_at if no transition found
    2. commitment_start:
       - Find FIRST time issue entered ANY column between "In Progress" and "Done"
       - Must be AFTER last_left_done_at (prevents using pre-reset transitions)
       - Must be BEFORE or at commitment_end
       - NO FALLBACK: issues without actual commitment zone transition are excluded
         (matches Jira Metrics: such issues show Lead Time = 0 and are excluded)
    3. Lead Time = CEIL(end - start) in whole calendar days
       - Ceiling rounding matches Jira Metrics calendar-day counting
    4. Only issues with actual commitment zone transitions are included

    Args:
        issues_df: Issue details (id, project_id, key, jira_created_at, jira_resolved_at)
        status_changelog_df: Status change history (issue_id, from_status_id, to_status_id, changed_at)
    # Note: from_status_id may be NULL (e.g. 30% of Jira changelog for initial status)
        middle_status_ids: List of ALL status IDs between "In Progress" and "Done" (inclusive start, exclusive end)
        end_status_ids: List of "Done" status IDs

    Returns:
        DataFrame: [issue_id, project_id, issue_key, issue_type,
                    commitment_start_at, commitment_end_at, lead_time_days]
    """
    if not middle_status_ids or not end_status_ids:
        # No valid configuration - return empty DataFrame
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "issue_type": pl.Utf8,
                "commitment_start_at": pl.Datetime,
                "commitment_end_at": pl.Datetime,
                "lead_time_days": pl.Float64,
            }
        )

    # ==============================================================
    # Step 1: Find LAST time each issue LEFT the "Done" column
    # ==============================================================
    # This handles cases where issue moved: Done → In Progress → Done
    # We need to find the LAST exit from Done to properly calculate the final entry

    last_left_end = None
    if not status_changelog_df.is_empty():
        # Find transitions FROM "Done" status TO non-"Done" status
        left_done_events = (
            status_changelog_df.filter(
                pl.col("from_status_id").is_in(end_status_ids)
                & ~pl.col("to_status_id").is_in(end_status_ids)
            )
            .group_by("issue_id")
            .agg(pl.col("changed_at").max().alias("last_left_done_at"))
        )

        if not left_done_events.is_empty():
            last_left_end = left_done_events

    # ==============================================================
    # Step 2: Find commitment_end (FIRST entry to "Done" after last exit)
    # ==============================================================

    # Find all transitions TO "Done" status
    done_transitions = status_changelog_df.filter(
        pl.col("to_status_id").is_in(end_status_ids)
    )

    # If we have last_left_end info, filter to only transitions AFTER last exit
    if last_left_end is not None:
        done_transitions = done_transitions.join(
            last_left_end, on="issue_id", how="left"
        ).filter(
            pl.col("last_left_done_at").is_null()
            | (pl.col("changed_at") > pl.col("last_left_done_at"))
        )

    # Get FIRST transition to Done (per issue)
    end_events_from_changelog = done_transitions.group_by("issue_id").agg(
        pl.col("changed_at").min().alias("end_at_from_changelog")
    )

    # Join with issues and use COALESCE(changelog_event, resolved_at)
    issues_with_end = (
        issues_df.join(
            end_events_from_changelog, left_on="id", right_on="issue_id", how="left"
        )
        .with_columns(
            [
                pl.coalesce(
                    [pl.col("end_at_from_changelog"), pl.col("jira_resolved_at")]
                ).alias("commitment_end_at")
            ]
        )
        .filter(pl.col("commitment_end_at").is_not_null())
    )

    if issues_with_end.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "issue_type": pl.Utf8,
                "commitment_start_at": pl.Datetime,
                "commitment_end_at": pl.Datetime,
                "lead_time_days": pl.Float64,
            }
        )

    # ==============================================================
    # Step 3: Find commitment_start (FIRST entry to middle columns, AFTER last Done exit, BEFORE end)
    # ==============================================================

    # Find all transitions TO any status in the middle range (In Progress to Done, exclusive)
    start_transitions = status_changelog_df.filter(
        pl.col("to_status_id").is_in(middle_status_ids)
    )

    # Filter to transitions BEFORE commitment_end
    start_transitions_filtered = start_transitions.join(
        issues_with_end.select(["id", "commitment_end_at"]),
        left_on="issue_id",
        right_on="id",
        how="inner",
    ).filter(pl.col("changed_at") <= pl.col("commitment_end_at"))

    # Also restrict to transitions AFTER last Done exit (prevents using pre-reset transitions)
    # This correctly handles Done → To Do → Done cycles
    if last_left_end is not None:
        start_transitions_filtered = start_transitions_filtered.join(
            last_left_end, on="issue_id", how="left"
        ).filter(
            pl.col("last_left_done_at").is_null()
            | (pl.col("changed_at") >= pl.col("last_left_done_at"))
        )

    # Get FIRST transition to middle columns (per issue) - only from actual changelog
    start_events_from_changelog = start_transitions_filtered.group_by("issue_id").agg(
        pl.col("changed_at").min().alias("start_at_from_changelog")
    )

    # Inner join: issues without actual commitment zone transition are excluded
    # (matches Jira Metrics: such issues appear as Lead Time = 0 and are excluded from analysis)
    lead_time = (
        issues_with_end.join(
            start_events_from_changelog, left_on="id", right_on="issue_id", how="inner"
        )
        .rename({"start_at_from_changelog": "commitment_start_at"})
        .filter(
            pl.col("commitment_start_at").is_not_null()
            & (pl.col("commitment_end_at") >= pl.col("commitment_start_at"))
        )
        .with_columns(
            [
                # Calculate lead time as whole calendar days (ceiling) matching Jira Metrics
                (
                    (
                        pl.col("commitment_end_at").cast(pl.Datetime("us", "UTC"))
                        - pl.col("commitment_start_at").cast(pl.Datetime("us", "UTC"))
                    ).dt.total_seconds()
                    / 86400.0
                )
                .ceil()
                .alias("lead_time_days")
            ]
        )
        .select(
            [
                pl.col("id").alias("issue_id"),
                pl.col("project_id"),
                pl.col("key").alias("issue_key"),
                pl.col("type_name").alias("issue_type"),
                "commitment_start_at",
                "commitment_end_at",
                "lead_time_days",
            ]
        )
    )

    return lead_time


def calculate_histogram_bins(lead_time_df: pl.DataFrame) -> pl.DataFrame:
    """
    Create histogram bins (1 day, 2 days, 3 days, etc.) for lead time distribution.

    Args:
        lead_time_df: Lead time facts with lead_time_days column

    Returns:
        DataFrame: [project_id, bin_number, tickets_count]
    """
    if lead_time_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "bin_number": pl.Int32,
                "tickets_count": pl.Int64,
            }
        )

    bins_df = (
        lead_time_df.with_columns(
            [
                # Round up to nearest integer (1.1 days → bin 2)
                pl.col("lead_time_days")
                .ceil()
                .cast(pl.Int32)
                .alias("bin_number")
            ]
        )
        .group_by(["project_id", "bin_number"])
        .agg(pl.count().alias("tickets_count"))
        .sort(["project_id", "bin_number"])
    )

    return bins_df


def calculate_histogram_bins_slice(lead_time_df: pl.DataFrame) -> pl.DataFrame:
    """
    Create histogram bins sliced by issue type.

    Args:
        lead_time_df: Lead time facts with lead_time_days and issue_type columns

    Returns:
        DataFrame: [project_id, issue_type, bin_number, tickets_count]
    """
    if lead_time_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "bin_number": pl.Int32,
                "tickets_count": pl.Int64,
            }
        )

    bins_slice_df = (
        lead_time_df.with_columns(
            [pl.col("lead_time_days").ceil().cast(pl.Int32).alias("bin_number")]
        )
        .group_by(["project_id", "issue_type", "bin_number"])
        .agg(pl.count().alias("tickets_count"))
        .sort(["project_id", "issue_type", "bin_number"])
    )

    return bins_slice_df


def calculate_lead_time_slice(lead_time_df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate aggregated Lead Time metrics sliced by issue type.

    Args:
        lead_time_df: Lead time facts

    Returns:
        DataFrame: [project_id, issue_type, avg_lead_time_days,
                    median_lead_time_days, p90_lead_time_days, total_issues]
    """
    if lead_time_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "avg_lead_time_days": pl.Float64,
                "median_lead_time_days": pl.Float64,
                "p90_lead_time_days": pl.Float64,
                "total_issues": pl.Int64,
            }
        )

    slice_df = (
        lead_time_df.group_by(["project_id", "issue_type"])
        .agg(
            [
                pl.col("lead_time_days").mean().round(2).alias("avg_lead_time_days"),
                pl.col("lead_time_days")
                .quantile(0.5)
                .round(2)
                .alias("median_lead_time_days"),
                pl.col("lead_time_days")
                .quantile(0.9)
                .round(2)
                .alias("p90_lead_time_days"),
                pl.count().alias("total_issues"),
            ]
        )
        .select(
            [
                "project_id",
                "issue_type",
                "avg_lead_time_days",
                "median_lead_time_days",
                "p90_lead_time_days",
                "total_issues",
            ]
        )
    )

    return slice_df
