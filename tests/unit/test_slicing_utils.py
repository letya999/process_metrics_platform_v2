import polars as pl
import pytest

from pipelines.calculations import slicing_utils
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules


class TestSlicingUtils:
    @pytest.fixture
    def df(self):
        return pl.DataFrame(
            {
                "project_id": ["p1", "p1", "p1", "p2"],
                "issue_type": ["Bug", "Story", "Bug", "Story"],
                "priority": ["High", "Low", "Medium", "High"],
                "value": [10, 20, 30, 40],
            }
        )

    def test_apply_slicing_basic_exact_match(self, df):
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

        result = apply_slicing(df, rules_df, mock_calc)

        assert len(result) == 3
        # rule-1, Bug (p1) -> 10 + 30 = 40
        # rule-1, Story (p1) -> 20
        # rule-1, Story (p2) -> 40
        bug_res = result.filter(
            (pl.col("slice_value") == "Bug") & (pl.col("project_id") == "p1")
        )
        assert bug_res["sum_val"][0] == 40
        assert bug_res["slice_rule_id"][0] == "rule-1"
        assert bug_res["slice_rule_name"][0] == "By Issue Type"

    def test_apply_slicing_project_specific(self, df):
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

        result = apply_slicing(df, rules_df, mock_calc)

        # Only p1 data should be processed
        assert len(result) == 2  # Bug, Story for p1
        assert result["sum_val"].sum() == 60  # 10 + 20 + 30
        assert (result["project_id"] == "p1").all()

    def test_apply_slicing_empty_df(self):
        df = pl.DataFrame()
        rules = pl.DataFrame({"slice_rule_id": ["r1"]})
        result = apply_slicing(df, rules, lambda x: x)
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


def test_apply_slicing_heuristic_column_match_and_missing_project_id():
    df = pl.DataFrame(
        {
            "bug_priority": ["High", "Low"],
            "value": [2, 3],
        }
    )
    rules_df = pl.DataFrame(
        {
            "slice_rule_id": ["r1"],
            "slice_rule_name": ["By Priority"],
            "group_by_column": ["priority"],
            "source_table": ["clean_jira.bugs"],
            "project_id": [None],
            "enabled": [True],
        }
    )

    def calc(subset_df):
        return subset_df.select(pl.col("value").sum().alias("sum_val"))

    result = apply_slicing(df, rules_df, calc)
    assert result.height == 2
    assert set(result["slice_value"].to_list()) == {"High", "Low"}


def test_apply_slicing_calc_empty_and_target_col_missing():
    df = pl.DataFrame(
        {
            "project_id": ["p1", "p2"],
            "issue_type": ["Bug", "Story"],
            "value": [1, 2],
        }
    )
    rules_df = pl.DataFrame(
        {
            "slice_rule_id": ["r-missing", "r-calc-empty"],
            "slice_rule_name": ["MissingCol", "CalcEmpty"],
            "group_by_column": ["non_existing_col", "issue_type"],
            "source_table": ["clean_jira.issues", "clean_jira.issues"],
            "project_id": [None, None],
            "enabled": [True, True],
        }
    )

    def calc(_subset_df):
        return pl.DataFrame()

    result = apply_slicing(df, rules_df, calc)
    assert result.is_empty()


def test_apply_slicing_adds_project_id_when_result_missing():
    df = pl.DataFrame(
        {
            "project_id": ["p1", "p1"],
            "issue_type": ["Bug", "Story"],
            "value": [1, 2],
        }
    )
    rules_df = pl.DataFrame(
        {
            "slice_rule_id": ["r1"],
            "slice_rule_name": ["P1"],
            "group_by_column": ["issue_type"],
            "source_table": ["clean_jira.issues"],
            "project_id": ["p1"],
            "enabled": [True],
        }
    )

    def calc(subset_df):
        return subset_df.select(pl.col("value").sum().alias("sum_val"))

    result = apply_slicing(df, rules_df, calc)
    assert not result.is_empty()
    assert "project_id" in result.columns
    assert (result["project_id"] == "p1").all()
