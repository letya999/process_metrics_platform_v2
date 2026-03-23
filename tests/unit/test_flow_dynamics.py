from datetime import date, datetime

import polars as pl

from pipelines.calculations import flow_dynamics as logic


def test_calculate_daily_status_entry_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2", "I3"],
            "to_status_id": ["INPROG", "INPROG", "INPROG"],
            "changed_at": [
                datetime(2024, 1, 5),
                datetime(2024, 1, 5),
                datetime(2024, 1, 5),
            ],
        }
    )
    # I3 is not in sprint

    result = logic.calculate_daily_status_entry(
        sprints, sprint_issues, status_changelog, "INPROG"
    )

    assert result.filter(pl.col("time_date") == date(2024, 1, 5))[0, "entry_count"] == 2


def test_calculate_field_change_count_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    field_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "field_key_id": ["F1", "F2"],
            "change_time": [datetime(2024, 1, 5), datetime(2024, 1, 5)],
        }
    )

    result = logic.calculate_field_change_count(
        sprints, sprint_issues, field_changelog, "F1"
    )

    assert result[0, "change_count"] == 1


def test_calculate_daily_status_entry_empty_changelog():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    empty_cl = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    result = logic.calculate_daily_status_entry(
        sprints, sprint_issues, empty_cl, "INPROG"
    )
    assert result.is_empty()
    assert "entry_count" in result.columns


def test_calculate_field_change_count_empty_changelog():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    empty_cl = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )
    result = logic.calculate_field_change_count(
        sprints, sprint_issues, empty_cl, "ASSIGNEE_FID"
    )
    assert result[0, "change_count"] == 0


def test_calculate_daily_status_entry_filters_out_of_sprint_issues():
    """Issues entering status OUTSIDE sprint date range are not counted."""
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 7)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    # changed_at is AFTER sprint end — should be excluded
    cl = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["INPROG"],
            "changed_at": [datetime(2024, 1, 10)],
        }
    )
    result = logic.calculate_daily_status_entry(sprints, sprint_issues, cl, "INPROG")
    assert result.is_empty()
