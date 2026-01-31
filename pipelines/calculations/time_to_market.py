"""
Time to Market Metrics Calculation

This module calculates Time to Market (TTM) - the time from idea/creation
to production deployment/release.

Key Metrics:
- Time to Market: Creation → Release/Done
- Feature Lead Time: Epic/Feature level tracking
- Release Cadence: Frequency of releases
- Cycle Time by Stage: Breakdown by workflow stages

Business Rules:
1. TTM = Time from issue creation to first release/deployment
2. For issues without release info, use completion date as proxy
3. Track at Epic/Feature level (high-level items)
4. Calculate percentiles (P50, P90) for benchmarking
"""

from datetime import datetime

import polars as pl


def calculate_time_to_market(
    issues_df: pl.DataFrame,
    issue_types_df: pl.DataFrame,
    releases_df: pl.DataFrame,
    issue_fix_versions_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate Time to Market for features/epics.

    Args:
        issues_df: Issue details (id, project_id, type_id, jira_created_at, jira_resolved_at)
        issue_types_df: Issue type definitions
        releases_df: Release/version information
        issue_fix_versions_df: Issue-to-release mappings
        status_changelog_df: Status change history
        board_columns_df: Board configuration

    Returns:
        DataFrame: [issue_id, project_id, issue_key, issue_type, created_at,
                    released_at, time_to_market_days]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "issue_type": pl.Utf8,
                "created_at": pl.Datetime,
                "released_at": pl.Datetime,
                "time_to_market_days": pl.Float64,
            }
        )

    # Filter to high-level items (Epic, Story, Feature)
    high_level_types = ["Epic", "Story", "Feature"]

    issues_with_type = issues_df.join(
        issue_types_df.select(["id", "name", "hierarchy_level"]),
        left_on="type_id",
        right_on="id",
        how="inner",
    )

    # Focus on epics and stories (strategic items)
    strategic_issues = issues_with_type.filter(
        pl.col("name").is_in(high_level_types)
        | pl.col("hierarchy_level").is_in(["epic", "story"])
    )

    if strategic_issues.is_empty():
        return pl.DataFrame(
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_key": pl.Utf8,
                "issue_type": pl.Utf8,
                "created_at": pl.Datetime,
                "released_at": pl.Datetime,
                "time_to_market_days": pl.Float64,
            }
        )

    # Get release dates for issues
    released_at = _get_release_dates(
        strategic_issues,
        releases_df,
        issue_fix_versions_df,
        status_changelog_df,
        board_columns_df,
    )

    # Calculate TTM
    ttm_data = (
        strategic_issues.select(
            [
                pl.col("id").alias("issue_id"),
                "project_id",
                pl.col("key").alias("issue_key"),
                pl.col("name").alias("issue_type"),
                pl.col("jira_created_at").alias("created_at"),
            ]
        )
        .join(released_at, on="issue_id", how="inner")
        .with_columns(
            [
                # Calculate TTM in days
                (
                    (pl.col("released_at") - pl.col("created_at")).dt.total_seconds()
                    / 86400.0
                ).alias("time_to_market_days")
            ]
        )
        .filter(
            pl.col("released_at").is_not_null() & (pl.col("time_to_market_days") >= 0)
        )
        .sort(["project_id", "released_at"])
    )

    return ttm_data


