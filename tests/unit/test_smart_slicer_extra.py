"""Additional unit tests for SmartSlicer branching logic."""

from unittest.mock import MagicMock, patch

import polars as pl

from pipelines.utils.smart_slicer import SmartSlicer


def test_get_schema_graph_builds_bidirectional_edges():
    engine = MagicMock()
    slicer = SmartSlicer(engine)

    inspector = MagicMock()
    inspector.get_table_names.return_value = ["issues", "issue_types"]
    inspector.get_foreign_keys.side_effect = [
        [
            {
                "referred_schema": "clean_jira",
                "referred_table": "issue_types",
                "constrained_columns": ["issue_type_id"],
                "referred_columns": ["id"],
            }
        ],
        [],
    ]

    with patch("pipelines.utils.smart_slicer.inspect", return_value=inspector):
        graph = slicer._get_schema_graph("clean_jira")

    assert ("clean_jira.issue_types", "issue_type_id", "id") in graph[
        "clean_jira.issues"
    ]
    assert ("clean_jira.issues", "id", "issue_type_id") in graph[
        "clean_jira.issue_types"
    ]


def test_get_slice_mapping_same_table_executes_direct_query():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    slicer = SmartSlicer(engine)

    inspector = MagicMock()
    inspector.get_table_names.return_value = ["issues"]
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "priority"}]

    expected_df = pl.DataFrame({"source_id": ["1"], "slice_value": ["High"]})
    with (
        patch("pipelines.utils.smart_slicer.inspect", return_value=inspector),
        patch(
            "pipelines.utils.smart_slicer.pl.read_database", return_value=expected_df
        ) as read_db,
    ):
        result = slicer.get_slice_mapping(
            "clean_jira.issues", "clean_jira.issues.priority"
        )

    assert result is not None
    assert result.to_dicts() == [{"source_id": "1", "slice_value": "High"}]
    query = read_db.call_args.args[0]
    assert "FROM clean_jira.issues" in query
    assert "priority AS slice_value" in query


def test_get_slice_mapping_returns_none_when_path_not_found():
    engine = MagicMock()
    slicer = SmartSlicer(engine)

    inspector = MagicMock()
    inspector.get_table_names.return_value = ["issues", "issue_types"]
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "name"}]

    with (
        patch("pipelines.utils.smart_slicer.inspect", return_value=inspector),
        patch.object(slicer, "_find_path", return_value=None),
    ):
        result = slicer.get_slice_mapping(
            "clean_jira.issues", "clean_jira.issue_types.name"
        )

    assert result is None


def test_get_slice_mapping_returns_none_for_invalid_target_format():
    slicer = SmartSlicer(MagicMock())
    result = slicer.get_slice_mapping("clean_jira.issues", "bad-format")
    assert result is None


def test_find_target_for_column_prefers_source_then_neighbor():
    slicer = SmartSlicer(MagicMock())
    graph = {"clean_jira.issues": [("clean_jira.issue_types", "issue_type_id", "id")]}

    inspector = MagicMock()

    def _columns(table_name, schema=None):
        if table_name == "issues":
            return [{"name": "id"}, {"name": "priority"}]
        if table_name == "issue_types":
            return [{"name": "id"}, {"name": "name"}]
        return []

    inspector.get_columns.side_effect = _columns

    with (
        patch.object(slicer, "_get_schema_graph", return_value=graph),
        patch("pipelines.utils.smart_slicer.inspect", return_value=inspector),
    ):
        in_source = slicer.find_target_for_column("clean_jira.issues", "priority")
        in_neighbor = slicer.find_target_for_column("clean_jira.issues", "name")

    assert in_source == "clean_jira.issues.priority"
    assert in_neighbor == "clean_jira.issue_types.name"


def test_find_target_for_column_skips_broken_neighbor_inspection():
    slicer = SmartSlicer(MagicMock())
    graph = {"clean_jira.issues": [("clean_jira.issue_types", "issue_type_id", "id")]}

    inspector = MagicMock()
    inspector.get_columns.side_effect = [
        [{"name": "id"}],  # source cols
        RuntimeError("inspection failed"),  # neighbor cols
    ]

    with (
        patch.object(slicer, "_get_schema_graph", return_value=graph),
        patch("pipelines.utils.smart_slicer.inspect", return_value=inspector),
    ):
        result = slicer.find_target_for_column("clean_jira.issues", "name")

    assert result is None
