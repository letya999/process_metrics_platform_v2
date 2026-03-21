from datetime import date, datetime

import polars as pl

from pipelines.calculations.velocity import (
    extract_story_points,
    identify_sprint_commitment,
)


def test_identify_sprint_commitment_no_created_at_col():
    # issues_df without jira_created_at
    issues = pl.DataFrame({"id": ["I1"], "type_name": ["Story"]})
    sprints = pl.DataFrame({"id": ["S1"], "start_date": [date(2025, 1, 1)]})
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})

    # Empty changelog
    res = identify_sprint_commitment(pl.DataFrame(), sprints, issues, sprint_issues)
    assert res.height == 1


def test_identify_sprint_commitment_ghost_issues():
    # Issue removed after start but never added explicitly
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "type_name": ["Story"],
            "jira_created_at": [datetime(2024, 12, 1)],
        }
    )
    sprints = pl.DataFrame({"id": ["S1"], "start_date": [datetime(2025, 1, 1)]})
    # Changelog only has removal
    changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "sprint_id": ["S1"],
            "action": ["removed"],
            "changed_at": [datetime(2025, 1, 2)],
        }
    )

    res = identify_sprint_commitment(changelog, sprints, issues, None)
    assert res.height == 1
    assert res["issue_id"][0] == "I1"


def test_extract_story_points_bad_json():
    issues = pl.DataFrame({"id": ["I1"]})
    # json_value is not a valid number or JSON
    values = pl.DataFrame(
        {"issue_id": ["I1"], "field_key_id": ["K1"], "json_value": ["invalid"]}
    )
    keys = pl.DataFrame(
        {"id": ["K1"], "external_key": ["customfield_10001"], "name": ["Story Points"]}
    )

    res = extract_story_points(issues, values, keys)
    # Should fallback to 0.0 or handle gracefully
    assert res["story_points"][0] == 0.0
