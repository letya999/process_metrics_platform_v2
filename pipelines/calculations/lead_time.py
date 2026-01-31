"""
Lead Time Metrics Calculation (Python/Polars Implementation)

This module contains the business logic for calculating Lead Time metrics.
It replaces the complex SQL Materialized View logic with debuggable Python code.

Key Metrics:
- Lead Time: Time from "In Progress" to "Done" (in days)
- Commitment points: When issue enters "In Progress" (start) and "Done" (end)
- Histogram bins: Distribution of lead times

Business Rules:
1. commitment_start = FIRST time issue entered columns between "In Progress" and "Done"
   - Fallback: Use issue.jira_created_at if no transition event found
2. commitment_end = FIRST time issue entered "Done" column (after leaving it last time)
   - Handles cases where issue moved Done → In Progress → Done again
   - Fallback: Use issue.jira_resolved_at if no transition event found
3. Lead Time = end - start (in days)
4. All issues with either resolved_at or Done transition are included
"""

from typing import Dict, List, Tuple

import polars as pl


def identify_commitment_points(
    boards_df: pl.DataFrame, board_columns_df: pl.DataFrame
) -> Dict[str, any]:
    """
    Identify "In Progress" (start) and "Done" (end) columns from board configuration.

    Args:
        boards_df: DataFrame of boards
        board_columns_df: DataFrame of board columns with status mappings (must include position)

    Returns:
        Dict with:
        - start_status_ids: List of status IDs in "In Progress" column
        - end_status_ids: List of status IDs in "Done" column
        - middle_status_ids: List of ALL status IDs between start and end columns
        - start_position: Position of start column
        - end_position: Position of end column

    Example:
        >>> points = identify_commitment_points(boards, columns)
        >>> print(f"Found {len(points['start_status_ids'])} start statuses")
    """
    if board_columns_df.is_empty():
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": None,
            "end_position": None,
        }

    # Find "In Progress" columns (start commitment point)
    start_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("in progress")
        | pl.col("name").str.to_lowercase().str.contains("в работе")  # Russian
    )

    # Find "Done" columns (end commitment point)
    end_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("done")
        | pl.col("name").str.to_lowercase().str.contains("готово")  # Russian
    )

    if start_columns.is_empty() or end_columns.is_empty():
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": None,
            "end_position": None,
        }

    # Get positions
    start_position = start_columns["position"].min()
    end_position = end_columns["position"].min()

    # Validate that start comes before end
    if start_position >= end_position:
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": None,
            "end_position": None,
        }

    # Get all status IDs for start and end columns
    start_status_ids = start_columns["status_id"].unique().drop_nulls().to_list()
    end_status_ids = end_columns["status_id"].unique().drop_nulls().to_list()

    # Get ALL status IDs in columns between start (inclusive) and end (exclusive)
    # This matches old SQL logic: cs.order_num >= p.start_order AND cs.order_num < p.end_order
    middle_columns = board_columns_df.filter(
        (pl.col("position") >= start_position) & (pl.col("position") < end_position)
    )
    middle_status_ids = middle_columns["status_id"].unique().drop_nulls().to_list()

    return {
        "start_status_ids": start_status_ids,
        "end_status_ids": end_status_ids,
        "middle_status_ids": middle_status_ids,
        "start_position": start_position,
        "end_position": end_position,
    }


