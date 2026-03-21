from datetime import datetime

import polars as pl

from pipelines.calculations import cycle_time_ext as logic


def test_calculate_issue_lifetime_basic():
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "issue_key": ["K1"],
            "project_id": ["P1"],
            "created_at": [datetime(2024, 1, 1)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 5)],
        }
    )

    result = logic.calculate_issue_lifetime(issues, status_changelog, ["DONE"])

    assert result[0, "lifetime_days"] == 4.0


def test_calculate_cycle_time_custom_basic():
    issues = pl.DataFrame({"id": ["I1"], "issue_key": ["K1"], "project_id": ["P1"]})
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "to_status_id": ["START", "END"],
            "changed_at": [datetime(2024, 1, 1), datetime(2024, 1, 3)],
        }
    )

    result = logic.calculate_cycle_time_custom(issues, status_changelog, "START", "END")

    assert result[0, "cycle_days"] == 2.0


def test_calculate_epic_delivery_time_basic():
    issues = pl.DataFrame(
        {
            "id": ["E1", "I1", "I2"],
            "issue_key": ["EK1", "K1", "K2"],
            "project_id": ["P1", "P1", "P1"],
            "parent_id": [None, "E1", "E1"],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "to_status_id": ["START", "DONE"],
            "changed_at": [datetime(2024, 1, 1), datetime(2024, 1, 5)],
        }
    )

    result = logic.calculate_epic_delivery_time(
        issues, status_changelog, ["START"], ["DONE"]
    )

    # Epic starts when I1 enters START (Jan 1)
    # Epic ends when I2 enters DONE (Jan 5)
    assert result[0, "delivery_days"] == 4.0


def test_calculate_issue_lifetime_no_completions():
    """Issues without done status produce empty result."""
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "issue_key": ["K1"],
            "project_id": ["P1"],
            "created_at": [datetime(2024, 1, 1)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["INPROG"],
            "changed_at": [datetime(2024, 1, 5)],
        }
    )
    result = logic.calculate_issue_lifetime(issues, status_changelog, ["DONE"])
    assert result.is_empty()


def test_calculate_issue_lifetime_skips_negative_days():
    """Issues where done_date < created_at are filtered out."""
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "issue_key": ["K1"],
            "project_id": ["P1"],
            "created_at": [datetime(2024, 1, 10)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 5)],
        }
    )
    result = logic.calculate_issue_lifetime(issues, status_changelog, ["DONE"])
    assert result.is_empty()


def test_calculate_cycle_time_custom_end_before_start_filtered():
    """When changelog only has end status (no start), no rows produced."""
    issues = pl.DataFrame({"id": ["I1"], "issue_key": ["K1"], "project_id": ["P1"]})
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["END"],
            "changed_at": [datetime(2024, 1, 1)],
        }
    )
    result = logic.calculate_cycle_time_custom(issues, status_changelog, "START", "END")
    assert result.is_empty()


def test_calculate_epic_delivery_time_no_parent_id_column():
    """When parent_id column missing, returns empty DataFrame gracefully."""
    issues = pl.DataFrame(
        {"id": ["E1"], "issue_key": ["EK1"], "project_id": ["P1"]}
    )  # no parent_id
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["E1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 5)],
        }
    )
    result = logic.calculate_epic_delivery_time(
        issues, status_changelog, ["START"], ["DONE"]
    )
    assert result.is_empty()
    assert "delivery_days" in result.columns


def test_calculate_epic_delivery_time_no_children():
    """Epic with no children produces empty result."""
    issues = pl.DataFrame(
        {
            "id": ["E1", "I1"],
            "issue_key": ["EK1", "K1"],
            "project_id": ["P1", "P1"],
            "parent_id": [None, None],
        }
    ).with_columns(pl.col("parent_id").cast(pl.Utf8))
    status_changelog = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    result = logic.calculate_epic_delivery_time(
        issues, status_changelog, ["START"], ["DONE"]
    )
    assert result.is_empty()


def test_calculate_cycle_time_ceil_fractional():
    """Cycle time 12 hours should be ceiled to 1.0 day."""
    issues = pl.DataFrame({"id": ["I1"], "issue_key": ["K1"], "project_id": ["P1"]})
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "to_status_id": ["START", "END"],
            "changed_at": [
                datetime(2024, 1, 1, 8, 0),
                datetime(2024, 1, 1, 20, 0),
            ],
        }
    )
    result = logic.calculate_cycle_time_custom(issues, status_changelog, "START", "END")
    assert result[0, "cycle_days"] == 1.0


def test_calculate_issue_lifetime_ceil_fractional():
    """Issue lifetime 12 hours should be ceiled to 1.0 day."""
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "issue_key": ["K1"],
            "project_id": ["P1"],
            "created_at": [datetime(2024, 1, 1, 8, 0)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 1, 20, 0)],
        }
    )
    result = logic.calculate_issue_lifetime(issues, status_changelog, ["DONE"])
    assert result[0, "lifetime_days"] == 1.0
