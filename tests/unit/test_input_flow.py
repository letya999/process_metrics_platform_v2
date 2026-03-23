from datetime import date, datetime

import polars as pl

from pipelines.calculations import input_flow as logic


def test_calculate_input_flow_weekly_basic():
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2", "I3"],
            "to_status_id": ["INPROG", "INPROG", "INPROG"],
            "changed_at": [
                datetime(2024, 1, 1),  # Mon (Week 1)
                datetime(2024, 1, 2),  # Tue (Week 1)
                datetime(2024, 1, 8),  # Mon (Week 2)
            ],
        }
    )
    issues = pl.DataFrame({"id": ["I1", "I2", "I3"], "project_id": ["P1", "P1", "P1"]})

    result = logic.calculate_input_flow_weekly(status_changelog, ["INPROG"], issues)

    assert (
        result.filter(pl.col("iso_week_start_date") == date(2024, 1, 1))[
            0, "flow_count"
        ]
        == 2
    )
    assert (
        result.filter(pl.col("iso_week_start_date") == date(2024, 1, 8))[
            0, "flow_count"
        ]
        == 1
    )


def test_calculate_input_flow_weekly_empty_changelog():
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
    empty_cl = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    result = logic.calculate_input_flow_weekly(empty_cl, ["INPROG"], issues)
    assert result.is_empty()


def test_calculate_input_flow_weekly_deduplicates_same_issue():
    """Same issue entering start status twice in one week counts as 1."""
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
    cl = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "to_status_id": ["INPROG", "INPROG"],
            "changed_at": [datetime(2024, 1, 2, 9, 0), datetime(2024, 1, 3, 10, 0)],
        }
    )
    result = logic.calculate_input_flow_weekly(cl, ["INPROG"], issues)
    assert result[0, "flow_count"] == 1