def calculate_lead_time_per_issue(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    middle_status_ids: List[str],
    end_status_ids: List[str],
) -> pl.DataFrame:
    """
    Calculate Lead Time (commitment_start → commitment_end) for each issue.

    Business Rules (matching old SQL implementation):
    1. commitment_end:
       - Find LAST time issue LEFT "Done" column (last_left_end)
       - Find FIRST time issue entered "Done" column AFTER last_left_end
       - Fallback: Use issue.jira_resolved_at if no transition found
    2. commitment_start:
       - Find FIRST time issue entered ANY column between "In Progress" and "Done"
       - Must be BEFORE commitment_end
       - Fallback: Use issue.jira_created_at if no transition found
    3. Lead Time = end - start (in days)
    4. Includes ALL issues with resolved_at or Done transition

    Args:
        issues_df: Issue details (id, project_id, key, jira_created_at, jira_resolved_at)
        status_changelog_df: Status change history (issue_id, from_status_id, to_status_id, changed_at)
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
    end_events_from_changelog = (
        done_transitions.group_by("issue_id")
        .agg(pl.col("changed_at").min().alias("end_at_from_changelog"))
    )

    # Join with issues and use COALESCE(changelog_event, resolved_at)
    issues_with_end = issues_df.join(
        end_events_from_changelog, left_on="id", right_on="issue_id", how="left"
    ).with_columns(
        [
            pl.coalesce(
                [pl.col("end_at_from_changelog"), pl.col("jira_resolved_at")]
            ).alias("commitment_end_at")
        ]
    ).filter(
        pl.col("commitment_end_at").is_not_null()
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
    # Step 3: Find commitment_start (FIRST entry to middle columns, BEFORE end)
    # ==============================================================

    # Find all transitions TO any status in the middle range (In Progress to Done, exclusive)
    start_transitions = status_changelog_df.filter(
        pl.col("to_status_id").is_in(middle_status_ids)
    )

    # Join with commitment_end to filter only transitions BEFORE end
    start_transitions_before_end = start_transitions.join(
        issues_with_end.select(["id", "commitment_end_at"]),
        left_on="issue_id",
        right_on="id",
        how="inner",
    ).filter(
        pl.col("changed_at") <= pl.col("commitment_end_at")
    )

    # Get FIRST transition to middle columns (per issue)
    start_events_from_changelog = (
        start_transitions_before_end.group_by("issue_id")
        .agg(pl.col("changed_at").min().alias("start_at_from_changelog"))
    )

    # Join with issues_with_end and use COALESCE(changelog_event, created_at)
    lead_time = (
        issues_with_end.join(
            start_events_from_changelog, left_on="id", right_on="issue_id", how="left"
        )
        .with_columns(
            [
                pl.coalesce(
                    [pl.col("start_at_from_changelog"), pl.col("jira_created_at")]
                ).alias("commitment_start_at")
            ]
        )
        .filter(
            pl.col("commitment_start_at").is_not_null()
            & (pl.col("commitment_end_at") >= pl.col("commitment_start_at"))
        )
        .with_columns(
            [
                # Calculate lead time in days
                (
                    (pl.col("commitment_end_at") - pl.col("commitment_start_at"))
                    .dt.total_seconds()
                    / 86400.0
                ).alias("lead_time_days")
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

    Example:
        >>> bins_df = calculate_histogram_bins(lead_time_df)
        >>> print(bins_df.sort("bin_number"))
        # bin 1: 50 tickets, bin 2: 30 tickets, etc.
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

    Computes:
    - Average lead time
    - Median (P50)
    - P90 (90th percentile)
    - Total issue count

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


def calculate_lead_time_facts(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Main orchestration function: Calculate Lead Time facts.

    This function implements the complete Lead Time calculation logic,
    replacing the complex SQL Materialized View with debuggable Python code.

    Args:
        issues_df: Issue details (must include: id, project_id, key, type_name,
                   jira_created_at, jira_resolved_at)
        status_changelog_df: Status change history (must include: issue_id,
                            from_status_id, to_status_id, changed_at)
        boards_df: Board definitions
        board_columns_df: Board column configuration (must include: id, board_id,
                         name, position, status_id)

    Returns:
        DataFrame ready to insert into metrics.fact_lead_time

    Example:
        >>> lead_time_df = calculate_lead_time_facts(
        ...     issues, status_changelog, boards, board_columns
        ... )
        >>> print(lead_time_df.describe())
    """
    # Step 1: Identify commitment points (start and end statuses)
    points = identify_commitment_points(boards_df, board_columns_df)

    if not points["middle_status_ids"] or not points["end_status_ids"]:
        # No valid board configuration - return empty DataFrame
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

    # Step 2: Calculate lead time per issue
    lead_time = calculate_lead_time_per_issue(
        issues_df,
        status_changelog_df,
        points["middle_status_ids"],
        points["end_status_ids"],
    )

    return lead_time
