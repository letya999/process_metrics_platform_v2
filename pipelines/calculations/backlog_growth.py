"""
Backlog Growth Metrics Calculation

This module calculates metrics to assess the growth and health of the product backlog.

Key Metrics:
- Backlog Size: Total number of open issues
- Age Distribution: How long issues have been in backlog
- Stale Issues: Issues not updated for X days
- Backlog Growth Rate: Change in backlog size over time
- Priority Distribution: Breakdown by priority/type

Business Rules:
1. Backlog = all issues NOT in "Done" status category
2. Age = days since issue creation
3. Stale = no updates for 30+ days
4. Growth rate = change over last 4 weeks
"""

from datetime import datetime, timedelta, timezone

import polars as pl


def _calculate_issue_status_on_dates(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    date_range_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine the status of each issue on each date.

    Ported from cumulative_flow.py with addition of last_status_change_at for staleness.
    """
    if issues_df.is_empty() or date_range_df.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "date": pl.Date,
                "status_id": pl.Utf8,
                "jira_created_at": pl.Datetime,
                "last_status_change_at": pl.Datetime,
            }
        )

    # Use internal name 'date'
    if "date" not in date_range_df.columns and "fact_date" in date_range_df.columns:
        date_range = date_range_df.rename({"fact_date": "date"})
    else:
        date_range = date_range_df

    # Create cartesian product: all issues × all dates
    issue_date_grid = issues_df.select(
        ["id", "project_id", "status_id", "jira_created_at"]
    ).join(date_range.select("date"), how="cross")

    # Filter out dates before issue was created
    issue_date_grid = issue_date_grid.filter(
        pl.col("date") >= pl.col("jira_created_at").cast(pl.Date)
    )

    if status_changelog_df is None or status_changelog_df.is_empty():
        # No changelog - all issues keep their current status
        return issue_date_grid.with_columns(
            [
                pl.col("id").alias("issue_id"),
                pl.lit(None).cast(pl.Datetime).alias("last_status_change_at"),
            ]
        ).select(
            [
                "issue_id",
                "project_id",
                "date",
                "status_id",
                "jira_created_at",
                "last_status_change_at",
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
                pl.col("jira_created_at").first(),
                # Use status from changelog if exists, otherwise use current status
                pl.coalesce(
                    [pl.col("to_status_id").first(), pl.col("status_id").first()]
                )
                .cast(pl.Utf8)
                .alias("status_id"),
                pl.col("changed_at").first().alias("last_status_change_at"),
            ]
        )
        .select(
            [
                pl.col("id").alias("issue_id"),
                "project_id",
                "date",
                "status_id",
                "jira_created_at",
                "last_status_change_at",
            ]
        )
    )

    return status_on_date


def calculate_backlog_growth(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    changelog_df: pl.DataFrame = None,
    board_column_statuses_df: pl.DataFrame = None,
    fact_date: datetime = None,
    days_back: int = 90,
    stale_threshold_days: int = 30,
) -> pl.DataFrame:
    """
    Calculate daily backlog health metrics per project.
    Reconstructs history for the last N days.

    Args:
        issues_df: Issue details (id, project_id, status_id, jira_created_at, jira_updated_at, jira_resolved_at)
        issue_statuses_df: Status definitions with categories
        field_values_df: Custom field values
        field_keys_df: Custom field definitions
        changelog_df: Status changelog
        board_column_statuses_df: Mapping of boards/columns to statuses
        fact_date: The end date for calculation (defaults to today)
        days_back: Number of days to look back for history
        stale_threshold_days: Days without updates to consider issue stale (default: 30)

    Returns:
        DataFrame: [project_id, fact_date, total_backlog_size, avg_age_days,
                    stale_issues_count, stale_percentage, oldest_issue_days,
                    created_daily, closed_daily, entered_backlog_count, exited_backlog_count]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "fact_date": pl.Date,
                "total_backlog_size": pl.Int64,
                "avg_age_days": pl.Float64,
                "stale_issues_count": pl.Int64,
                "stale_percentage": pl.Float64,
                "oldest_issue_days": pl.Int64,
                "created_daily": pl.Int64,
                "closed_daily": pl.Int64,
                "entered_backlog_count": pl.Int64,
                "exited_backlog_count": pl.Int64,
            }
        )

    if fact_date is None:
        fact_date = datetime.now(timezone.utc)

    end_date = fact_date.date()
    start_date = end_date - timedelta(days=days_back)

    date_range = pl.DataFrame(
        {
            "date": pl.date_range(start_date, end_date, interval="1d", eager=True).cast(
                pl.Date
            )
        }
    )

    # 1. Reconstruct state for each day
    daily_statuses = _calculate_issue_status_on_dates(
        issues_df, changelog_df, date_range
    )

    # Join with status categories to identify backlog
    daily_issue_categories = daily_statuses.join(
        issue_statuses_df.select(["id", "category"]),
        left_on="status_id",
        right_on="id",
        how="inner",
    )

    # Metrics for the backlog (not "done")
    backlog_daily = daily_issue_categories.filter(pl.col("category") != "done")

    if not backlog_daily.is_empty():
        snapshot_metrics = (
            backlog_daily.with_columns(
                [
                    # Age in days as of that date
                    (
                        (
                            pl.col("date") - pl.col("jira_created_at").cast(pl.Date)
                        ).dt.days()
                    ).alias("age_days"),
                    # Staleness as of that date (no status change for X days)
                    (
                        (
                            pl.col("date")
                            - pl.coalesce(
                                [
                                    pl.col("last_status_change_at").cast(pl.Date),
                                    pl.col("jira_created_at").cast(pl.Date),
                                ]
                            )
                        ).dt.days()
                        > stale_threshold_days
                    ).alias("is_stale"),
                ]
            )
            .group_by(["project_id", "date"])
            .agg(
                [
                    pl.len().cast(pl.Int64).alias("total_backlog_size"),
                    pl.col("age_days").mean().round(2).alias("avg_age_days"),
                    pl.col("is_stale").sum().cast(pl.Int64).alias("stale_issues_count"),
                    pl.col("age_days")
                    .max()
                    .round(0)
                    .cast(pl.Int64)
                    .alias("oldest_issue_days"),
                ]
            )
            .with_columns(
                [
                    (
                        pl.col("stale_issues_count")
                        * 100.0
                        / pl.col("total_backlog_size")
                    )
                    .round(2)
                    .alias("stale_percentage")
                ]
            )
        )
    else:
        snapshot_metrics = pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "date": pl.Date,
                "total_backlog_size": pl.Int64,
                "avg_age_days": pl.Float64,
                "stale_issues_count": pl.Int64,
                "oldest_issue_days": pl.Int64,
                "stale_percentage": pl.Float64,
            }
        )

    # 2. Daily Fluctuations (Created/Closed)
    created_daily = (
        issues_df.with_columns(pl.col("jira_created_at").cast(pl.Date).alias("date"))
        .group_by(["project_id", "date"])
        .agg([pl.len().cast(pl.Int64).alias("created_daily")])
    )

    closed_daily = (
        issues_df.filter(pl.col("jira_resolved_at").is_not_null())
        .with_columns(pl.col("jira_resolved_at").cast(pl.Date).alias("date"))
        .group_by(["project_id", "date"])
        .agg([pl.len().cast(pl.Int64).alias("closed_daily")])
    )

    # 3. Entered/Exited Backlog (Column 0 logic)
    entered_backlog = pl.DataFrame(
        {"project_id": [], "date": [], "entered_backlog_count": []},
        schema_overrides={
            "project_id": pl.Utf8,
            "date": pl.Date,
            "entered_backlog_count": pl.Int64,
        },
    )
    exited_backlog = pl.DataFrame(
        {"project_id": [], "date": [], "exited_backlog_count": []},
        schema_overrides={
            "project_id": pl.Utf8,
            "date": pl.Date,
            "exited_backlog_count": pl.Int64,
        },
    )

    if (
        changelog_df is not None
        and board_column_statuses_df is not None
        and not board_column_statuses_df.is_empty()
    ):
        # Get statuses in the first column (position 0)
        backlog_column_statuses = board_column_statuses_df.filter(
            pl.col("position") == 0
        )

        if not backlog_column_statuses.is_empty():
            changelog_with_project = changelog_df.join(
                issues_df.select(["id", "project_id"]),
                left_on="issue_id",
                right_on="id",
            )

            # Map changelog events to dates
            daily_changelog = changelog_with_project.with_columns(
                pl.col("changed_at").cast(pl.Date).alias("date")
            ).filter((pl.col("date") >= start_date) & (pl.col("date") <= end_date))

            backlog_status_set = backlog_column_statuses.select(
                ["project_id", "status_id"]
            ).with_columns(pl.lit(True).alias("is_backlog"))

            entered_events = daily_changelog.join(
                backlog_status_set,
                left_on=["project_id", "to_status_id"],
                right_on=["project_id", "status_id"],
                how="left",
            ).with_columns(pl.col("is_backlog").fill_null(False).alias("to_is_backlog"))

            entered_events = entered_events.join(
                backlog_status_set,
                left_on=["project_id", "from_status_id"],
                right_on=["project_id", "status_id"],
                how="left",
                suffix="_from",
            ).with_columns(
                pl.col("is_backlog_from").fill_null(False).alias("from_is_backlog")
            )

            entered_backlog = (
                entered_events.filter(
                    (pl.col("to_is_backlog").eq(True))
                    & (pl.col("from_is_backlog").eq(False))
                )
                .group_by(["project_id", "date"])
                .agg([pl.len().cast(pl.Int64).alias("entered_backlog_count")])
            )

            exited_backlog = (
                entered_events.filter(
                    (pl.col("from_is_backlog").eq(True))
                    & (pl.col("to_is_backlog").eq(False))
                )
                .group_by(["project_id", "date"])
                .agg([pl.len().cast(pl.Int64).alias("exited_backlog_count")])
            )

            # Created directly in backlog column
            created_in_backlog = (
                daily_statuses.filter(
                    pl.col("date") == pl.col("jira_created_at").cast(pl.Date)
                )
                .join(
                    backlog_status_set,
                    left_on=["project_id", "status_id"],
                    right_on=["project_id", "status_id"],
                    how="inner",
                )
                .group_by(["project_id", "date"])
                .agg([pl.len().cast(pl.Int64).alias("created_in_backlog_count")])
            )

            entered_backlog = (
                entered_backlog.join(
                    created_in_backlog,
                    on=["project_id", "date"],
                    how="outer",
                    coalesce=True,
                )
                .with_columns(
                    (
                        pl.col("entered_backlog_count").fill_null(0)
                        + pl.col("created_in_backlog_count").fill_null(0)
                    ).alias("entered_backlog_count")
                )
                .select(["project_id", "date", "entered_backlog_count"])
            )

    # 4. Final Join and Alignment
    relevant_projects = issues_df.select("project_id").unique()
    full_grid = relevant_projects.join(date_range, how="cross")

    final_df = (
        full_grid.join(snapshot_metrics, on=["project_id", "date"], how="left")
        .join(created_daily, on=["project_id", "date"], how="left")
        .join(closed_daily, on=["project_id", "date"], how="left")
        .join(entered_backlog, on=["project_id", "date"], how="left")
        .join(exited_backlog, on=["project_id", "date"], how="left")
        .with_columns(
            [
                pl.col("total_backlog_size").fill_null(0),
                pl.col("avg_age_days").fill_null(0.0),
                pl.col("stale_issues_count").fill_null(0),
                pl.col("stale_percentage").fill_null(0.0),
                pl.col("oldest_issue_days").fill_null(0),
                pl.col("created_daily").fill_null(0),
                pl.col("closed_daily").fill_null(0),
                pl.col("entered_backlog_count").fill_null(0),
                pl.col("exited_backlog_count").fill_null(0),
                pl.col("date").alias("fact_date"),
            ]
        )
        .select(
            [
                "project_id",
                "fact_date",
                "total_backlog_size",
                "avg_age_days",
                "stale_issues_count",
                "stale_percentage",
                "oldest_issue_days",
                "created_daily",
                "closed_daily",
                "entered_backlog_count",
                "exited_backlog_count",
            ]
        )
        .sort(["project_id", "fact_date"])
    )

    return final_df


