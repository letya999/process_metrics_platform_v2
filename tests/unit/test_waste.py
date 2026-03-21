from datetime import date, datetime

import polars as pl

from pipelines.calculations import waste as logic


def test_calculate_cancellation_rate_weekly_basic():
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "to_status_id": ["CANCEL", "CANCEL"],
            "changed_at": [datetime(2024, 1, 1), datetime(2024, 1, 8)],
        }
    )
    issues = pl.DataFrame({"id": ["I1", "I2"], "project_id": ["P1", "P1"]})

    result = logic.calculate_cancellation_rate_weekly(
        status_changelog, ["CANCEL"], issues
    )

    assert (
        result.filter(pl.col("iso_week_start_date") == date(2024, 1, 1))[
            0, "cancellation_count"
        ]
        == 1
    )
    assert (
        result.filter(pl.col("iso_week_start_date") == date(2024, 1, 8))[
            0, "cancellation_count"
        ]
        == 1
    )


def test_calculate_cancellation_rate_weekly_empty_changelog():
    """Empty changelog returns empty DataFrame with correct schema."""
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
    empty_cl = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    result = logic.calculate_cancellation_rate_weekly(empty_cl, ["CANCELLED"], issues)
    assert result.is_empty()
    assert "cancellation_count" in result.columns


def test_calculate_cancellation_rate_weekly_no_cancellations():
    """Status transitions to non-cancelled statuses not counted."""
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
    cl = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 5)],
        }
    )
    result = logic.calculate_cancellation_rate_weekly(cl, ["CANCELLED"], issues)
    assert result.is_empty()
