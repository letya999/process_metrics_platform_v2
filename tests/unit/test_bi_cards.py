"""
Contract tests for Metabase BI card JSON definitions.

These tests validate SQL query patterns and visualization settings in the
card JSON files without executing queries against a real database. They catch
regressions when card files are edited.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CARDS_DIR = (
    Path(__file__).resolve().parents[2]
    / "bi"
    / "packs"
    / "metabase"
    / "process_metrics_v1"
    / "cards"
)


def _load(name: str) -> dict:
    path = CARDS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# cfd_30_days
# ---------------------------------------------------------------------------


class TestCfdCard:
    @pytest.fixture(autouse=True)
    def card(self):
        self.c = _load("cfd_30_days")

    def test_series_dimension_is_column_name(self):
        dims = self.c["visualization_settings"]["graph.dimensions"]
        assert dims == [
            "date",
            "column_name",
        ], "CFD must break out series by column_name, not slice_value"

    def test_query_uses_context_json_column_name(self):
        assert (
            "context_json->>'column_name'" in self.c["query"]
        ), "CFD must derive series label from context_json, not slice_value"

    def test_query_filters_base_rows_only(self):
        assert (
            "slice_rule_id IS NULL" in self.c["query"]
        ), "CFD must filter slice_rule_id IS NULL to exclude issue-type sliced rows"

    def test_query_orders_by_column_position_asc(self):
        query = self.c["query"]
        assert "column_position" in query, "CFD must reference column_position"
        # ASC ordering puts To Do (lowest position) first in series
        pos = query.find("column_position")
        fragment = query[pos : pos + 60]
        assert (
            "ASC" in fragment or "ASC" in query.split("column_position")[-1]
        ), "column_position sort must be ASC so series order matches board column order"

    def test_query_groups_by_column_position(self):
        assert "GROUP BY" in self.c["query"]
        group_clause = self.c["query"].split("GROUP BY")[1].split("ORDER BY")[0]
        assert (
            "column_position" in group_clause
        ), "column_position must be in GROUP BY to support ORDER BY on it"

    def test_stacked_area_type(self):
        assert self.c["display"] == "area"
        assert self.c["visualization_settings"]["stackable.stack_type"] == "stacked"


# ---------------------------------------------------------------------------
# velocity_sp
# ---------------------------------------------------------------------------


class TestVelocityCard:
    @pytest.fixture(autouse=True)
    def card(self):
        self.c = _load("velocity_sp")

    def test_sprint_name_from_sprints_table(self):
        assert (
            "sprints.name" in self.c["query"]
        ), "Velocity must use sprints.name, not entity_id, for the X-axis label"

    def test_coalesce_uses_sprint_name_first(self):
        query = self.c["query"]
        coalesce_pos = query.lower().find("coalesce")
        assert coalesce_pos != -1
        coalesce_fragment = query[coalesce_pos : coalesce_pos + 60]
        assert (
            "sprints.name" in coalesce_fragment
        ), "COALESCE must prefer sprints.name as the first argument"

    def test_last_10_via_subquery_limit(self):
        assert "LIMIT 10" in self.c["query"], "Velocity must limit to last 10 sprints"

    def test_outer_order_is_ascending(self):
        # The outer ORDER BY (after the subquery) must be ASC for chronological display
        query = self.c["query"]
        last_order = query.rfind("ORDER BY")
        assert last_order != -1
        outer_clause = query[last_order:]
        assert (
            "ASC" in outer_clause
        ), "Outer ORDER BY must be ASC so sprints display oldest-to-newest left-to-right"

    def test_x_axis_dimension_is_sprint_name(self):
        dims = self.c["visualization_settings"]["graph.dimensions"]
        assert dims == ["sprint_name"]

    def test_metrics_include_planned_and_completed(self):
        metrics = self.c["visualization_settings"]["graph.metrics"]
        assert "planned_story_points" in metrics
        assert "completed_story_points" in metrics
