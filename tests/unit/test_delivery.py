from datetime import date, datetime

import polars as pl

from pipelines.calculations import delivery as logic


def test_calculate_release_burnup_basic():
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "created_at": [datetime(2025, 6, 1), datetime(2025, 6, 2)],
        }
    )
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["DONE"],
            "changed_at": [datetime(2025, 6, 3)],
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
    field_changelog = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )
    fix_versions = pl.DataFrame(
        {"issue_id": ["I1", "I2"], "version_name": ["V1", "V1"]}
    )

    result = logic.calculate_release_burnup(
        issues,
        status_changelog,
        ["DONE"],
        field_values,
        field_keys,
        field_changelog,
        fix_versions,
    )

    # 2025-06-01: scope=5 (I1 created), done=0
    # 2025-06-02: scope=8 (I2 created), done=0
    # 2025-06-03: scope=8, done=5 (I1 completed)
    assert (
        result.filter(pl.col("time_date") == date(2025, 6, 1)).select("scope_sp").item()
        == 5.0
    )
    assert (
        result.filter(pl.col("time_date") == date(2025, 6, 3)).select("done_sp").item()
        == 5.0
    )


def test_to_date_utility():
    """Test internal _to_date utility in delivery.py."""
    from datetime import date, datetime

    assert logic._to_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert logic._to_date(datetime(2025, 1, 1, 10, 0)) == date(2025, 1, 1)
    assert logic._to_date("2025-01-01T10:00:00") == date(2025, 1, 1)
    assert logic._to_date(123) == 123  # Fallback


def test_calculate_release_burnup_empty_input():
    """Test calculate_release_burnup with various empty inputs."""
    issues = pl.DataFrame(
        schema={"id": pl.Utf8, "project_id": pl.Utf8, "created_at": pl.Datetime}
    )
    changelog = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    field_values = pl.DataFrame()
    field_keys = pl.DataFrame()
    field_changelog = pl.DataFrame()

    # fix_versions_df is None
    result = logic.calculate_release_burnup(
        issues, changelog, ["DONE"], field_values, field_keys, field_changelog, None
    )
    assert result.is_empty()
    assert "scope_sp" in result.columns

    # all_data is empty (no versions matched)
    fix_versions = pl.DataFrame({"issue_id": ["I1"], "version_name": ["V1"]})
    result = logic.calculate_release_burnup(
        issues,
        changelog,
        ["DONE"],
        field_values,
        field_keys,
        field_changelog,
        fix_versions,
    )
    assert result.is_empty()


def test_calculate_release_burnup_empty_fix_versions():
    """Empty fix_versions returns empty DataFrame gracefully."""
    issues = pl.DataFrame(
        {"id": ["I1"], "project_id": ["P1"], "created_at": [datetime(2025, 6, 1)]}
    )
    cl = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
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
    result = logic.calculate_release_burnup(
        issues, cl, ["DONE"], fv, fk, fvc, fix_versions_df=None
    )
    assert result.is_empty()
    assert "scope_sp" in result.columns


def test_calculate_release_burnup_scope_grows_cumulatively():
    """Scope line is cumulative — grows as more issues are created."""
    issues = pl.DataFrame(
        {
            "id": ["I1", "I2"],
            "project_id": ["P1", "P1"],
            "created_at": [datetime(2025, 6, 1), datetime(2025, 6, 3)],
        }
    )
    cl = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "to_status_id": pl.Utf8, "changed_at": pl.Datetime}
    )
    fv = pl.DataFrame(
        {
            "issue_id": ["I1", "I2"],
            "field_key_id": ["SP", "SP"],
            "json_value": ["5", "3"],
        }
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
    fix_versions = pl.DataFrame(
        {"issue_id": ["I1", "I2"], "version_name": ["V1", "V1"]}
    )
    result = logic.calculate_release_burnup(
        issues, cl, ["DONE"], fv, fk, fvc, fix_versions
    )
    scope_d1 = (
        result.filter(pl.col("time_date") == date(2025, 6, 1)).select("scope_sp").item()
    )
    scope_d3 = (
        result.filter(pl.col("time_date") == date(2025, 6, 3)).select("scope_sp").item()
    )
    assert scope_d1 == 5.0  # only I1 created
    assert scope_d3 == 8.0  # I1 + I2
