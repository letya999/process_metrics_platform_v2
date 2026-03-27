from datetime import datetime

import polars as pl

from pipelines.calculations.velocity import (
    determine_story_points_at_date,
    extract_story_points,
)


def test_extract_story_points_uses_override_when_provided():
    # Setup data with two potential SP fields
    issues_df = pl.DataFrame({"id": ["I1", "I2"]})
    field_keys_df = pl.DataFrame(
        [
            {"id": "K1", "external_key": "customfield_10036", "name": "Story Points"},
            {"id": "K2", "external_key": "customfield_999", "name": "My Custom SP"},
        ]
    )
    field_values_df = pl.DataFrame(
        [
            {"issue_id": "I1", "field_key_id": "K1", "json_value": "5.0"},
            {"issue_id": "I1", "field_key_id": "K2", "json_value": "10.0"},
            {"issue_id": "I2", "field_key_id": "K2", "json_value": "8.0"},
        ]
    )

    # 1. Without override: should use K1 (heuristic match)
    res_no_override = extract_story_points(issues_df, field_values_df, field_keys_df)
    assert res_no_override.filter(pl.col("issue_id") == "I1")["story_points"][0] == 5.0
    assert (
        res_no_override.filter(pl.col("issue_id") == "I2")["story_points"][0] == 0.0
    )  # K1 not present for I2

    # 2. With override: should use K2 only
    res_with_override = extract_story_points(
        issues_df, field_values_df, field_keys_df, sp_field_key_ids_override=["K2"]
    )
    assert (
        res_with_override.filter(pl.col("issue_id") == "I1")["story_points"][0] == 10.0
    )
    assert (
        res_with_override.filter(pl.col("issue_id") == "I2")["story_points"][0] == 8.0
    )


def test_determine_story_points_at_date_uses_override():
    # Setup - use offset-naive datetimes consistently
    scope_df = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    sprints_df = pl.DataFrame({"id": ["S1"], "start_date": [datetime(2026, 1, 1)]})

    current_sp_df = pl.DataFrame({"issue_id": ["I1"], "story_points": [10.0]})
    field_keys_df = pl.DataFrame(
        [
            {"id": "K1", "external_key": "customfield_10036", "name": "Story Points"},
            {"id": "K2", "external_key": "customfield_999", "name": "My Custom SP"},
        ]
    )

    # Changelog has changes for both K1 and K2
    changelog_df = pl.DataFrame(
        [
            {
                "issue_id": "I1",
                "field_key_id": "K1",
                "old_value": "3.0",
                "new_value": "10.0",
                "changed_at": datetime(2026, 1, 2),
            },
            {
                "issue_id": "I1",
                "field_key_id": "K2",
                "old_value": "7.0",
                "new_value": "10.0",
                "changed_at": datetime(2026, 1, 2),
            },
        ]
    )

    # 1. Without override: uses K1 heuristic -> historic value 3.0
    res_no_override = determine_story_points_at_date(
        scope_df, sprints_df, current_sp_df, changelog_df, field_keys_df
    )
    assert res_no_override["story_points"][0] == 3.0

    # 2. With override: uses K2 -> historic value 7.0
    res_with_override = determine_story_points_at_date(
        scope_df,
        sprints_df,
        current_sp_df,
        changelog_df,
        field_keys_df,
        sp_field_key_ids_override=["K2"],
    )
    assert res_with_override["story_points"][0] == 7.0
