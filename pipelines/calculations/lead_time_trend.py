"""
Lead Time Trend Calculation (Python/Polars Implementation)

This module calculates how Lead Time percentiles evolve over time.
It answers: "Are we getting faster, slower, or staying the same?"

Key Metrics:
- Periodic P50 (Median), P85, P95
- Trend direction (Increasing/Decreasing)

Business Rules:
1. Group completed issues by End Date periods (Weekly or Monthly).
2. Calculate percentiles for each bucket.
3. Compare with previous period to determine trend.
"""

import polars as pl


def calculate_lead_time_trends(
    lead_time_df: pl.DataFrame, period: str = "1w"  # 1w (week) or 1mo (month)
) -> pl.DataFrame:
    """
    Calculate Lead Time percentiles over time.

    Args:
        lead_time_df: DataFrame with [commitment_end_at, lead_time_days]
        period: Grouping period (default "1w")

    Returns:
        DataFrame: [period_start, count, p50, p85, p95, trend_p85]
    """
    if lead_time_df.is_empty():
        return _empty_trend_df()

    # Truncate date to period start
    grouped = (
        lead_time_df.with_columns(
            [pl.col("commitment_end_at").dt.truncate(period).alias("period_start")]
        )
        .group_by("period_start")
        .agg(
            [
                pl.count().alias("count"),
                pl.col("lead_time_days").median().round(2).alias("p50"),
                pl.col("lead_time_days").quantile(0.85).round(2).alias("p85"),
                pl.col("lead_time_days").quantile(0.95).round(2).alias("p95"),
            ]
        )
        .sort("period_start")
    )

    # Calculate Trend based on P85
    result = (
        grouped.with_columns([pl.col("p85").shift(1).alias("prev_p85")])
        .with_columns(
            [
                pl.when(pl.col("prev_p85").is_null())
                .then(pl.lit("stable"))
                .when(pl.col("p85") > pl.col("prev_p85") * 1.1)
                .then(pl.lit("slowing"))
                .when(pl.col("p85") < pl.col("prev_p85") * 0.9)
                .then(pl.lit("improving"))
                .otherwise(pl.lit("stable"))
                .alias("trend_p85")
            ]
        )
        .drop("prev_p85")
    )

    return result


def _empty_trend_df() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "period_start": pl.Datetime,
            "count": pl.Int64,
            "p50": pl.Float64,
            "p85": pl.Float64,
            "p95": pl.Float64,
            "trend_p85": pl.Utf8,
        }
    )
