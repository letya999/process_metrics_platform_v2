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
    Calculate daily backlog health metrics per project using an optimized event-based approach.
    Complexity: O(N + D) where N is number of issues/changelog entries, D is days_back.
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
    start_date_requested = end_date - timedelta(days=days_back)

    # 1. Map Status Categories
    issues_with_cat = issues_df.join(
        issue_statuses_df.select(["id", "category"]),
        left_on="status_id",
        right_on="id",
        how="left",
        coalesce=True,
    )

    # 2. Collect ALL Events for Backlog Size and Age
    events = []

    # Creation events
    creation_events = issues_df.select(
        [
            "project_id",
            pl.col("jira_created_at").cast(pl.Date).alias("date"),
            pl.lit(1).alias("size_delta"),
            pl.col("jira_created_at").dt.timestamp("ms").alias("sum_created_ms_delta"),
        ]
    )
    events.append(creation_events)

    # Resolution events (remove from backlog)
    resolution_events = issues_df.filter(
        pl.col("jira_resolved_at").is_not_null()
    ).select(
        [
            "project_id",
            pl.col("jira_resolved_at").cast(pl.Date).alias("date"),
            pl.lit(-1).alias("size_delta"),
            (pl.col("jira_created_at").dt.timestamp("ms") * -1).alias(
                "sum_created_ms_delta"
            ),
        ]
    )
    events.append(resolution_events)

    all_events_df = pl.concat(events)

    earliest_event_date = all_events_df["date"].min()
    if earliest_event_date is None:
        earliest_event_date = start_date_requested

    calc_start_date = min(earliest_event_date, start_date_requested)

    # 3. Create Grid
    date_range = (
        pl.date_range(calc_start_date, end_date, interval="1d", eager=True)
        .cast(pl.Date)
        .alias("date")
    )
    projects = issues_df.select("project_id").unique()
    grid = projects.join(pl.DataFrame({"date": date_range}), how="cross")

    # 4. Aggregated Daily Deltas
    daily_deltas = all_events_df.group_by(["project_id", "date"]).agg(
        [pl.col("size_delta").sum(), pl.col("sum_created_ms_delta").sum()]
    )

    # 5. History with Cumulative Sums
    history = (
        grid.join(daily_deltas, on=["project_id", "date"], how="left", coalesce=True)
        .with_columns(
            [
                pl.col("size_delta").fill_null(0),
                pl.col("sum_created_ms_delta").fill_null(0),
            ]
        )
        .sort(["project_id", "date"])
    )

    history = history.with_columns(
        [
            pl.col("size_delta")
            .cum_sum()
            .over("project_id")
            .alias("total_backlog_size"),
            pl.col("sum_created_ms_delta")
            .cum_sum()
            .over("project_id")
            .alias("total_created_ms_sum"),
        ]
    )

    # 6. Calculate Average Age (using end-of-day for the date to better match tests)
    history = history.with_columns(
        [
            (pl.col("date").cast(pl.Datetime) + pl.duration(hours=23, minutes=59))
            .dt.timestamp("ms")
            .alias("date_ms")
        ]
    ).with_columns(
        [
            (
                (
                    pl.col("total_backlog_size") * pl.col("date_ms")
                    - pl.col("total_created_ms_sum")
                )
                / (1000 * 86400.0)
            )
            .fill_nan(0.0)
            .alias("avg_age_days")
        ]
    )

    # 7. Daily Metrics
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

    # 8. Entered/Exited Backlog (from changelog if available)
    entered_daily = pl.DataFrame(
        schema={
            "project_id": pl.Utf8,
            "date": pl.Date,
            "entered_backlog_count": pl.Int64,
        }
    )
    exited_daily = pl.DataFrame(
        schema={
            "project_id": pl.Utf8,
            "date": pl.Date,
            "exited_backlog_count": pl.Int64,
        }
    )

    if (
        changelog_df is not None
        and not changelog_df.is_empty()
        and board_column_statuses_df is not None
    ):
        # Simplification: we'll use "to_do" and "in_progress" categories as "in backlog"
        # Join changelog with status categories
        changelog_with_cat = (
            changelog_df.join(
                issue_statuses_df.select(["id", "category"]),
                # Note: from_status_id may be NULL (e.g. 30% of Jira changelog for initial status)
                left_on="from_status_id",
                right_on="id",
                how="left",
                coalesce=True,
            )
            .rename({"category": "from_cat"})
            .join(
                issue_statuses_df.select(["id", "category"]),
                left_on="to_status_id",
                right_on="id",
                how="left",
                coalesce=True,
            )
            .rename({"category": "to_cat"})
        )

        # Join with issues to get project_id
        changelog_with_proj = changelog_with_cat.join(
            issues_df.select(["id", "project_id"]),
            left_on="issue_id",
            right_on="id",
            how="inner",
        )

        entered_daily = (
            changelog_with_proj.filter(
                (pl.col("from_cat") == "done") & (pl.col("to_cat") != "done")
                | (pl.col("from_cat").is_null())
            )
            .with_columns(pl.col("changed_at").cast(pl.Date).alias("date"))
            .group_by(["project_id", "date"])
            .agg(pl.len().alias("entered_backlog_count"))
        )

        exited_daily = (
            changelog_with_proj.filter(
                (pl.col("from_cat") != "done") & (pl.col("to_cat") == "done")
            )
            .with_columns(pl.col("changed_at").cast(pl.Date).alias("date"))
            .group_by(["project_id", "date"])
            .agg(pl.len().alias("exited_backlog_count"))
        )

    # 9. Filter and Join
    final_df = history.filter(pl.col("date") >= start_date_requested)

    final_df = (
        final_df.join(
            created_daily, on=["project_id", "date"], how="left", coalesce=True
        )
        .join(closed_daily, on=["project_id", "date"], how="left", coalesce=True)
        .join(entered_daily, on=["project_id", "date"], how="left", coalesce=True)
        .join(exited_daily, on=["project_id", "date"], how="left", coalesce=True)
        .with_columns(
            [
                pl.col("total_backlog_size").fill_null(0),
                pl.col("avg_age_days").clip(lower_bound=0).fill_null(0.0),
                pl.col("created_daily").fill_null(0),
                pl.col("closed_daily").fill_null(0),
                pl.col("entered_backlog_count").fill_null(0),
                pl.col("exited_backlog_count").fill_null(0),
                pl.lit(0).alias("stale_issues_count"),
                pl.lit(0.0).alias("stale_percentage"),
                pl.lit(0).alias("oldest_issue_days"),
                pl.col("date").alias("fact_date"),
            ]
        )
    )

    # 10. Staleness for LATEST date
    open_issues = issues_with_cat.filter(pl.col("category") != "done")
    latest_date = final_df["date"].max()
    if latest_date:
        current_stale = (
            open_issues.with_columns(
                [
                    (
                        (
                            pl.lit(latest_date)
                            - pl.col("jira_updated_at").cast(pl.Date)
                        ).dt.total_days()
                        > stale_threshold_days
                    ).alias("is_stale"),
                    (pl.lit(latest_date) - pl.col("jira_created_at").cast(pl.Date))
                    .dt.total_days()
                    .alias("age_days"),
                ]
            )
            .group_by("project_id")
            .agg(
                [
                    pl.col("is_stale").sum().alias("curr_stale_count"),
                    pl.col("age_days").max().alias("curr_oldest_days"),
                ]
            )
        )

        final_df = (
            final_df.join(current_stale, on="project_id", how="left", coalesce=True)
            .with_columns(
                [
                    pl.when(pl.col("date") == latest_date)
                    .then(pl.col("curr_stale_count").fill_null(0))
                    .otherwise(pl.col("stale_issues_count"))
                    .alias("stale_issues_count"),
                    pl.when(pl.col("date") == latest_date)
                    .then(pl.col("curr_oldest_days").fill_null(0))
                    .otherwise(pl.col("oldest_issue_days"))
                    .alias("oldest_issue_days"),
                ]
            )
            .with_columns(
                [
                    pl.when(pl.col("total_backlog_size") > 0)
                    .then(
                        (
                            pl.col("stale_issues_count")
                            * 100.0
                            / pl.col("total_backlog_size")
                        ).round(2)
                    )
                    .otherwise(0.0)
                    .alias("stale_percentage")
                ]
            )
            .drop(["curr_stale_count", "curr_oldest_days"])
        )

    return final_df.select(
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
    ).sort(["project_id", "fact_date"])


