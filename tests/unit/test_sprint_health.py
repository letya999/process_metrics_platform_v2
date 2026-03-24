from datetime import date, datetime

import polars as pl

from pipelines.calculations import sprint_health as logic


def test_calculate_sprint_scope_changes_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
            "complete_date": [datetime(2024, 1, 14)],
        }
    )
    changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "sprint_id": ["S1", "S1"],
            "action": ["added", "removed"],
            "changed_at": [datetime(2024, 1, 5), datetime(2024, 1, 6)],
        }
    )
    issues = pl.DataFrame(
        {"id": ["I1", "I2"], "project_id": ["P1", "P1"], "issue_key": ["K1", "K2"]}
    )
    field_values = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "field_key_id": ["SP", "SP"],
            "json_value": ["5", "3"],
        }
    )
    field_keys = pl.DataFrame(
        {"id": ["SP"], "external_key": ["customfield_10036"], "name": ["Story Points"]}
    )
    field_value_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )

    result = logic.calculate_sprint_scope_changes(
        sprints, changelog, issues, field_values, field_keys, field_value_changelog
    )

    assert result[0, "added_count"] == 1
    assert result[0, "added_sp"] == 5.0
    assert result[0, "removed_count"] == 1
    assert result[0, "removed_sp"] == 3.0


def test_calculate_sprint_spillover_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1", "S2"],
            "project_id": ["P1", "P1"],
            "name": ["Sprint 1", "Sprint 2"],
            "start_date": [datetime(2024, 1, 1), datetime(2024, 1, 15)],
        }
    )
    sprint_issues = pl.DataFrame(
        {"issue_id": ["I1", "I1", "I2"], "sprint_id": ["S1", "S2", "S2"]}
    )

    result = logic.calculate_sprint_spillover(sprints, sprint_issues)

    assert result.filter(pl.col("iteration_id") == "S1")[0, "spillover_count"] == 1
    assert result.filter(pl.col("iteration_id") == "S2")[0, "spillover_count"] == 1


def test_calculate_sprint_burndown_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 3)],
            "complete_date": [datetime(2024, 1, 3)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    # I1, I2 in commitment
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "sprint_id": ["S1", "S1"],
            "action": ["added", "added"],
            "changed_at": [datetime(2023, 12, 31), datetime(2023, 12, 31)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 2, 10, 0)],
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "type_name": ["Task", "Task"],
            "jira_created_at": [datetime(2023, 12, 1), datetime(2023, 12, 1)],
        }
    )
    field_values = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "field_key_id": ["SP", "SP"],
            "json_value": ["5", "3"],
        }
    )
    field_keys = pl.DataFrame(
        {"id": ["SP"], "external_key": ["customfield_10036"], "name": ["Story Points"]}
    )
    field_value_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )

    result = logic.calculate_sprint_burndown(
        sprints,
        sprint_issues,
        sprint_changelog,
        status_changelog,
        ["DONE"],
        issues,
        field_values,
        field_keys,
        field_value_changelog,
    )

    # 2024-01-01: 8.0 remaining
    # 2024-01-02: 3.0 remaining (I1 done)
    # 2024-01-03: 3.0 remaining

    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 1))[0, "remaining_sp"] == 8.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 2))[0, "remaining_sp"] == 3.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 3))[0, "remaining_sp"] == 3.0
    )


def test_calculate_sprint_burndown_duplicate_done_transitions():
    """Regression: issue going Canceled -> Done (both done statuses) within seconds
    must not be double-counted. Old code multiplied SP via Cartesian product."""
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 3)],
            "complete_date": [datetime(2024, 1, 3)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "sprint_id": ["S1", "S1"],
            "action": ["added", "added"],
            "changed_at": [datetime(2023, 12, 31), datetime(2023, 12, 31)],
        }
    )
    # I1 transitions: Canceled at 10:00, then Done at 10:01 (both are done statuses)
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "to_status_id": ["CANCELED", "DONE"],
            "changed_at": [
                datetime(2024, 1, 2, 10, 0),
                datetime(2024, 1, 2, 10, 1),
            ],
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "type_name": ["Task", "Task"],
            "jira_created_at": [datetime(2023, 12, 1), datetime(2023, 12, 1)],
        }
    )
    field_values = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "field_key_id": ["SP", "SP"],
            "json_value": ["5", "3"],
        }
    )
    field_keys = pl.DataFrame(
        {"id": ["SP"], "external_key": ["customfield_10036"], "name": ["Story Points"]}
    )
    field_value_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )

    result = logic.calculate_sprint_burndown(
        sprints,
        sprint_issues,
        sprint_changelog,
        status_changelog,
        ["CANCELED", "DONE"],
        issues,
        field_values,
        field_keys,
        field_value_changelog,
    )

    # Day 1: 8 remaining (both issues in scope, neither done)
    # Day 2: I1 done (last status = DONE) -> 3 remaining
    # Day 3: 3 remaining
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 1))[0, "remaining_sp"] == 8.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 2))[0, "remaining_sp"] == 3.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 3))[0, "remaining_sp"] == 3.0
    )


