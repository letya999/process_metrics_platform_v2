"""
Cumulative Flow Diagram (CFD) Calculation

This module calculates data for Cumulative Flow Diagrams - showing how many
issues are in each status on each day.

Key Metrics:
- Daily snapshot of issue counts per status
- Issue distribution across workflow stages
- Flow trends over time

Business Rules:
1. For each day, count how many issues were in each status
2. Use status changelog to determine issue status on any given day
3. Include all statuses configured in board columns
4. Calculate for configurable date range (default: last 90 days)
"""

from datetime import datetime, timedelta

import polars as pl


def calculate_cumulative_flow_diagram(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
    days_back: int = 90,
) -> pl.DataFrame:
    """
    Calculate Cumulative Flow Diagram data (daily issue counts per status).

    Args:
        issues_df: Issue details (id, project_id, status_id, jira_created_at)
        status_changelog_df: Status change history
        issue_statuses_df: Status definitions (id, project_id, name, category)
        boards_df: Board definitions
        board_columns_df: Board column configuration
        days_back: Number of days to look back (default: 90)

    Returns:
        DataFrame: [project_id, date, status_name, status_category,
                    issue_count, column_position]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "date": pl.Date,
                "status_name": pl.Utf8,
                "status_category": pl.Utf8,
                "issue_count": pl.Int64,
                "column_position": pl.Int32,
            }
        )

    # Generate date range (from days_back until today)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)

    date_range = pl.DataFrame(
        {
            "date": pl.date_range(start_date, end_date, interval="1d", eager=True).cast(
                pl.Date
            )
        }
    )

    # Get distinct projects from issues
    relevant_projects = issues_df.select("project_id").unique()

    # Start with all statuses for these projects
    all_statuses = issue_statuses_df.join(
        relevant_projects, on="project_id", how="inner"
    )

    # Use board configuration to define/filter statuses and add positions
    if not board_columns_df.is_empty():
        status_positions = (
            board_columns_df.select(["status_id", "position"])
            .sort("position")
            .unique(subset=["status_id"], keep="first")
            .rename({"position": "column_position"})
        )

        # Inner join to restrict to board columns and map positions
        project_statuses = all_statuses.join(
            status_positions, left_on="id", right_on="status_id", how="inner"
        ).select(
            [
                "project_id",
                pl.col("id").alias("status_id"),
                pl.col("name").alias("status_name"),
                pl.col("category").alias("status_category"),
                "column_position",
            ]
        )
    else:
        # Default: use all project statuses
        project_statuses = all_statuses.select(
            [
                "project_id",
                pl.col("id").alias("status_id"),
                pl.col("name").alias("status_name"),
                pl.col("category").alias("status_category"),
            ]
        ).with_columns(pl.lit(None).cast(pl.Int32).alias("column_position"))

    project_statuses = project_statuses.unique()

    # Create cartesian product: all dates × all project-status combinations
    date_status_grid = date_range.join(project_statuses, how="cross")

    # For each date, determine the status of each issue on that date
    daily_statuses = _calculate_issue_status_on_dates(
        issues_df, status_changelog_df, date_range
    )

    # Fix potential list type in status_id (Polars may infer list from aggregation)
    if daily_statuses.schema["status_id"] == pl.List(pl.Utf8) or isinstance(
        daily_statuses.schema["status_id"], pl.List
    ):
        daily_statuses = daily_statuses.with_columns(
            pl.col("status_id").list.first().cast(pl.Utf8)
        )
    else:
        daily_statuses = daily_statuses.with_columns(pl.col("status_id").cast(pl.Utf8))

    # Count issues per project-status-date
    daily_counts = daily_statuses.group_by(["project_id", "date", "status_id"]).agg(
        [pl.len().alias("issue_count")]
    )

    # Join with full grid to ensure all dates/statuses are present
    cfd_data = (
        date_status_grid.join(
            daily_counts,
            on=["project_id", "date", "status_id"],
            how="left",
            coalesce=True,
        )
        # Fill missing counts with 0
        .with_columns([pl.col("issue_count").fill_null(0)])
        # Group by status name to merge duplicate status names in same project
        .group_by(["project_id", "date", "status_name"])
        .agg(
            [
                pl.col("status_category").first(),
                pl.col("issue_count").sum(),
                pl.col("column_position").min(),
            ]
        )
        .select(
            [
                "project_id",
                "date",
                "status_name",
                "status_category",
                "issue_count",
                "column_position",
            ]
        )
        .sort(["project_id", "date", "column_position"])
    )

    return cfd_data


def _calculate_issue_status_on_dates(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    date_range_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine the status of each issue on each date.

    Logic:
    1. For each issue, find the status it had on each date
    2. Use status changelog to track status changes over time
    3. If no changelog entry before date, use issue creation status

    Args:
        issues_df: Issues with creation dates and current status
        status_changelog_df: Status change history
        date_range_df: Date range to calculate for

    Returns:
        DataFrame: [issue_id, project_id, date, status_id]
    """
    if issues_df.is_empty() or date_range_df.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "date": pl.Date,
                "status_id": pl.Utf8,
            }
        )

    # Create cartesian product: all issues × all dates
    issue_date_grid = issues_df.select(
        ["id", "project_id", "status_id", "jira_created_at"]
    ).join(date_range_df, how="cross")

    # Filter out dates before issue was created
    issue_date_grid = issue_date_grid.filter(
        pl.col("date") >= pl.col("jira_created_at").cast(pl.Date)
    )

    if status_changelog_df.is_empty():
        # No changelog - all issues keep their current status
        return issue_date_grid.select(
            [
                pl.col("id").alias("issue_id"),
                "project_id",
                "date",
                "status_id",
            ]
        )

    # For each issue-date pair, find the most recent status change before that date
    status_on_date = (
        issue_date_grid.join(
            status_changelog_df.select(["issue_id", "to_status_id", "changed_at"]),
            left_on="id",
            right_on="issue_id",
            how="left",
        )
        # Keep only changelog entries before or on the date
        .filter(
            pl.col("changed_at").is_null()
            | (pl.col("changed_at").cast(pl.Date) <= pl.col("date"))
        )
        # For each issue-date, get the most recent status change
        .sort(["id", "date", "changed_at"], descending=[False, False, True])
        .group_by(["id", "date"])
        .agg(
            [
                pl.col("project_id").first(),
                # Use status from changelog if exists, otherwise use current status
                pl.coalesce(
                    [pl.col("to_status_id").first(), pl.col("status_id").first()]
                )
                .cast(pl.Utf8)
                .alias("status_id"),
            ]
        )
        .select(
            [
                pl.col("id").alias("issue_id"),
                "project_id",
                "date",
                "status_id",
            ]
        )
    )

    return status_on_date


