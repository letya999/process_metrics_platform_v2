"""
Backlog Health Metrics Calculation

This module calculates metrics to assess the health of the product backlog.

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


def calculate_backlog_health(
    issues_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    stale_threshold_days: int = 30,
) -> pl.DataFrame:
    """
    Calculate backlog health metrics per project.

    Args:
        issues_df: Issue details (id, project_id, status_id, jira_created_at, jira_updated_at)
        issue_statuses_df: Status definitions with categories
        field_values_df: Custom field values (for priority, story points, etc.)
        field_keys_df: Custom field definitions
        stale_threshold_days: Days without updates to consider issue stale (default: 30)

    Returns:
        DataFrame: [project_id, total_backlog_size, avg_age_days,
                    stale_issues_count, stale_percentage, oldest_issue_days,
                    backlog_growth_last_week, backlog_growth_last_month]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "total_backlog_size": pl.Int64,
                "avg_age_days": pl.Float64,
                "stale_issues_count": pl.Int64,
                "stale_percentage": pl.Float64,
                "oldest_issue_days": pl.Int64,
                "backlog_growth_last_week": pl.Int64,
                "backlog_growth_last_month": pl.Int64,
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
                "total_backlog_size": pl.Int64,
                "avg_age_days": pl.Float64,
                "stale_issues_count": pl.Int64,
                "stale_percentage": pl.Float64,
                "oldest_issue_days": pl.Int64,
                "backlog_growth_last_week": pl.Int64,
                "backlog_growth_last_month": pl.Int64,
            }
        )

    now = datetime.now(timezone.utc)

    # Calculate age and staleness
    backlog_with_metrics = backlog_issues.with_columns(
        [
            # Age in days since creation
            (
                (pl.lit(now) - pl.col("jira_created_at")).dt.total_seconds() / 86400.0
            ).alias("age_days"),
            # Days since last update
            (
                (pl.lit(now) - pl.col("jira_updated_at")).dt.total_seconds() / 86400.0
            ).alias("days_since_update"),
            # Is issue stale?
            (
                (pl.lit(now) - pl.col("jira_updated_at")).dt.total_seconds() / 86400.0
                > stale_threshold_days
            ).alias("is_stale"),
        ]
    )

    # Calculate backlog growth (issues created in last week/month)
    last_week = now - timedelta(days=7)
    last_month = now - timedelta(days=30)

    backlog_growth = backlog_with_metrics.group_by("project_id").agg(
        [
            pl.when(pl.col("jira_created_at") >= last_week)
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .sum()
            .alias("created_last_week"),
            pl.when(pl.col("jira_created_at") >= last_month)
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .sum()
            .alias("created_last_month"),
        ]
    )

    # Calculate main metrics
    backlog_health = (
        backlog_with_metrics.group_by("project_id")
        .agg(
            [
                pl.len().alias("total_backlog_size"),
                pl.col("age_days").mean().round(2).alias("avg_age_days"),
                pl.col("is_stale").sum().alias("stale_issues_count"),
                pl.col("age_days")
                .max()
                .round(0)
                .cast(pl.Int64)
                .alias("oldest_issue_days"),
            ]
        )
        .with_columns(
            [
                # Calculate stale percentage
                (pl.col("stale_issues_count") * 100.0 / pl.col("total_backlog_size"))
                .round(2)
                .alias("stale_percentage")
            ]
        )
        .join(backlog_growth, on="project_id", how="left")
        .select(
            [
                "project_id",
                "total_backlog_size",
                "avg_age_days",
                "stale_issues_count",
                "stale_percentage",
                "oldest_issue_days",
                pl.col("created_last_week").alias("backlog_growth_last_week"),
                pl.col("created_last_month").alias("backlog_growth_last_month"),
            ]
        )
        .sort("project_id")
    )

    return backlog_health


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
            priorities, left_on="id", right_on="issue_id", how="left"
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
        distribution.join(project_totals, on="project_id", how="left")
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
        [pl.count().alias("issue_count")]
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
