from unittest.mock import MagicMock, patch

import pytest

from pipelines.utils.smart_slicer import SmartSlicer


@pytest.fixture
def mock_engine():
    return MagicMock()


def test_find_path_direct(mock_engine):
    slicer = SmartSlicer(mock_engine)

    # Mock graph
    graph = {
        "clean_jira.issues": [("clean_jira.issue_types", "type_id", "id")],
        "clean_jira.issue_types": [("clean_jira.issues", "id", "type_id")],
    }

    with patch.object(slicer, "_get_schema_graph", return_value=graph):
        path = slicer._find_path("clean_jira.issues", "clean_jira.issue_types")
        assert path == [("clean_jira.issue_types", "type_id", "id")]


def test_find_path_multi_hop(mock_engine):
    slicer = SmartSlicer(mock_engine)

    # Mock graph: issues -> sprint_issues -> sprints
    graph = {
        "clean_jira.issues": [("clean_jira.sprint_issues", "id", "issue_id")],
        "clean_jira.sprint_issues": [
            ("clean_jira.issues", "issue_id", "id"),
            ("clean_jira.sprints", "sprint_id", "id"),
        ],
        "clean_jira.sprints": [("clean_jira.sprint_issues", "id", "sprint_id")],
    }

    with patch.object(slicer, "_get_schema_graph", return_value=graph):
        path = slicer._find_path("clean_jira.issues", "clean_jira.sprints")
        assert path == [
            ("clean_jira.sprint_issues", "id", "issue_id"),
            ("clean_jira.sprints", "sprint_id", "id"),
        ]


def test_get_slice_mapping_validation(mock_engine):
    slicer = SmartSlicer(mock_engine)

    # Mock inspector
    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = ["issues"]
    mock_inspector.get_columns.return_value = [{"name": "id"}, {"name": "key"}]

    with patch("pipelines.utils.smart_slicer.inspect", return_value=mock_inspector):
        # Case: Table not found
        res = slicer.get_slice_mapping(
            "clean_jira.issues", "clean_jira.unknown_table.name"
        )
        assert res is None

        # Case: Column not found
        res = slicer.get_slice_mapping(
            "clean_jira.issues", "clean_jira.issues.unknown_col"
        )
        assert res is None


def test_find_path_no_route(mock_engine):
    slicer = SmartSlicer(mock_engine)
    graph = {"clean_jira.issues": [], "clean_jira.sprints": []}
    with patch.object(slicer, "_get_schema_graph", return_value=graph):
        path = slicer._find_path("clean_jira.issues", "clean_jira.sprints")
        assert path is None