def calculate_backlog_growth_trends(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
    period: str = "weekly",  # weekly or monthly
) -> pl.DataFrame:
    """
    Calculate backlog growth trends (Created, Completed, Net Growth) over time.

    Args:
        issues_df: Issue details including resolved_at
        issue_statuses_df: Status definitions
        period: "weekly" or "monthly"

    Returns:
        DataFrame: [project_id, period_start, period_type, created_count, completed_count, net_growth]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "period_start": pl.Date,
                "period_type": pl.Utf8,
                "created_count": pl.Int64,
                "completed_count": pl.Int64,
                "net_growth": pl.Int64,
            }
        )

    # Prepare created data
    # Truncate dates to week/month start
    if period == "weekly":
        trunc_str = "1w"
    else:
        trunc_str = "1mo"

    created_counts = (
        issues_df.with_columns(
            [
                pl.col("jira_created_at")
                .dt.truncate(trunc_str)
                .cast(pl.Date)
                .alias("period_start")
            ]
        )
        .group_by(["project_id", "period_start"])
        .agg([pl.len().alias("created_count")])
    )

    # Prepare completed data
    # Use jira_resolved_at for completed date
    completed_counts = (
        issues_df.filter(pl.col("jira_resolved_at").is_not_null())
        .with_columns(
            [
                pl.col("jira_resolved_at")
                .dt.truncate(trunc_str)
                .cast(pl.Date)
                .alias("period_start")
            ]
        )
        .group_by(["project_id", "period_start"])
        .agg([pl.len().alias("completed_count")])
    )

    # Join and calculate net
    # We need a full outer join on project_id and period_start
    # Polars doesn't support multi-key outer join easily in all versions,
    # but we can concat keys and dedup, then join left.

    # Simple approach: Outer join via special logic or align periods

    # Get all unique periods per project
    all_periods = pl.concat(
        [
            created_counts.select(["project_id", "period_start"]),
            completed_counts.select(["project_id", "period_start"]),
        ]
    ).unique()

    growth_df = (
        all_periods.join(
            created_counts, on=["project_id", "period_start"], how="left", coalesce=True
        )
        .join(
            completed_counts,
            on=["project_id", "period_start"],
            how="left",
            coalesce=True,
        )
        .with_columns(
            [
                pl.col("created_count").fill_null(0),
                pl.col("completed_count").fill_null(0),
                pl.lit(period).alias("period_type"),
            ]
        )
        .with_columns(
            [(pl.col("created_count") - pl.col("completed_count")).alias("net_growth")]
        )
        .sort(["project_id", "period_start"])
    )

    return growth_df


def calculate_backlog_distribution(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
    issue_types_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate backlog distribution by issue type and priority.

    Args:
        issues_df: Issue details
        issue_statuses_df: Status definitions
        issue_types_df: Issue type definitions
        field_values_df: Custom field values
        field_keys_df: Custom field definitions

    Returns:
        DataFrame: [project_id, issue_type, priority, issue_count, percentage]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "priority": pl.Utf8,
                "issue_count": pl.Int64,
                "percentage": pl.Float64,
            }
        )

    # Join issues with statuses to get category
    issues_with_status = issues_df.join(
        issue_statuses_df.select(["id", "category"]),
        left_on="status_id",
        right_on="id",
        how="inner",
    )

    # Filter to backlog (not "done")
    backlog_issues = issues_with_status.filter(pl.col("category") != "done")

    if backlog_issues.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "priority": pl.Utf8,
                "issue_count": pl.Int64,
                "percentage": pl.Float64,
            }
        )

    # Join with issue types
    backlog_with_type = backlog_issues.join(
        issue_types_df.select(["id", "name"]),
        left_on="type_id",
        right_on="id",
        how="left",
        coalesce=True,
    ).select(
        [
            "id",
            "project_id",
            pl.col("name").alias("issue_type"),
        ]
    )

    # Extract priority from custom fields
    priority_field_id = None
    if not field_keys_df.is_empty():
        priority_fields = field_keys_df.filter(
            pl.col("name").str.to_lowercase().str.contains("priority")
        )
        if not priority_fields.is_empty():
            priority_field_id = priority_fields["id"][0]

    if priority_field_id and not field_values_df.is_empty():
        # Get priority values
        priorities = field_values_df.filter(
            pl.col("field_key_id") == priority_field_id
        ).select(
            [
                "issue_id",
                pl.col("json_value")
                .str.json_decode(pl.Struct({"name": pl.Utf8}))
                .struct.field("name")
                .alias("priority"),
            ]
        )

        backlog_with_priority = backlog_with_type.join(
            priorities, left_on="id", right_on="issue_id", how="left", coalesce=True
        ).with_columns([pl.col("priority").fill_null("Unknown")])
    else:
        # No priority field - use "Unknown"
        backlog_with_priority = backlog_with_type.with_columns(
            [pl.lit("Unknown").alias("priority")]
        )

    # Calculate distribution
    distribution = (
        backlog_with_priority.group_by(["project_id", "issue_type", "priority"])
        .agg([pl.len().alias("issue_count")])
        .sort(["project_id", "issue_type", "priority"])
    )

    # Calculate percentages within each project
    project_totals = distribution.group_by("project_id").agg(
        [pl.col("issue_count").sum().alias("project_total")]
    )

    distribution_with_pct = (
        distribution.join(project_totals, on="project_id", how="left", coalesce=True)
        .with_columns(
            [
                (pl.col("issue_count") * 100.0 / pl.col("project_total"))
                .round(2)
                .alias("percentage")
            ]
        )
        .select(["project_id", "issue_type", "priority", "issue_count", "percentage"])
    )

    return distribution_with_pct


def calculate_age_distribution(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate age distribution of backlog issues.

    Buckets:
    - 0-7 days (new)
    - 8-30 days (recent)
    - 31-90 days (aging)
    - 91+ days (old)

    Args:
        issues_df: Issue details
        issue_statuses_df: Status definitions

    Returns:
        DataFrame: [project_id, age_bucket, issue_count, percentage]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "age_bucket": pl.Utf8,
                "issue_count": pl.Int64,
                "percentage": pl.Float64,
            }
        )

    # Join issues with statuses to get category
    issues_with_status = issues_df.join(
        issue_statuses_df.select(["id", "category"]),
        left_on="status_id",
        right_on="id",
        how="inner",
    )

    # Filter to backlog (not "done")
    backlog_issues = issues_with_status.filter(pl.col("category") != "done")

    if backlog_issues.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "age_bucket": pl.Utf8,
                "issue_count": pl.Int64,
                "percentage": pl.Float64,
            }
        )

    now = datetime.now(timezone.utc)

    # Calculate age and bucket
    backlog_with_age = backlog_issues.with_columns(
        [
            # Age in days
            (
                (pl.lit(now) - pl.col("jira_created_at")).dt.total_seconds() / 86400.0
            ).alias("age_days"),
        ]
    ).with_columns(
        [
            pl.when(pl.col("age_days") <= 7)
            .then(pl.lit("0-7 days (new)"))
            .when(pl.col("age_days") <= 30)
            .then(pl.lit("8-30 days (recent)"))
            .when(pl.col("age_days") <= 90)
            .then(pl.lit("31-90 days (aging)"))
            .otherwise(pl.lit("91+ days (old)"))
            .alias("age_bucket")
        ]
    )

    # Count by bucket
    distribution = backlog_with_age.group_by(["project_id", "age_bucket"]).agg(
        [pl.len().alias("issue_count")]
    )

    # Calculate percentages
    project_totals = distribution.group_by("project_id").agg(
        [pl.col("issue_count").sum().alias("project_total")]
    )

    distribution_with_pct = (
        distribution.join(project_totals, on="project_id", how="left")
        .with_columns(
            [
                (pl.col("issue_count") * 100.0 / pl.col("project_total"))
                .round(2)
                .alias("percentage")
            ]
        )
        .select(["project_id", "age_bucket", "issue_count", "percentage"])
        .sort(["project_id", "age_bucket"])
    )

    return distribution_with_pct
