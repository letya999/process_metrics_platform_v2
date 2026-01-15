"""
Lead Time Metrics Calculation (Python/Polars Implementation)

This module contains the business logic for calculating Lead Time metrics.
It replaces the complex SQL Materialized View logic with debuggable Python code.

Key Metrics:
- Lead Time: Time from "In Progress" to "Done" (in days)
- Commitment points: When issue enters "In Progress" (start) and "Done" (end)
- Histogram bins: Distribution of lead times

Business Rules:
1. commitment_start = FIRST time issue entered "In Progress" column
2. commitment_end = FIRST time issue entered "Done" column (after start)
3. Lead Time = end - start (in days)
4. Only issues with both start and end are included
"""

from typing import List, Tuple

import polars as pl


def identify_commitment_points(
    boards_df: pl.DataFrame, board_columns_df: pl.DataFrame
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Identify "In Progress" (start) and "Done" (end) columns from board configuration.

    Args:
        boards_df: DataFrame of boards
        board_columns_df: DataFrame of board columns with status mappings

    Returns:
        Tuple of (start_columns_df, end_columns_df) each with status_id column

    Example:
        >>> start_cols, end_cols = identify_commitment_points(boards, columns)
        >>> print(f"Found {len(start_cols)} start statuses, {len(end_cols)} end statuses")
    """
    if board_columns_df.is_empty():
        return pl.DataFrame(), pl.DataFrame()

    # Find "In Progress" columns
    start_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("in progress")
        | pl.col("name").str.to_lowercase().str.contains("в работе")  # Russian
    )

    # Find "Done" columns
    end_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("done")
        | pl.col("name").str.to_lowercase().str.contains("готово")  # Russian
    )

    return start_columns, end_columns


def calculate_lead_time_per_issue(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    start_status_ids: List[str],
    end_status_ids: List[str],
) -> pl.DataFrame:
    """
    Calculate Lead Time (commitment_start → commitment_end) for each issue.

    Business Rules:
    1. commitment_start = FIRST time issue entered "In Progress" column
    2. commitment_end = FIRST time issue entered "Done" column (after start)
    3. Lead Time = end - start (in days)
    4. Only issues with both start and end events are included

    Args:
        issues_df: Issue details (id, project_id, key)
        status_changelog_df: Status change history
        start_status_ids: List of "In Progress" status IDs
        end_status_ids: List of "Done" status IDs

    Returns:
        DataFrame: [issue_id, project_id, commitment_start_at,
                    commitment_end_at, lead_time_days]

    Example:
        >>> lead_time_df = calculate_lead_time_per_issue(
        ...     issues, changelog, ["10001"], ["10002"]
        ... )
        >>> print(lead_time_df.filter(pl.col("lead_time_days") > 10))
    """
    if not start_status_ids or not end_status_ids or status_changelog_df.is_empty():
        # No valid configuration - return empty DataFrame
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "commitment_start_at": pl.Datetime,
                "commitment_end_at": pl.Datetime,
                "lead_time_days": pl.Float64,
            }
        )

    # Step 1: Find first "In Progress" transition per issue
    start_events = (
        status_changelog_df.filter(pl.col("to_status_id").is_in(start_status_ids))
        .group_by("issue_id")
        .agg(pl.col("changed_at").min().alias("commitment_start_at"))
    )

    if start_events.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "commitment_start_at": pl.Datetime,
                "commitment_end_at": pl.Datetime,
                "lead_time_days": pl.Float64,
            }
        )

    # Step 2: Find first "Done" transition per issue (AFTER start)
    end_events = (
        status_changelog_df.join(start_events, on="issue_id", how="inner")
        .filter(
            pl.col("to_status_id").is_in(end_status_ids)
            & (pl.col("changed_at") > pl.col("commitment_start_at"))
        )
        .group_by("issue_id")
        .agg(pl.col("changed_at").min().alias("commitment_end_at"))
    )

    if end_events.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "commitment_start_at": pl.Datetime,
                "commitment_end_at": pl.Datetime,
                "lead_time_days": pl.Float64,
            }
        )

    # Step 3: Combine start and end events with issue details
    lead_time = (
        issues_df.join(start_events, left_on="id", right_on="issue_id", how="inner")
        .join(end_events, left_on="id", right_on="issue_id", how="inner")
        .filter(
            pl.col("commitment_start_at").is_not_null()
            & pl.col("commitment_end_at").is_not_null()
        )
        .with_columns(
            [
                # Calculate lead time in days
                (
                    (
                        pl.col("commitment_end_at") - pl.col("commitment_start_at")
                    ).dt.total_seconds()
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
        issues_df: Issue details
        status_changelog_df: Status change history
        boards_df: Board definitions
        board_columns_df: Board column configuration

    Returns:
        DataFrame ready to insert into metrics.fact_lead_time

    Example:
        >>> lead_time_df = calculate_lead_time_facts(
        ...     issues, status_changelog, boards, board_columns
        ... )
        >>> print(lead_time_df.describe())
    """
    # Step 1: Identify commitment points (start and end statuses)
    start_columns, end_columns = identify_commitment_points(boards_df, board_columns_df)

    if start_columns.is_empty() or end_columns.is_empty():
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

    start_status_ids = start_columns["status_id"].unique().to_list()
    end_status_ids = end_columns["status_id"].unique().to_list()

    # Step 2: Calculate lead time per issue
    lead_time = calculate_lead_time_per_issue(
        issues_df, status_changelog_df, start_status_ids, end_status_ids
    )

    return lead_time
