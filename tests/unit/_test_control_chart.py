"""
Unit tests for Control Chart calculation logic.
"""

from datetime import datetime

import polars as pl

from pipelines.calculations.control_chart import calculate_control_chart_stats


class TestControlChart:
    """Tests for calculate_control_chart_stats."""

    def test_calculate_control_chart_basic(self):
        """Test basic stats calculation."""
        # 10 issues with constant lead time 5 days
        data = pl.DataFrame(
            {
                "issue_id": [str(i) for i in range(10)],
                "lead_time_days": [5.0] * 10,
                "commitment_end_at": [datetime(2024, 1, i + 1) for i in range(10)],
            }
        )

        result = calculate_control_chart_stats(data, window_size=5)

        # Rolling mean should be 5.0 after enough periods
        assert result.filter(pl.col("issue_id") == "9")["rolling_mean"][0] == 5.0
        # Std dev should be 0
        assert result.filter(pl.col("issue_id") == "9")["rolling_std"][0] == 0.0

    def test_calculate_control_chart_outlier(self):
        """Test outlier detection."""
        # Issues with small variance, then one huge outlier
        lead_times = [5.0] * 19 + [100.0]  # 20 items
        data = pl.DataFrame(
            {
                "issue_id": [str(i) for i in range(20)],
                "lead_time_days": lead_times,
                "commitment_end_at": [datetime(2024, 1, i + 1) for i in range(20)],
            }
        )

        result = calculate_control_chart_stats(data, window_size=20)

        # Last item (100.0) should be outlier because mean ~10, std ~20 => ucl_3sigma ~ 70
        # Wait, rolling window includes the current item in Polars default?
        # rolling_mean at index 19 includes indices 0..19.
        # Check logic: Mean of [5...5, 100] is (95 + 100)/20 = 9.75.
        # Std will be large.
        # UCL 3 sigma = Mean + 3*Std.
        # If Std is large enough, 100 might effectively hide itself if window is small,
        # but here window covers all.

        # Let's test a spike after a stable period.
        # 20 stable items (5.0), then 1 spike (100.0). Window 20.
        # The spike comes at index 20 (21st item).
        lead_times = [5.0] * 20 + [100.0]
        data = pl.DataFrame(
            {
                "issue_id": [str(i) for i in range(21)],
                "lead_time_days": lead_times,
                "commitment_end_at": [datetime(2024, 1, i + 1) for i in range(21)],
            }
        )

        result = calculate_control_chart_stats(data, window_size=20)

        # Item 19 (20th) has mean 5.0, std 0.0. UCL = 5.0.
        # Item 20 (21st) has a rolling window of previous 19 + itself (20 items).
        # But rolling_mean usually centered? No, default is trailing (closed='right').
        # So item 21 window includes item 21.
        # The outlier logic compares item value vs UCL calculated INCLUDING the item itself?
        # That's standard control chart logic sometimes, or one uses previous stats.
        # The code:
        # (pl.col("lead_time_days") > pl.col("ucl_3sigma")).alias("is_outlier")
        # So it uses CURRENT window stats.

        # If window has one 100 and nineteen 5s.
        # Mean = 9.75.
        # Variance ~ ((100-9.75)^2 + 19*(5-9.75)^2)/19 ~ (8100 + 400)/19 ~ 450.
        # Std ~ 21.
        # UCL = 9.75 + 3*21 = 72.
        # 100 > 72. So it should be outlier.

        outlier_row = result.filter(pl.col("issue_id") == "20")
        assert outlier_row["is_outlier"][0] is True

    def test_control_chart_empty(self):
        """Test empty input."""
        result = calculate_control_chart_stats(pl.DataFrame({}), window_size=5)
        assert result.is_empty()
        assert "ucl_3sigma" in result.columns
