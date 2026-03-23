from unittest.mock import MagicMock, patch

import polars as pl

from pipelines.calculations.commitment_resolver import (
    get_done_column_ids,
    identify_commitment_points_from_rule,
    identify_commitment_points_heuristic,
    load_commitment_rules_for_calc,
    resolve_commitment_columns,
    resolve_rule_from_cache,
)


def test_load_commitment_rules_exception():
    mock_engine = MagicMock()
    with patch(
        "pipelines.calculations.commitment_resolver.read_table",
        side_effect=Exception("DB Error"),
    ):
        rules = load_commitment_rules_for_calc(mock_engine, "calc_1")
        assert rules == []


def test_resolve_rule_from_cache_priority():
    rules = [
        {"project_id": "P1", "board_id": None, "id": "rule_proj"},
        {"project_id": "P1", "board_id": "B1", "id": "rule_both"},
        {"project_id": None, "board_id": "B1", "id": "rule_board"},
        {"project_id": None, "board_id": None, "id": "rule_global"},
    ]
    # Should pick rule_both
    res = resolve_rule_from_cache(rules, "P1", "B1")
    assert res["id"] == "rule_both"

    # Should pick rule_proj
    res = resolve_rule_from_cache(rules, "P1", "B2")
    assert res["id"] == "rule_proj"


def test_get_done_column_ids_strategies():
    # Empty
    assert get_done_column_ids(pl.DataFrame()) == []

    # Heuristic fallback (Russian)
    df = pl.DataFrame(
        {
            "board_id": ["B1"],
            "name": ["Готово"],
            "position": [5],
            "status_id": ["S_DONE"],
        }
    )
    assert get_done_column_ids(df) == ["S_DONE"]

    # Exception in strategy 1 (missing columns for join)
    df_broken = pl.DataFrame(
        {"name": ["Done"], "status_id": ["S1"]}
    )  # no position/board_id
    # Should use heuristic
    assert get_done_column_ids(df_broken) == ["S1"]


def test_identify_commitment_points_from_rule_missing_cols():
    rule = {"start_column_id": "C1", "end_column_id": "C2", "commitment_rule_id": "R1"}
    # DataFrame doesn't have these IDs
    df = pl.DataFrame({"id": ["CX"], "status_id": ["SX"], "position": [10]})
    res = identify_commitment_points_from_rule(rule, df)
    assert res["start_position"] == 0
    assert res["end_position"] == 999
    assert res["start_status_ids"] == []


def test_identify_commitment_points_heuristic_missing_phases():
    # Only Start, no End
    df = pl.DataFrame({"name": ["In Progress"], "position": [1], "status_id": ["S1"]})
    res = identify_commitment_points_heuristic(df)
    assert res["start_status_ids"] == ["S1"]
    assert res["end_status_ids"] == []

    # Only End, no Start
    df = pl.DataFrame({"name": ["Done"], "position": [5], "status_id": ["S2"]})
    res = identify_commitment_points_heuristic(df)
    assert res["start_status_ids"] == []
    assert res["end_status_ids"] == ["S2"]


def test_resolve_commitment_columns_none(mock_db_engine):
    # This requires a mock engine that returns None on fetchone
    mock_conn = mock_db_engine.connect.return_value.__enter__.return_value
    mock_conn.execute.return_value.fetchone.return_value = None

    res = resolve_commitment_columns(mock_db_engine, "P1", "B1", "C1")
    assert res is None
