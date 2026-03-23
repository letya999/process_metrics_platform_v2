"""Unit tests for Control Chart calculation logic."""

from datetime import datetime

import polars as pl

from pipelines.calculations.control_chart import calculate_control_chart_stats


class TestControlChart:
    """Tests for calculate_control_chart_stats."""

    def test_calculate_control_chart_basic(self):
        data = pl.DataFrame(
            {
                "issue_id": [str(i) for i in range(10)],
                "lead_time_days": [5.0] * 10,
                "commitment_end_at": [datetime(2024, 1, i + 1) for i in range(10)],
            }
        )

        result = calculate_control_chart_stats(data, window_size=5)

        assert result.filter(pl.col("issue_id") == "9")["rolling_mean"][0] == 5.0
        assert result.filter(pl.col("issue_id") == "9")["rolling_std"][0] == 0.0
        assert result["is_outlier"].sum() == 0

    def test_calculate_control_chart_detects_outlier(self):
        lead_times = [5.0] * 20 + [100.0]
        data = pl.DataFrame(
            {
                "issue_id": [str(i) for i in range(21)],
                "lead_time_days": lead_times,
                "commitment_end_at": [datetime(2024, 1, i + 1) for i in range(21)],
            }
        )

        result = calculate_control_chart_stats(data, window_size=20)
        outlier_row = result.filter(pl.col("issue_id") == "20")
        assert outlier_row["is_outlier"][0] is True

    def test_control_chart_returns_empty_for_invalid_input(self):
        result = calculate_control_chart_stats(pl.DataFrame({}), window_size=5)
        assert result.is_empty()
        assert "ucl_3sigma" in result.columns

    def test_control_chart_returns_empty_for_missing_columns(self):
        data = pl.DataFrame({"issue_id": ["1"], "lead_time_days": [1.0]})
        result = calculate_control_chart_stats(data, window_size=5)
        assert result.is_empty()
        assert set(result.columns) == {
            "issue_id",
            "lead_time_days",
            "commitment_end_at",
            "rolling_mean",
            "rolling_std",
            "ucl_3sigma",
            "lcl_3sigma",
            "is_outlier",
        }

    def test_control_chart_normalizes_non_positive_window_size(self):
        data = pl.DataFrame(
            {
                "issue_id": ["a", "b"],
                "lead_time_days": [3, 5],
                "commitment_end_at": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            }
        )

        result = calculate_control_chart_stats(data, window_size=0)
        assert result["rolling_mean"].to_list() == [3.0, 5.0]
