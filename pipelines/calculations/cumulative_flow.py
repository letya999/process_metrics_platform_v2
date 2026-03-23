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
    Calculate Cumulative Flow Diagram data (daily issue counts per board column).

    Behavior matches Jira Metrics browser extension:
    - Active columns (non-done): snapshot count of issues in that status on each day.
    - Done columns: INCREMENTAL count - only issues that first reached a "done"
      category status WITHIN the calculation window (start_date to today).
      This prevents historical completions from inflating the Done band and makes
      the chart start at 0 for Done on the first day, just like Jira Metrics.

    Each board column is one row per date (multiple statuses in the same column
    are summed together, so "Done" + "Canceled" → single "Done" row).

    Returns:
        DataFrame: [project_id, date, status_id, status_name, status_category,
                    issue_count, column_id, column_position]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "date": pl.Date,
                "status_id": pl.Utf8,
                "status_name": pl.Utf8,
                "status_category": pl.Utf8,
                "issue_count": pl.Int64,
                "column_id": pl.Utf8,
                "column_position": pl.Int32,
            }
        )

    # Generate date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    date_range = pl.DataFrame(
        {
            "date": pl.date_range(start_date, end_date, interval="1d", eager=True).cast(
                pl.Date
            )
        }
    )
    cfd_start_date = start_date

    # Use board configuration to define/filter statuses and add positions/IDs
    if not board_columns_df.is_empty():
        column_mapping = board_columns_df.select(
            ["id", "status_id", "position"]
        ).rename({"id": "column_id", "position": "column_position"})

        project_statuses = issue_statuses_df.join(
            column_mapping, left_on="id", right_on="status_id", how="inner"
        ).select(
            [
                "project_id",
                pl.col("id").alias("status_id"),
                pl.col("name").alias("status_name"),
                pl.col("category").alias("status_category"),
                "column_id",
                "column_position",
            ]
        )
    else:
        project_statuses = issue_statuses_df.select(
            [
                "project_id",
                pl.col("id").alias("status_id"),
                pl.col("name").alias("status_name"),
                pl.col("category").alias("status_category"),
            ]
        ).with_columns(
            [
                pl.lit(None).cast(pl.Utf8).alias("column_id"),
                pl.lit(None).cast(pl.Int32).alias("column_position"),
            ]
        )

    project_statuses = project_statuses.unique()
    date_status_grid = date_range.join(project_statuses, how="cross")

    daily_statuses = _calculate_issue_status_on_dates(
        issues_df, status_changelog_df, date_range
    )

    # Cast status_id to string and handle potential list type
    if daily_statuses.schema["status_id"] == pl.List(pl.Utf8) or isinstance(
        daily_statuses.schema["status_id"], pl.List
    ):
        daily_statuses = daily_statuses.with_columns(
            pl.col("status_id").list.first().cast(pl.Utf8)
        )
    else:
        daily_statuses = daily_statuses.with_columns(pl.col("status_id").cast(pl.Utf8))

    # Incremental Done: for "done" category statuses, only count issues that
    # first reached a done status WITHIN the CFD window (>= cfd_start_date).
    # Issues already Done before the window start are excluded from Done counts,
    # matching Jira Metrics extension behavior where Done starts at 0.
    done_status_ids = (
        project_statuses.filter(pl.col("status_category") == "done")["status_id"]
        .unique()
        .to_list()
    )

    if done_status_ids:
        # First done date must come from the full changelog, not just the window.
        # daily_statuses only covers the window, so its minimum "Done" date is
        # always the window start for pre-existing Done issues - useless for filtering.
        first_done_from_changelog = (
            status_changelog_df.filter(pl.col("to_status_id").is_in(done_status_ids))
            .group_by("issue_id")
            .agg(pl.col("changed_at").cast(pl.Date).min().alias("first_done_date"))
        )

        # Issues created directly in Done (no changelog entry for Done transition)
        # get first_done_date = their creation date (always before any CFD window).
        issues_created_in_done = (
            issues_df.filter(pl.col("status_id").is_in(done_status_ids))
            .join(
                first_done_from_changelog,
                left_on="id",
                right_on="issue_id",
                how="left",
            )
            .filter(pl.col("first_done_date").is_null())
            .select(
                [
                    pl.col("id").alias("issue_id"),
                    pl.col("jira_created_at").cast(pl.Date).alias("first_done_date"),
                ]
            )
        )

        first_done_per_issue = pl.concat(
            [first_done_from_changelog, issues_created_in_done]
        )

        daily_statuses = (
            daily_statuses.join(first_done_per_issue, on="issue_id", how="left")
            .filter(
                # Keep non-done issues always
                pl.col("status_id").is_in(done_status_ids).not_()
                # Keep done issues only if they first entered Done within the CFD window
                | (pl.col("first_done_date") >= pl.lit(cfd_start_date))
            )
            .drop("first_done_date")
        )

    daily_counts = daily_statuses.group_by(["project_id", "date", "status_id"]).agg(
        [pl.len().cast(pl.Int64).alias("issue_count")]
    )

    cfd_data = (
        date_status_grid.join(
            daily_counts,
            on=["project_id", "date", "status_id"],
            how="left",
            coalesce=True,
        )
        .with_columns([pl.col("issue_count").fill_null(0)])
        # Aggregate by column (not individual status) so that multiple statuses
        # mapped to the same board column (e.g. "Done" + "Canceled" → "Done")
        # produce a single row per date/column instead of duplicate rows.
        .group_by(["project_id", "date", "column_id"])
        .agg(
            [
                pl.col("status_id").first(),
                pl.col("status_name").first(),
                pl.col("status_category").first(),
                pl.col("issue_count").sum(),
                pl.col("column_position").min(),
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
