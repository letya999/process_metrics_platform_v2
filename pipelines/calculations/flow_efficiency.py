"""
Flow Efficiency Calculation (Python/Polars Implementation)

This module calculates Flow Efficiency: the ratio of "active" working time
vs. total time (including waiting/blocked states).

Formula:
    Flow Efficiency % = (Active Time / (Active Time + Wait Time)) * 100

Business Rules:
1. Duration is measured from Commitment Start to Commitment End (Lead Time).
2. Statuses must be explicitly mapped to "Wait" (e.g. Blocked, Ready for Review).
   All other statuses in the lifecycle are considered "Active" (or vice versa).
3. We calculate efficiency PER ISSUE, and then aggregate.
"""

import polars as pl

from pipelines.calculations.lead_time import identify_commitment_points


def calculate_flow_efficiency(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
    wait_status_ids: list[str] = None,
) -> pl.DataFrame:
    """
    Calculate Flow Efficiency for each COMPLETED issue.

    Args:
        issues_df: Issue details
        status_changelog_df: Status change history
        boards_df: Board definitions (for identifying start/end)
        board_columns_df: Board column config
        wait_status_ids: List of status IDs considered as "Waiting" state.

    Returns:
        DataFrame: [issue_id, project_id, active_days, wait_days, total_days, flow_efficiency_pct]
    """
    if issues_df.is_empty() or status_changelog_df.is_empty():
        return _empty_efficiency_df()

    wait_status_ids = wait_status_ids or []

    # 1. Identify Start/End Scope to limit calculation to relevant history
    points = identify_commitment_points(boards_df, board_columns_df)
    middle_status_ids = points.get("middle_status_ids", [])

    # We only care about history within the "In Progress" phase (Middle statuses)
    # Events before start or after end are typically excluded from Flow Efficiency
    # (or depend on precise definition). For now, let's look at ALL history
    # but only count durations for statuses strictly in the "Middle" set.
    relevant_status_ids = set(middle_status_ids)

    # 2. Calculate time in each status for each issue
    # Sort history by issue and date
    history = status_changelog_df.sort(["issue_id", "changed_at"])

    # Calculate duration of each status interval
    # Shift 'changed_at' to subtract from the NEXT change
    status_durations = history.group_by("issue_id").map_groups(
        lambda df: _calculate_intervals(df)
    )

    # 3. Classify intervals as Active vs Wait
    # Filter only for Lead Time phase (statuses in "In Progress" columns)
    in_progress_durations = status_durations.filter(
        pl.col("status_id").is_in(relevant_status_ids)
    )

    efficiency_stats = (
        in_progress_durations.with_columns(
            [
                pl.when(pl.col("status_id").is_in(wait_status_ids))
                .then(pl.lit("wait"))
                .otherwise(pl.lit("active"))
                .alias("activity_type")
            ]
        )
        .group_by(["issue_id"])
        .agg(
            [
                pl.col("duration_days")
                .filter(pl.col("activity_type") == "active")
                .sum()
                .fill_null(0.0)
                .alias("active_days"),
                pl.col("duration_days")
                .filter(pl.col("activity_type") == "wait")
                .sum()
                .fill_null(0.0)
                .alias("wait_days"),
            ]
        )
    )

    # 4. Calculate Final %
    final_df = (
        efficiency_stats.join(
            issues_df.select(["id", "project_id", "key", "type_name"]),
            left_on="issue_id",
            right_on="id",
            how="inner",
        )
        .with_columns(
            [(pl.col("active_days") + pl.col("wait_days")).alias("total_days")]
        )
        .with_columns(
            [
                (
                    pl.when(pl.col("total_days") > 0)
                    .then((pl.col("active_days") / pl.col("total_days")) * 100.0)
                    .otherwise(0.0)
                )
                .round(2)
                .alias("flow_efficiency_pct")
            ]
        )
    )

    return final_df


def _calculate_intervals(df: pl.DataFrame) -> pl.DataFrame:
    """
    Helper to calculate time between status changes.
    Last interval is ignored (time since last change until now/end)
    unless we have a closure event.
    For simplicity here, we stick to intervals BETWEEN changes.
    """
    # Shift changed_at to get end time of current status duration
    # This is a simplification. A full reconstruction would need to know
    # the exit status time.
    return (
        df.with_columns(
            [
                pl.col("changed_at").shift(-1).alias("next_change_at"),
                pl.col("to_status_id").alias("status_id"),  # The status entered
            ]
        )
        .filter(pl.col("next_change_at").is_not_null())
        .with_columns(
            [
                (
                    (pl.col("next_change_at") - pl.col("changed_at")).dt.total_seconds()
                    / 86400.0
                ).alias("duration_days")
            ]
        )
    )


def _empty_efficiency_df() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "project_id": pl.Utf8,
            "key": pl.Utf8,
            "type_name": pl.Utf8,
            "active_days": pl.Float64,
            "wait_days": pl.Float64,
            "total_days": pl.Float64,
            "flow_efficiency_pct": pl.Float64,
        }
    )