def calculate_cfd_aggregates(cfd_df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate aggregate metrics from CFD data.

    Args:
        cfd_df: Daily CFD data

    Returns:
        DataFrame: [project_id, status_name, avg_daily_count,
                    min_count, max_count, trend]
    """
    if cfd_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "status_name": pl.Utf8,
                "avg_daily_count": pl.Float64,
                "min_count": pl.Int64,
                "max_count": pl.Int64,
                "trend": pl.Utf8,
            }
        )

    # Calculate basic statistics per status
    aggregates = (
        cfd_df.group_by(["project_id", "status_name"])
        .agg(
            [
                pl.col("issue_count").mean().round(2).alias("avg_daily_count"),
                pl.col("issue_count").min().alias("min_count"),
                pl.col("issue_count").max().alias("max_count"),
            ]
        )
        .sort(["project_id", "status_name"])
    )

    # Calculate trend (increasing/decreasing/stable)
    # Compare first week average vs last week average
    trends = (
        cfd_df.sort(["project_id", "status_name", "date"])
        .group_by(["project_id", "status_name"])
        .agg(
            [
                # First 7 days average
                pl.col("issue_count").head(7).mean().alias("first_week_avg"),
                # Last 7 days average
                pl.col("issue_count").tail(7).mean().alias("last_week_avg"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("last_week_avg") > pl.col("first_week_avg") * 1.1)
                .then(pl.lit("increasing"))
                .when(pl.col("last_week_avg") < pl.col("first_week_avg") * 0.9)
                .then(pl.lit("decreasing"))
                .otherwise(pl.lit("stable"))
                .alias("trend")
            ]
        )
        .select(["project_id", "status_name", "trend"])
    )

    # Join aggregates with trends
    result = aggregates.join(trends, on=["project_id", "status_name"], how="left")

    return result