def test_calculate_sprint_burndown_scope_changes():
    """Regression: issue removed mid-sprint must reduce remaining SP on removal day."""
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 4)],
            "complete_date": [datetime(2024, 1, 4)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    # I1 added at sprint start, removed on day 2; I2 added at sprint start
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1", "I2"],
            "sprint_id": ["S1", "S1", "S1"],
            "action": ["added", "removed", "added"],
            "changed_at": [
                datetime(2024, 1, 1, 0, 0),
                datetime(2024, 1, 2, 12, 0),
                datetime(2024, 1, 1, 0, 0),
            ],
        }
    )
    status_changelog = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "type_name": ["Task", "Task"],
            "jira_created_at": [datetime(2023, 12, 1), datetime(2023, 12, 1)],
        }
    )
    field_values = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "field_key_id": ["SP", "SP"],
            "json_value": ["8", "3"],
        }
    )
    field_keys = pl.DataFrame(
        {"id": ["SP"], "external_key": ["customfield_10036"], "name": ["Story Points"]}
    )
    field_value_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )

    result = logic.calculate_sprint_burndown(
        sprints,
        sprint_issues,
        sprint_changelog,
        status_changelog,
        ["DONE"],
        issues,
        field_values,
        field_keys,
        field_value_changelog,
    )

    # Day 1: I1(8) + I2(3) = 11 remaining
    # Day 2: I1 removed -> only I2(3) = 3 remaining
    # Day 3: 3 remaining
    # Day 4: 3 remaining
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 1))[0, "remaining_sp"]
        == 11.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 2))[0, "remaining_sp"] == 3.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 3))[0, "remaining_sp"] == 3.0
    )


def test_calculate_activation_velocity_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 3)],
            "complete_date": [datetime(2024, 1, 3)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "sprint_id": ["S1", "S1"],
            "action": ["added", "added"],
            "changed_at": [datetime(2023, 12, 31), datetime(2023, 12, 31)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "from_status_id": ["TODO"],
            "to_status_id": ["INPROG"],
            "changed_at": [datetime(2024, 1, 2, 10, 0)],
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "type_name": ["Task", "Task"],
            "jira_created_at": [datetime(2023, 12, 1), datetime(2023, 12, 1)],
        }
    )
    field_values = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "field_key_id": ["SP", "SP"],
            "json_value": ["5", "5"],
        }
    )
    field_keys = pl.DataFrame(
        {"id": ["SP"], "external_key": ["customfield_10036"], "name": ["Story Points"]}
    )
    field_value_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )

    result = logic.calculate_activation_velocity(
        sprints,
        sprint_issues,
        sprint_changelog,
        status_changelog,
        issues,
        field_values,
        field_keys,
        field_value_changelog,
        "TODO",
    )

    # Day 1: 0%
    # Day 2: (5 / 10) * 100 = 50%
    # Day 3: 50%

    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 1))[0, "activation_pct"]
        == 0.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2024, 1, 2))[0, "activation_pct"]
        == 50.0
    )


def test_calculate_unestimated_closed_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
            "complete_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    sprint_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "sprint_id": pl.Utf8,
            "action": pl.Utf8,
            "changed_at": pl.Datetime,
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "status_id": ["DONE", "DONE"],
            "jira_resolved_at": [datetime(2024, 1, 10), datetime(2024, 1, 10)],
            "type_name": ["Task", "Task"],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "from_status_id": ["TODO", "TODO"],
            "to_status_id": ["DONE", "DONE"],
            "changed_at": [datetime(2024, 1, 10), datetime(2024, 1, 10)],
        }
    )
    field_values = pl.DataFrame(
        {"issue_id": ["I1"], "field_key_id": ["SP"], "json_value": ["0"]}
    )  # I2 is missing (null SP)
    result = logic.calculate_unestimated_closed(
        sprints,
        sprint_issues,
        sprint_changelog,
        issues,
        status_changelog,
        ["DONE"],
        field_values,
        "SP",
    )

    assert (
        result[0, "unestimated_count"] == 2
    )  # Both I1 (0) and I2 (null) are unestimated


def test_calculate_sprint_scope_changes_empty_changelog():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    empty_cl = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "sprint_id": pl.Utf8,
            "action": pl.Utf8,
            "changed_at": pl.Datetime,
        }
    )
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"], "issue_key": ["K1"]})
    fv = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "field_key_id": pl.Utf8, "json_value": pl.Utf8}
    )
    fk = pl.DataFrame({"id": ["SP"], "external_key": ["cf"], "name": ["Story Points"]})
    fvc = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )
    result = logic.calculate_sprint_scope_changes(
        sprints, empty_cl, issues, fv, fk, fvc
    )
    assert "start_date" in result.columns  # verify consistent schema
    assert result.is_empty()


