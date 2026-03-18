import polars as pl
import pytest

from pipelines.calculations.slicing_utils import apply_slicing


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
        bug_res = result.filter(pl.col("slice_value") == "Bug")
        assert bug_res["sum_val"][0] == 40
        assert bug_res["slice_rule_id"][0] == "rule-1"
        assert bug_res["slice_rule_name"][0] == "By Issue Type"

    def test_apply_slicing_with_filter_condition(self, df):
        rules_df = pl.DataFrame(
            {
                "slice_rule_id": ["rule-filtered"],
                "slice_rule_name": ["High Priority Only"],
                "group_by_column": ["issue_type"],
                "filter_condition": ["priority = 'High'"],
                "project_id": [None],
                "enabled": [True],
            }
        )

        def mock_calc(subset_df):
            return subset_df.select(pl.col("value").sum().alias("sum_val"))

        result = apply_slicing(df, rules_df, mock_calc)

        # High priority items:
        # Bug (p1) -> 10
        # Story (p2) -> 40
        assert len(result) == 2
        assert result.filter(pl.col("slice_value") == "Bug")["sum_val"][0] == 10
        assert result.filter(pl.col("slice_value") == "Story")["sum_val"][0] == 40

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