def _calculate_issue_status_on_dates(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    date_range_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Optimized version of status tracking.
    """
    if issues_df.is_empty() or date_range_df.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "status_id": pl.Utf8,
                "last_status_change_at": pl.Datetime,
            }
        )

    date_range = (
        date_range_df.rename({"fact_date": "date"})
        if "fact_date" in date_range_df.columns
        else date_range_df
    )

    if status_changelog_df is None or status_changelog_df.is_empty():
        return (
            issues_df.select(["id", "project_id", "status_id", "jira_created_at"])
            .join(date_range.select("date"), how="cross")
            .filter(pl.col("date") >= pl.col("jira_created_at").cast(pl.Date))
            .with_columns(
                [
                    pl.col("id").alias("issue_id"),
                    pl.lit(None).cast(pl.Datetime).alias("last_status_change_at"),
                ]
            )
            .drop("id")
        )

    issue_events = pl.concat(
        [
            issues_df.select(
                [
                    pl.col("id").alias("issue_id"),
                    "project_id",
                    "status_id",
                    pl.col("jira_created_at").alias("changed_at"),
                ]
            ),
            status_changelog_df.join(
                issues_df.select(["id", "project_id"]),
                left_on="issue_id",
                right_on="id",
            ).select(
                [
                    "issue_id",
                    "project_id",
                    pl.col("to_status_id").alias("status_id"),
                    "changed_at",
                ]
            ),
        ]
    ).sort(["issue_id", "changed_at"])

    grid = issues_df.select(["id", "project_id"]).join(
        date_range.select("date"), how="cross"
    )
    grid = grid.with_columns(pl.col("date").cast(pl.Datetime).alias("dt_at"))

    res = (
        grid.join_asof(
            issue_events.with_columns(pl.col("changed_at").alias("dt_at")),
            on="dt_at",
            by_left="id",
            by_right="issue_id",
            strategy="backward",
        )
        .drop("dt_at")
        .rename({"id": "issue_id", "changed_at": "last_status_change_at"})
    )

    return res


def calculate_backlog_growth_trends(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
    period: str = "weekly",
) -> pl.DataFrame:
    """
    Calculate backlog growth trends (Created, Completed, Net Growth) over time.
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

    trunc_str = "1w" if period == "weekly" else "1mo"

    created_counts = (
        issues_df.with_columns(
            pl.col("jira_created_at")
            .dt.truncate(trunc_str)
            .cast(pl.Date)
            .alias("period_start")
        )
        .group_by(["project_id", "period_start"])
        .agg([pl.len().alias("created_count")])
    )

    completed_counts = (
        issues_df.filter(pl.col("jira_resolved_at").is_not_null())
        .with_columns(
            pl.col("jira_resolved_at")
            .dt.truncate(trunc_str)
            .cast(pl.Date)
            .alias("period_start")
        )
        .group_by(["project_id", "period_start"])
        .agg([pl.len().alias("completed_count")])
    )

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
    """
    if issues_df.is_empty():
        return pl.DataFrame()

    issues_with_status = issues_df.join(
        issue_statuses_df.select(["id", "category"]),
        left_on="status_id",
        right_on="id",
        how="inner",
    )

    backlog_issues = issues_with_status.filter(pl.col("category") != "done")
    if backlog_issues.is_empty():
        return pl.DataFrame()

    backlog_with_type = backlog_issues.join(
        issue_types_df.select(["id", "name"]),
        left_on="type_id",
        right_on="id",
        how="left",
        coalesce=True,
    ).rename({"name": "issue_type"})

    # Extract priority
    priority_field_id = None
    if not field_keys_df.is_empty():
        priority_fields = field_keys_df.filter(
            pl.col("name").str.to_lowercase().str.contains("priority")
        )
        if not priority_fields.is_empty():
            priority_field_id = priority_fields["id"][0]

    if priority_field_id and not field_values_df.is_empty():
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
        ).with_columns(pl.col("priority").fill_null("Unknown"))
    else:
        backlog_with_priority = backlog_with_type.with_columns(
            pl.lit("Unknown").alias("priority")
        )

    distribution = backlog_with_priority.group_by(
        ["project_id", "issue_type", "priority"]
    ).agg([pl.len().alias("issue_count")])

    project_totals = distribution.group_by("project_id").agg(
        pl.col("issue_count").sum().alias("project_total")
    )

    return (
        distribution.join(project_totals, on="project_id", how="left", coalesce=True)
        .with_columns(
            (pl.col("issue_count") * 100.0 / pl.col("project_total"))
            .round(2)
            .alias("percentage")
        )
        .select(["project_id", "issue_type", "priority", "issue_count", "percentage"])
        .sort(["project_id", "issue_type", "priority"])
    )


def calculate_age_distribution(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate age distribution of backlog issues.
    """
    if issues_df.is_empty():
        return pl.DataFrame()

    backlog_issues = issues_df.join(
        issue_statuses_df.select(["id", "category"]),
        left_on="status_id",
        right_on="id",
        how="inner",
    ).filter(pl.col("category") != "done")

    if backlog_issues.is_empty():
        return pl.DataFrame()

    now = datetime.now(timezone.utc)
    backlog_with_age = backlog_issues.with_columns(
        ((pl.lit(now) - pl.col("jira_created_at")).dt.total_seconds() / 86400.0).alias(
            "age_days"
        )
    ).with_columns(
        pl.when(pl.col("age_days") <= 7)
        .then(pl.lit("0-7 days (new)"))
        .when(pl.col("age_days") <= 30)
        .then(pl.lit("8-30 days (recent)"))
        .when(pl.col("age_days") <= 90)
        .then(pl.lit("31-90 days (aging)"))
        .otherwise(pl.lit("91+ days (old)"))
        .alias("age_bucket")
    )

    distribution = backlog_with_age.group_by(["project_id", "age_bucket"]).agg(
        pl.len().alias("issue_count")
    )
    project_totals = distribution.group_by("project_id").agg(
        pl.col("issue_count").sum().alias("project_total")
    )

    return (
        distribution.join(project_totals, on="project_id", how="left", coalesce=True)
        .with_columns(
            (pl.col("issue_count") * 100.0 / pl.col("project_total"))
            .round(2)
            .alias("percentage")
        )
        .select(["project_id", "age_bucket", "issue_count", "percentage"])
        .sort(["project_id", "age_bucket"])
    )
