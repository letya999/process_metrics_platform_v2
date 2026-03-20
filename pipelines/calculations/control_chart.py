"""
Control Chart metrics calculation helpers.

This module computes rolling statistics for issue lead times and marks outliers
using 3-sigma control limits.
"""

import polars as pl


def _empty_result() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "lead_time_days": pl.Float64,
            "commitment_end_at": pl.Datetime,
            "rolling_mean": pl.Float64,
            "rolling_std": pl.Float64,
            "ucl_3sigma": pl.Float64,
            "lcl_3sigma": pl.Float64,
            "is_outlier": pl.Boolean,
        }
    )


def calculate_control_chart_stats(
    lead_time_df: pl.DataFrame, window_size: int = 20
) -> pl.DataFrame:
    """
    Calculate rolling control-chart statistics.

    Args:
        lead_time_df: DataFrame with columns:
            - issue_id
            - lead_time_days
            - commitment_end_at
        window_size: Trailing rolling window size.

    Returns:
        DataFrame with original columns plus:
            - rolling_mean
            - rolling_std
            - ucl_3sigma
            - lcl_3sigma
            - is_outlier
    """
    required_cols = {"issue_id", "lead_time_days", "commitment_end_at"}
    if lead_time_df.is_empty() or not required_cols.issubset(set(lead_time_df.columns)):
        return _empty_result()

    if window_size <= 0:
        window_size = 1

    base_df = (
        lead_time_df.select(["issue_id", "lead_time_days", "commitment_end_at"])
        .sort("commitment_end_at")
        .with_columns(pl.col("lead_time_days").cast(pl.Float64))
    )

    stats_df = base_df.with_columns(
        [
            pl.col("lead_time_days")
            .rolling_mean(window_size=window_size, min_periods=1)
            .alias("rolling_mean"),
            pl.col("lead_time_days")
            .rolling_std(window_size=window_size, min_periods=1)
            .fill_null(0.0)
            .alias("rolling_std"),
        ]
    ).with_columns(
        [
            (pl.col("rolling_mean") + 3.0 * pl.col("rolling_std")).alias("ucl_3sigma"),
            (pl.col("rolling_mean") - 3.0 * pl.col("rolling_std")).alias("lcl_3sigma"),
        ]
    )

    return stats_df.with_columns(
        (pl.col("lead_time_days") > pl.col("ucl_3sigma")).alias("is_outlier")
    )
