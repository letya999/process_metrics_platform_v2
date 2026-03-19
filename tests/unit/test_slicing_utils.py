from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from pipelines.calculations import slicing_utils
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules


class TestSlicingUtils:
    @pytest.fixture
    def df(self):
        return pl.DataFrame(
            {
                "id": ["i1", "i2", "i3", "i4"],
                "project_id": ["p1", "p1", "p1", "p2"],
                "issue_type": ["Bug", "Story", "Bug", "Story"],
                "priority": ["High", "Low", "Medium", "High"],
                "value": [10, 20, 30, 40],
            }
        )

    @pytest.fixture
    def mock_engine(self):
        return MagicMock()

    def test_apply_slicing_basic_exact_match(self, df, mock_engine):
        rules_df = pl.DataFrame(
            {
                "slice_rule_id": ["rule-1"],
                "slice_rule_name": ["By Issue Type"],
                "group_by_column": ["issue_type"],
                "project_id": [None],
                "enabled": [True],
            }
        )

        def mock_calc(subset_df):
            return subset_df.select(pl.col("value").sum().alias("sum_val"))

        result = apply_slicing(df, rules_df, mock_calc, engine=mock_engine)

        assert len(result) == 3
        bug_res = result.filter(
            (pl.col("slice_value") == "Bug") & (pl.col("project_id") == "p1")
        )
        assert bug_res["sum_val"][0] == 40
        assert bug_res["slice_rule_id"][0] == "rule-1"

    def test_apply_slicing_project_specific(self, df, mock_engine):
        rules_df = pl.DataFrame(
            {
                "slice_rule_id": ["rule-p1"],
                "slice_rule_name": ["P1 Specific"],
                "group_by_column": ["issue_type"],
                "project_id": ["p1"],
                "enabled": [True],
            }
        )

        def mock_calc(subset_df):
            return subset_df.select(pl.col("value").sum().alias("sum_val"))

        result = apply_slicing(df, rules_df, mock_calc, engine=mock_engine)

        assert len(result) == 2
        assert result["sum_val"].sum() == 60
        assert (result["project_id"] == "p1").all()

    def test_apply_slicing_empty_df(self, mock_engine):
        df = pl.DataFrame()
        rules = pl.DataFrame({"slice_rule_id": ["r1"]})
        result = apply_slicing(df, rules, lambda x: x, engine=mock_engine)
        assert result.is_empty()


def test_get_slice_rules_filters_project_and_definition(monkeypatch):
    monkeypatch.setattr(
        slicing_utils,
        "read_table",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r-global", "r-project", "r-other-def"],
                "project_id": [None, "p1", "p1"],
                "target_definition_id": [None, "def-1", "def-2"],
                "slice_rule_name": ["Global", "Project", "OtherDef"],
                "source_table": ["clean_jira.issues"] * 3,
                "group_by_column": ["issue_type"] * 3,
                "enabled": [True, True, True],
            }
        ),
    )

    result = get_slice_rules(object(), project_id="p1", target_definition_id="def-1")

    assert result.height == 2
    assert set(result["slice_rule_id"].to_list()) == {"r-global", "r-project"}


def test_get_slice_rules_returns_empty_on_read_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("db error")

    monkeypatch.setattr(slicing_utils, "read_table", _raise)

    result = get_slice_rules(object(), project_id="p1", target_definition_id="def-1")
    assert result.is_empty()


def test_apply_slicing_heuristic_column_match():
    # Heuristic match: 'priority' -> 'priority_name'
    df = pl.DataFrame(
        {
            "id": ["i1", "i2"],
            "priority_name": ["High", "Low"],
            "value": [2, 3],
        }
    )
    rules_df = pl.DataFrame(
        {
            "slice_rule_id": ["r1"],
            "slice_rule_name": ["By Priority"],
            "group_by_column": ["priority"],
            "source_table": ["clean_jira.issues"],
            "project_id": [None],
            "enabled": [True],
        }
    )

    def calc(subset_df):
        return subset_df.select(pl.col("value").sum().alias("sum_val"))

    mock_engine = MagicMock()
    result = apply_slicing(df, rules_df, calc, engine=mock_engine)
    assert result.height == 2
    assert set(result["slice_value"].to_list()) == {"High", "Low"}


def test_apply_slicing_suffix_heuristic():
    # Suffix match: 'issue_type' -> 'type_name'
    df = pl.DataFrame(
        {
            "id": ["i1", "i2"],
            "type_name": ["Bug", "Story"],
            "value": [2, 3],
        }
    )
    rules_df = pl.DataFrame(
        {
            "slice_rule_id": ["r1"],
            "slice_rule_name": ["By Issue Type"],
            "group_by_column": ["issue_type"],
            "source_table": ["clean_jira.issues"],
            "project_id": [None],
            "enabled": [True],
        }
    )

    def calc(subset_df):
        return subset_df.select(pl.col("value").sum().alias("sum_val"))

    mock_engine = MagicMock()
    result = apply_slicing(df, rules_df, calc, engine=mock_engine)
    assert result.height == 2
    assert set(result["slice_value"].to_list()) == {"Bug", "Story"}


def test_apply_slicing_dynamic_injection():
    # Test SmartSlicer integration
    df = pl.DataFrame({"id": ["i1", "i2"], "value": [10, 20]})
    rules_df = pl.DataFrame(
        {
            "slice_rule_id": ["r-dyn"],
            "slice_rule_name": ["Dynamic"],
            "group_by_column": ["sprint_name"],
            "source_table": ["clean_jira.sprints"],
            "project_id": [None],
            "enabled": [True],
        }
    )

    mapping_df = pl.DataFrame(
        {"source_id": ["i1", "i2"], "slice_value": ["Sprint 1", "Sprint 1"]}
    )

    def calc(subset_df):
        return subset_df.select(pl.col("value").sum().alias("sum_val"))

    mock_engine = MagicMock()

    with patch("pipelines.calculations.slicing_utils.SmartSlicer") as mock_slicer_cls:
        mock_slicer = mock_slicer_cls.return_value
        mock_slicer.get_slice_mapping.return_value = mapping_df

        result = apply_slicing(df, rules_df, calc, engine=mock_engine)

        assert not result.is_empty()
        assert result["slice_value"][0] == "Sprint 1"
        assert result["sum_val"][0] == 30
