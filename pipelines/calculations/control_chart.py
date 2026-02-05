"""
Control Chart Calculation (Python/Polars Implementation)

This module calculates Control Chart statistics for Lead Time.
It helps identify process stability and outliers.

Key Metrics:
- Rolling Mean (Average Lead Time over last N items)
- Rolling Standard Deviation (Sigma)
- Upper Control Limits (UCL): Mean + 2*Sigma, Mean + 3*Sigma
- Outlier flagging

Business Rules:
1. Sort completed issues by End Date.
2. Use a rolling window (e.g., 20 items) to calculate local stability.
3. Issues exceeding UCL are flagged as special cause variation (outliers).
"""

import polars as pl


def calculate_control_chart_stats(
    lead_time_df: pl.DataFrame, window_size: int = 20
) -> pl.DataFrame:
    """
    Calculate Rolling Mean/StdDev and Control Limits for Lead Time.

    Args:
        lead_time_df: DataFrame with [issue_id, commitment_end_at, lead_time_days]
        window_size: Number of items in rolling window (default 20)

    Returns:
        DataFrame joining original data with:
        [rolling_mean, rolling_std, ucl_2sigma, ucl_3sigma, is_outlier]
    """
    if lead_time_df.is_empty():
        return _empty_control_chart_df()

    # Ensure processed in chronological order of completion
    sorted_df = lead_time_df.sort("commitment_end_at")

    # Calculate Rolling Stats
    # Polars rolling functions operate on the column
    stats_df = sorted_df.with_columns(
        [
            pl.col("lead_time_days")
            .rolling_mean(window_size=window_size, min_periods=5)
            .alias("rolling_mean"),
            pl.col("lead_time_days")
            .rolling_std(window_size=window_size, min_periods=5)
            .alias("rolling_std"),
        ]
    )

    # Calculate Limits and Outliers
    result_df = stats_df.with_columns(
        [
            (pl.col("rolling_mean") + 2 * pl.col("rolling_std")).alias("ucl_2sigma"),
            (pl.col("rolling_mean") + 3 * pl.col("rolling_std")).alias("ucl_3sigma"),
        ]
    ).with_columns(
        [(pl.col("lead_time_days") > pl.col("ucl_3sigma")).alias("is_outlier")]
    )

    return result_df


def _empty_control_chart_df() -> pl.DataFrame:
    # Return structure matching expected output
    return pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "commitment_end_at": pl.Datetime,
            "lead_time_days": pl.Float64,
            "rolling_mean": pl.Float64,
            "rolling_std": pl.Float64,
            "ucl_2sigma": pl.Float64,
            "ucl_3sigma": pl.Float64,
            "is_outlier": pl.Boolean,
        }
    )
