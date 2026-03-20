from datetime import datetime

import polars as pl

from pipelines.calculations.flow_efficiency import calculate_flow_efficiency_per_issue


def test_flow_efficiency_empty_inputs_returns_schema_df():
    result = calculate_flow_efficiency_per_issue(
        issues_df=pl.DataFrame(),
        status_changelog_df=pl.DataFrame(),
        active_status_ids=["in_progress"],
        wait_status_ids=["todo"],
        end_status_ids=["done"],
    )
    assert result.is_empty()
    assert "efficiency_pct" in result.columns


def test_flow_efficiency_no_completed_events_returns_empty():
    issues = pl.DataFrame({"id": ["i1"], "project_id": ["p1"], "key": ["P1-1"]})
    changelog = pl.DataFrame(
        {
            "issue_id": ["i1", "i1"],
            "to_status_id": ["todo", "in_progress"],
            "changed_at": [datetime(2026, 1, 1), datetime(2026, 1, 2)],
        }
    )

    result = calculate_flow_efficiency_per_issue(
        issues_df=issues,
        status_changelog_df=changelog,
        active_status_ids=["in_progress"],
        wait_status_ids=["todo"],
        end_status_ids=["done"],
    )
    assert result.is_empty()


def test_flow_efficiency_calculation_happy_path():
    issues = pl.DataFrame({"id": ["i1"], "project_id": ["p1"], "key": ["P1-1"]})
    changelog = pl.DataFrame(
        {
            "issue_id": ["i1", "i1", "i1"],
            "to_status_id": ["todo", "in_progress", "done"],
            "changed_at": [
                datetime(2026, 1, 1, 0, 0),
                datetime(2026, 1, 3, 0, 0),
                datetime(2026, 1, 7, 0, 0),
            ],
        }
    )

    result = calculate_flow_efficiency_per_issue(
        issues_df=issues,
        status_changelog_df=changelog,
        active_status_ids=["in_progress"],
        wait_status_ids=["todo"],
        end_status_ids=["done"],
    )

    assert result.height == 1
    row = result.to_dicts()[0]
    assert row["issue_id"] == "i1"
    assert row["wait_days"] == 2.0
    assert row["active_days"] == 4.0
    assert row["efficiency_pct"] == 66.67