def _get_release_dates(
    issues_df: pl.DataFrame,
    releases_df: pl.DataFrame,
    issue_fix_versions_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine release date for each issue.

    Priority:
    1. Actual release date from fix_versions
    2. Completion date (first entry to "Done")
    3. jira_resolved_at

    Args:
        issues_df: Issues
        releases_df: Releases
        issue_fix_versions_df: Issue-release mappings
        status_changelog_df: Status changelog
        board_columns_df: Board configuration

    Returns:
        DataFrame: [issue_id, released_at]
    """
    # Strategy 1: Use actual release dates
    released_via_version = None
    if not releases_df.is_empty() and not issue_fix_versions_df.is_empty():
        released_via_version = (
            issue_fix_versions_df.join(
                releases_df.select(["id", "release_date"]),
                left_on="version_id",
                right_on="id",
                how="inner",
            )
            .filter(pl.col("release_date").is_not_null())
            .group_by("issue_id")
            .agg(
                [
                    # Use earliest release date if issue is in multiple releases
                    pl.col("release_date")
                    .min()
                    .alias("released_at")
                ]
            )
        )

    # Strategy 2: Use completion date (Done status)
    done_status_ids = _get_done_status_ids(board_columns_df)
    completed_via_status = None

    if done_status_ids and not status_changelog_df.is_empty():
        completed_via_status = (
            status_changelog_df.filter(pl.col("to_status_id").is_in(done_status_ids))
            .group_by("issue_id")
            .agg([pl.col("changed_at").min().alias("released_at")])
        )

    # Strategy 3: Use jira_resolved_at
    resolved_fallback = issues_df.select(
        [
            pl.col("id").alias("issue_id"),
            pl.col("jira_resolved_at").alias("released_at"),
        ]
    ).filter(pl.col("released_at").is_not_null())

    # Combine all strategies with priority
    if released_via_version is not None:
        result = released_via_version

        # Add completion dates for issues without releases
        if completed_via_status is not None:
            result = (
                result.join(
                    completed_via_status,
                    on="issue_id",
                    how="outer",
                    suffix="_completion",
                )
                .with_columns(
                    [
                        pl.coalesce(
                            [pl.col("released_at"), pl.col("released_at_completion")]
                        ).alias("released_at")
                    ]
                )
                .select(["issue_id", "released_at"])
            )

        # Add resolved dates as final fallback
        result = (
            result.join(
                resolved_fallback,
                on="issue_id",
                how="outer",
                suffix="_resolved",
            )
            .with_columns(
                [
                    pl.coalesce(
                        [pl.col("released_at"), pl.col("released_at_resolved")]
                    ).alias("released_at")
                ]
            )
            .select(["issue_id", "released_at"])
        )

    elif completed_via_status is not None:
        result = completed_via_status

        # Add resolved dates as fallback
        result = (
            result.join(
                resolved_fallback,
                on="issue_id",
                how="outer",
                suffix="_resolved",
            )
            .with_columns(
                [
                    pl.coalesce(
                        [pl.col("released_at"), pl.col("released_at_resolved")]
                    ).alias("released_at")
                ]
            )
            .select(["issue_id", "released_at"])
        )
    else:
        result = resolved_fallback

    return result


def calculate_ttm_aggregates(ttm_df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate aggregate Time to Market metrics.

    Args:
        ttm_df: TTM facts

    Returns:
        DataFrame: [project_id, issue_type, total_issues, avg_ttm_days,
                    median_ttm_days, p90_ttm_days, min_ttm, max_ttm]
    """
    if ttm_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "total_issues": pl.Int64,
                "avg_ttm_days": pl.Float64,
                "median_ttm_days": pl.Float64,
                "p90_ttm_days": pl.Float64,
                "min_ttm": pl.Float64,
                "max_ttm": pl.Float64,
            }
        )

    aggregates = (
        ttm_df.group_by(["project_id", "issue_type"])
        .agg(
            [
                pl.count().alias("total_issues"),
                pl.col("time_to_market_days").mean().round(2).alias("avg_ttm_days"),
                pl.col("time_to_market_days")
                .quantile(0.5)
                .round(2)
                .alias("median_ttm_days"),
                pl.col("time_to_market_days")
                .quantile(0.9)
                .round(2)
                .alias("p90_ttm_days"),
                pl.col("time_to_market_days").min().round(2).alias("min_ttm"),
                pl.col("time_to_market_days").max().round(2).alias("max_ttm"),
            ]
        )
        .sort(["project_id", "issue_type"])
    )

    return aggregates


def calculate_release_cadence(
    releases_df: pl.DataFrame,
    days_back: int = 180,
) -> pl.DataFrame:
    """
    Calculate release cadence metrics (frequency and regularity).

    Args:
        releases_df: Release information
        days_back: Number of days to analyze (default: 180)

    Returns:
        DataFrame: [project_id, total_releases, avg_days_between_releases,
                    min_gap, max_gap, releases_per_month]
    """
    if releases_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "total_releases": pl.Int64,
                "avg_days_between_releases": pl.Float64,
                "min_gap": pl.Int64,
                "max_gap": pl.Int64,
                "releases_per_month": pl.Float64,
            }
        )

    # Filter to recent releases
    cutoff_date = datetime.now() - pl.duration(days=days_back)

    recent_releases = releases_df.filter(
        pl.col("release_date").is_not_null() & (pl.col("release_date") >= cutoff_date)
    ).sort(["project_id", "release_date"])

    if recent_releases.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "total_releases": pl.Int64,
                "avg_days_between_releases": pl.Float64,
                "min_gap": pl.Int64,
                "max_gap": pl.Int64,
                "releases_per_month": pl.Float64,
            }
        )

    # Calculate gaps between releases
    releases_with_gaps = (
        recent_releases.with_columns(
            [
                # Get previous release date within same project
                pl.col("release_date")
                .shift(1)
                .over("project_id")
                .alias("prev_release_date")
            ]
        )
        .with_columns(
            [
                # Days since previous release
                (
                    (
                        pl.col("release_date") - pl.col("prev_release_date")
                    ).dt.total_seconds()
                    / 86400.0
                )
                .cast(pl.Int64)
                .alias("days_since_prev")
            ]
        )
        .filter(pl.col("days_since_prev").is_not_null())
    )

    # Calculate cadence metrics
    cadence = (
        releases_with_gaps.group_by("project_id")
        .agg(
            [
                pl.count().alias("total_releases"),
                pl.col("days_since_prev")
                .mean()
                .round(2)
                .alias("avg_days_between_releases"),
                pl.col("days_since_prev").min().alias("min_gap"),
                pl.col("days_since_prev").max().alias("max_gap"),
            ]
        )
        .with_columns(
            [
                # Releases per month = 30 / avg_days_between
                (30.0 / pl.col("avg_days_between_releases"))
                .round(2)
                .alias("releases_per_month")
            ]
        )
        .sort("project_id")
    )

    return cadence


def _get_done_status_ids(board_columns_df: pl.DataFrame) -> list[str]:
    """
    Extract status IDs representing "Done" from board configuration.

    Args:
        board_columns_df: Board columns with status mappings

    Returns:
        List of status IDs representing "Done" state
    """
    if board_columns_df.is_empty():
        return []

    done_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("done")
        | pl.col("name").str.to_lowercase().str.contains("готово")  # Russian
    )

    if "status_id" in done_columns.columns:
        return done_columns["status_id"].unique().drop_nulls().to_list()

    return []