def test_calculate_sprint_spillover_single_sprint_not_counted():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S1"]})
    result = logic.calculate_sprint_spillover(sprints, sprint_issues)
    assert result[0, "spillover_count"] == 0  # issues in ONE sprint are not spillover


def test_calculate_sprint_burndown_no_completions():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 3)],
            "complete_date": [datetime(2024, 1, 3)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "sprint_id": ["S1"],
            "action": ["added"],
            "changed_at": [datetime(2023, 12, 31)],
        }
    )
    status_changelog = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "project_id": ["P1"],
            "type_name": ["Task"],
            "jira_created_at": [datetime(2023, 12, 1)],
        }
    )
    fv = pl.DataFrame({"issue_id": ["I1"], "field_key_id": ["SP"], "json_value": ["8"]})
    fk = pl.DataFrame({"id": ["SP"], "external_key": ["cf"], "name": ["Story Points"]})
    fvc = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )
    result = logic.calculate_sprint_burndown(
        sprints,
        sprint_issues,
        sprint_changelog,
        status_changelog,
        ["DONE"],
        issues,
        fv,
        fk,
        fvc,
    )
    # All days should have same remaining_sp = 8.0
    assert all(result["remaining_sp"] == 8.0)
    assert len(result) == 3  # Jan 1, 2, 3


def test_calculate_activation_velocity_zero_planned_sp():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 2)],
            "complete_date": [datetime(2024, 1, 2)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "sprint_id": ["S1"],
            "action": ["added"],
            "changed_at": [datetime(2023, 12, 31)],
        }
    )
    status_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "from_status_id": pl.Utf8,
            "to_status_id": pl.Utf8,
            "changed_at": pl.Datetime,
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "project_id": ["P1"],
            "type_name": ["Task"],
            "jira_created_at": [datetime(2023, 12, 1)],
        }
    )
    # no SP assigned (null)
    fv = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "field_key_id": pl.Utf8, "json_value": pl.Utf8}
    )
    fk = pl.DataFrame({"id": ["SP"], "external_key": ["cf"], "name": ["Story Points"]})
    fvc = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )
    # Should not raise ZeroDivisionError
    result = logic.calculate_activation_velocity(
        sprints,
        sprint_issues,
        sprint_changelog,
        status_changelog,
        issues,
        fv,
        fk,
        fvc,
        "TODO",
    )
    assert all(result["activation_pct"] == 0.0)


def test_calculate_field_value_sprint_pct_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
        }
    )
    sprint_issues = pl.DataFrame(
        {"issue_id": ["I1", "I2", "I3"], "sprint_id": ["S1", "S1", "S1"]}
    )
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2", "I3"],
            "project_id": ["P1", "P1", "P1"],
            "issue_key": ["K1", "K2", "K3"],
        }
    )
    fv = pl.DataFrame(
        {
            "issue_id": ["I1", "I2", "I3"],
            "field_key_id": ["PR", "PR", "PR"],
            "json_value": ["Highest", "Highest", "Low"],
        }
    )
    fk = pl.DataFrame(
        {"id": ["PR"], "external_key": ["cf_priority"], "name": ["priority"]}
    )
    result = logic.calculate_field_value_sprint_pct(
        sprints, sprint_issues, issues, "priority", "Highest", fv, fk
    )
    # 2 out of 3 = 66.67%
    assert abs(result[0, "field_pct"] - 66.67) < 0.1


def test_calculate_field_value_sprint_pct_unknown_field():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"], "issue_key": ["K1"]})
    fv = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "field_key_id": pl.Utf8, "json_value": pl.Utf8}
    )
    fk = pl.DataFrame({"id": ["SP"], "external_key": ["cf"], "name": ["Story Points"]})
    result = logic.calculate_field_value_sprint_pct(
        sprints, sprint_issues, issues, "nonexistent_field", "value", fv, fk
    )
    assert result[0, "field_pct"] == 0.0


def test_calculate_unestimated_closed_none_unestimated():
    """When all closed issues have SP > 0, count should be 0."""
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
            "complete_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    sprint_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "sprint_id": pl.Utf8,
            "action": pl.Utf8,
            "changed_at": pl.Datetime,
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "project_id": ["P1"],
            "status_id": ["DONE"],
            "jira_resolved_at": [datetime(2024, 1, 10)],
            "type_name": ["Task"],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "from_status_id": ["TODO"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2024, 1, 10)],
        }
    )
    fv = pl.DataFrame(
        {"issue_id": ["I1"], "field_key_id": ["SP"], "json_value": ["5"]}
    )  # has SP
    result = logic.calculate_unestimated_closed(
        sprints,
        sprint_issues,
        sprint_changelog,
        issues,
        status_changelog,
        ["DONE"],
        fv,
        "SP",
    )
    assert result[0, "unestimated_count"] == 0
