"""
Throughput Metrics Calculation (Python/Polars Implementation)

This module calculates Throughput metrics - the number of issues completed
over time periods (weekly aggregation).

Key Metrics:
- Weekly Throughput: Number of issues completed per week
- Average throughput over time
- Throughput by issue type

Business Rules:
1. Throughput is counted by completion date (when issue reached "Done" status)
2. Issues are grouped into weekly periods (Monday to Sunday)
3. Throughput is calculated per project and per issue type
"""

import polars as pl


def calculate_weekly_throughput(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate weekly throughput (issues completed per week).

    Args:
        issues_df: Issue details (id, project_id, key, type_name, jira_resolved_at)
        status_changelog_df: Status change history
        boards_df: Board definitions
        board_columns_df: Board column configuration

    Returns:
        DataFrame: [project_id, week_start_date, week_end_date, issue_type,
                    issues_completed, avg_lead_time_days]
    """
    if issues_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "week_start_date": pl.Date,
                "week_end_date": pl.Date,
                "issue_type": pl.Utf8,
                "issues_completed": pl.Int64,
            }
        )

    # Identify "Done" statuses from board configuration
    done_status_ids = _get_done_status_ids(board_columns_df)

    if not done_status_ids:
        # No "Done" column configured - use jira_resolved_at as fallback
        completed_issues = issues_df.filter(
            pl.col("jira_resolved_at").is_not_null()
        ).with_columns([pl.col("jira_resolved_at").alias("completion_date")])
    else:
        # Get completion date from status changelog (first entry to "Done")
        done_transitions = (
            status_changelog_df.filter(pl.col("to_status_id").is_in(done_status_ids))
            .group_by("issue_id")
            .agg(pl.col("changed_at").min().alias("completion_from_changelog"))
        )

        # Join with issues and use COALESCE(changelog, resolved_at)
        completed_issues = (
            issues_df.join(
                done_transitions,
                left_on="id",
                right_on="issue_id",
                how="left",
            )
            .with_columns(
                [
                    pl.coalesce(
                        [
                            pl.col("completion_from_changelog"),
                            pl.col("jira_resolved_at"),
                        ]
                    ).alias("completion_date")
                ]
            )
            .filter(pl.col("completion_date").is_not_null())
        )

    if completed_issues.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "week_start_date": pl.Date,
                "week_end_date": pl.Date,
                "issue_type": pl.Utf8,
                "issues_completed": pl.Int64,
            }
        )

    # Calculate week boundaries (ISO week: Monday = start)
    weekly_throughput = (
        completed_issues.with_columns(
            [
                # Get ISO week start (Monday)
                (
                    pl.col("completion_date").cast(pl.Date)
                    - pl.duration(days=pl.col("completion_date").dt.weekday() - 1)
                ).alias("week_start_date"),
            ]
        )
        .with_columns(
            [
                # Week end is 6 days after start (Sunday)
                (pl.col("week_start_date") + pl.duration(days=6)).alias("week_end_date")
            ]
        )
        .group_by(["project_id", "week_start_date", "week_end_date", "type_name"])
        .agg(
            [
                pl.count().alias("issues_completed"),
            ]
        )
        .select(
            [
                "project_id",
                "week_start_date",
                "week_end_date",
                pl.col("type_name").alias("issue_type"),
                "issues_completed",
            ]
        )
        .sort(["project_id", "week_start_date"])
    )

    return weekly_throughput


def _get_done_status_ids(board_columns_df: pl.DataFrame) -> list[str]:
    """
    Extract status IDs that represent "Done" from board configuration.

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
