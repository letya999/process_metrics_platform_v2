from datetime import datetime

import polars as pl

from pipelines.calculations import estimation as logic


def test_calculate_estimate_volatility_basic():
    issues = pl.DataFrame({"id": ["I1"], "issue_key": ["K1"], "project_id": ["P1"]})
    field_changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "field_key_id": ["SP"],
            "old_value": ["2"],
            "new_value": ["5"],
            "change_time": [datetime(2024, 1, 5)],
        }
    )
    field_values = pl.DataFrame(
        {"issue_id": ["I1"], "field_key_id": ["SP"], "json_value": ["5"]}
    )

    result = logic.calculate_estimate_volatility(
        issues, field_changelog, field_values, "SP"
    )

    assert result[0, "volatility"] == 3.0
    assert result[0, "initial_sp"] == 2.0
    assert result[0, "final_sp"] == 5.0


def test_calculate_estimate_volatility_no_changelog():
    """Without changelog, volatility is 0 (initial == final)."""
    issues = pl.DataFrame({"id": ["I1"], "issue_key": ["K1"], "project_id": ["P1"]})
    fv = pl.DataFrame({"issue_id": ["I1"], "field_key_id": ["SP"], "json_value": ["5"]})
    empty_fvc = pl.DataFrame(
        schema={
            "issue_id": pl.Utf8,
            "field_key_id": pl.Utf8,
            "old_value": pl.Utf8,
            "new_value": pl.Utf8,
            "change_time": pl.Datetime,
        }
    )
    result = logic.calculate_estimate_volatility(issues, empty_fvc, fv, "SP")
    assert result[0, "volatility"] == 0.0


def test_calculate_estimate_volatility_null_sp_treated_as_zero():
    """Null SP counts as 0 for volatility calculation."""
    issues = pl.DataFrame({"id": ["I1"], "issue_key": ["K1"], "project_id": ["P1"]})
    fv = pl.DataFrame(
        schema={"issue_id": pl.Utf8, "field_key_id": pl.Utf8, "json_value": pl.Utf8}
    )  # no SP entry
    fvc = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "field_key_id": ["SP"],
            "old_value": ["3"],
            "new_value": [None],
            "change_time": [datetime(2024, 1, 5)],
        }
    )
    result = logic.calculate_estimate_volatility(issues, fvc, fv, "SP")
    # initial=3, final=0 (null treated as 0) → volatility=3
    assert result[0, "volatility"] == 3.0
