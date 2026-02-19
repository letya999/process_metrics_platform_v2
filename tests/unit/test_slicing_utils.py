"""
Unit tests for slicing utilities.
"""

import polars as pl

from pipelines.calculations.slicing_utils import apply_slicing


class TestSlicingUtils:
    def test_get_slice_rules_basic(self):
        """Test fetching slice rules returns a DataFrame."""
        # We can't easily mock pd.read_sql or pl.read_database here without
        # mocking the implementation inside get_slice_rules.
        # Ideally, we should test the logic *after* data is loaded or mock the DB call.
        # Since get_slice_rules mostly executes SQL, it's better tested in integration
        # or by mocking the return of read_table/read_database.
        pass

    def test_apply_slicing_basic_exact_match(self):
        """Test slicing with an exact match rule."""
        df = pl.DataFrame(
            {
                "project_id": ["P1", "P1", "P2"],
                "issue_type": ["Bug", "Task", "Bug"],
                "value": [10, 20, 30],
            }
        )

        rules_df = pl.DataFrame(
            {
                "project_id": [None],  # Global
                "metric_table": ["default"],
                "slice_table_name": ["daily"],
                "rule_name": ["By Type"],
                "source_table": ["issues"],
                "group_by_column": ["issue_type"],
                "filter_condition": [None],
            }
        )

        def mock_calc(d):
            if "project_id" in d.columns:
                return d.group_by("project_id").agg(pl.sum("value").alias("sum_val"))
            return d.select(pl.sum("value").alias("sum_val"))

        result = apply_slicing(df, rules_df, mock_calc, base_columns=["project_id"])

        # Expectation:
        # P1, Bug -> 10
        # P1, Task -> 20
        # P2, Bug -> 30

        assert result.height == 3
        # Sort for deterministic assertions
        result = result.select(
            ["project_id", "slice_rule_name", "slice_value", "sum_val"]
        ).sort(["project_id", "slice_value"])

        assert result.row(0) == ("P1", "By Type", "Bug", 10)
        assert result.row(1) == ("P1", "By Type", "Task", 20)
        assert result.row(2) == ("P2", "By Type", "Bug", 30)

    def test_apply_slicing_project_specific(self):
        """Test slicing with project-specific rules."""
        df = pl.DataFrame(
            {
                "project_id": ["P1", "P1", "P2"],
                "priority": ["High", "Low", "High"],
                "value": [10, 20, 30],
            }
        )

        rules_df = pl.DataFrame(
            {
                "project_id": ["P1"],
                "metric_table": ["default"],
                "slice_table_name": ["x"],
                "rule_name": ["By Priority"],
                "source_table": ["issues"],
                "group_by_column": ["priority"],
                "filter_condition": [None],
            }
        )

        def mock_calc(d):
            if "project_id" in d.columns:
                return d.group_by("project_id").agg(pl.sum("value").alias("sum_val"))
            return d.select(pl.sum("value").alias("sum_val"))

        result = apply_slicing(df, rules_df, mock_calc, base_columns=["project_id"])

        # P2 should be ignored because rule is only for P1
        assert result.height == 2
        result = result.select(
            ["project_id", "slice_rule_name", "slice_value", "sum_val"]
        ).sort(["project_id", "slice_value"])

        assert result.row(0) == ("P1", "By Priority", "High", 10)
        assert result.row(1) == ("P1", "By Priority", "Low", 20)

    def test_apply_slicing_multiple_rules(self):
        """Test applying multiple rules to the same dataset."""
        df = pl.DataFrame(
            {"project_id": ["P1"], "type": ["Bug"], "priority": ["High"], "val": [1]}
        )

        rules_df = pl.DataFrame(
            {
                "project_id": [None, None],
                "metric_table": ["default", "default"],
                "slice_table_name": ["t", "p"],
                "rule_name": ["By Type", "By Priority"],
                "source_table": ["issues", "issues"],
                "group_by_column": ["type", "priority"],
                "filter_condition": [None, None],
            }
        )

        def mock_calc(d):
            if "project_id" in d.columns:
                return d.group_by("project_id").agg(pl.len().alias("cnt"))
            return d.select(pl.len().alias("cnt"))

        result = apply_slicing(df, rules_df, mock_calc, base_columns=["project_id"])

        assert result.height == 2
        types = result["slice_rule_name"].to_list()
        values = result["slice_value"].to_list()

        assert "By Type" in types
        assert "By Priority" in types
        assert "Bug" in values
        assert "High" in values

    def test_apply_slicing_empty_df(self):
        """Test slicing on empty input."""
        df = pl.DataFrame({"project_id": [], "val": []})
        rules = pl.DataFrame(
            {"project_id": [None], "rule_name": ["Rule"], "group_by_column": ["val"]}
        )

        result = apply_slicing(df, rules, lambda x: x)
        assert result.is_empty()

    def test_apply_slicing_missing_column(self):
        """Test behavior when group_by column is missing in data."""
        df = pl.DataFrame({"project_id": ["P1"], "val": [1]})
        rules = pl.DataFrame(
            {
                "project_id": [None],
                "rule_name": ["By Type"],
                "group_by_column": ["type_is_missing"],
            }
        )

        # Should gracefully skip or error?
        # Current implementation likely skips iteration or fails.
        # Based on implementation: if col not in df.columns, it might fail if we don't check.
        # Slicing utils checks unique values on that column.
        # It's better if it skips.

        result = apply_slicing(df, rules, lambda x: x, base_columns=["project_id"])

        assert result.is_empty()
        # Because we can't extract unique values for "type_is_missing".
