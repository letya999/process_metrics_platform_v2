"""
Commitment Resolver: Dynamic lookup of start and end columns for flow metrics.
Replaces hardcoded string heuristics with database-driven rules.
"""

import logging
from typing import Any, Dict, List, Optional

import polars as pl
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pipelines.utils.polars_db import read_table

logger = logging.getLogger(__name__)


def load_commitment_rules_for_calc(
    engine: Engine, calc_code: str
) -> List[Dict[str, Any]]:
    """Load commitment rules for a calculation in one query."""
    try:
        rules_df = read_table(
            engine,
            """
            SELECT
                cr.id AS commitment_rule_id,
                cr.project_id,
                cr.board_id,
                cr.start_column_id,
                cr.end_column_id,
                cr.start_column_name_snapshot AS start_column_name,
                cr.end_column_name_snapshot AS end_column_name
            FROM metrics.commitment_rules cr
            JOIN metrics.calculations c ON c.id = cr.target_calculation_id
            WHERE c.calc_code = :calc_code
            """,
            params={"calc_code": calc_code},
        )
        return rules_df.to_dicts() if not rules_df.is_empty() else []
    except Exception as exc:
        logger.warning(
            "Failed to load commitment rules for calc_code=%s; using empty rules fallback. Error: %s",
            calc_code,
            exc,
        )
        return []


def resolve_rule_from_cache(
    rules: List[Dict[str, Any]], project_id: str, board_id: str
) -> Optional[Dict[str, Any]]:
    """Pick best rule with priority: project+board > project > board > global."""
    candidates = []
    for rule in rules:
        rule_project = str(rule["project_id"]) if rule.get("project_id") else None
        rule_board = str(rule["board_id"]) if rule.get("board_id") else None

        if rule_project not in (None, str(project_id)):
            continue
        if rule_board not in (None, str(board_id)):
            continue

        score = (int(rule_project is not None), int(rule_board is not None))
        candidates.append((score, rule))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def get_done_column_ids(board_columns_df: pl.DataFrame) -> List[str]:
    """
    Unified "done status" resolution.
    1. Try rightmost column by position (GROUP BY board_id, take max position).
    2. Fallback: name contains "done|готово|closed|resolved|completed".
    3. Return list of status_ids.
    """
    if board_columns_df.is_empty():
        return []

    # Strategy 1: Rightmost column
    try:
        max_pos_df = board_columns_df.group_by("board_id").agg(
            pl.col("position").max().alias("max_pos")
        )
        rightmost_cols = board_columns_df.join(max_pos_df, on="board_id").filter(
            pl.col("position") == pl.col("max_pos")
        )
        if not rightmost_cols.is_empty():
            status_ids = (
                rightmost_cols.select("status_id").drop_nulls().to_series().to_list()
            )
            if status_ids:
                return [str(sid) for sid in status_ids]
    except Exception as exc:
        logger.debug(
            "Failed rightmost done-column detection; using heuristic fallback: %s", exc
        )

    # Strategy 2: Heuristic
    done_cols = board_columns_df.filter(
        pl.col("name")
        .str.to_lowercase()
        .str.contains("done|готово|closed|resolved|completed")  # 'готово' means 'done'
    )
    if not done_cols.is_empty():
        status_ids = done_cols.select("status_id").drop_nulls().to_series().to_list()
        return [str(sid) for sid in status_ids]

    return []


def resolve_commitment_columns(
    engine: Engine,
    project_id: str,
    board_id: str,
    calc_code: str,
) -> Optional[Dict[str, Any]]:
    """
    Query commitment_rules for project/board/calc_code.
    Return {'start_column_id': uuid, 'end_column_id': uuid,
            'start_column_name': str, 'end_column_name': str,
            'commitment_rule_id': uuid}
    """
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT cr.id, cr.start_column_id, cr.end_column_id,
                       bc_start.name as start_name, bc_end.name as end_name
                FROM metrics.commitment_rules cr
                JOIN clean_jira.board_columns bc_start ON cr.start_column_id = bc_start.id
                JOIN clean_jira.board_columns bc_end ON cr.end_column_id = bc_end.id
                JOIN metrics.calculations calc ON cr.target_calculation_id = calc.id
                WHERE calc.calc_code = :calc_code
                  AND (cr.project_id = :project_id OR cr.project_id IS NULL)
                  AND (cr.board_id = :board_id OR cr.board_id IS NULL)
                ORDER BY cr.project_id NULLS LAST, cr.board_id NULLS LAST
                LIMIT 1
            """),
            {"calc_code": calc_code, "project_id": project_id, "board_id": board_id},
        ).fetchone()

    if not result:
        return None

    return {
        "commitment_rule_id": str(result[0]),
        "start_column_id": str(result[1]),
        "end_column_id": str(result[2]),
        "start_column_name": result[3],
        "end_column_name": result[4],
    }


def identify_commitment_points_from_rule(
    rule: Dict[str, Any],
    board_columns_df: pl.DataFrame,
) -> Dict[str, Any]:
    """
    Given a resolved commitment rule and board_columns_df, return status_ids and positions.
    """
    start_col_id = rule["start_column_id"]
    end_col_id = rule["end_column_id"]

    start_statuses = (
        board_columns_df.filter(pl.col("id").cast(str) == start_col_id)
        .select("status_id")
        .to_series()
        .to_list()
    )
    end_statuses = (
        board_columns_df.filter(pl.col("id").cast(str) == end_col_id)
        .select("status_id")
        .to_series()
        .to_list()
    )

    start_pos_result = board_columns_df.filter(
        pl.col("id").cast(str) == start_col_id
    ).select("position")
    start_pos = start_pos_result.row(0)[0] if not start_pos_result.is_empty() else 0

    end_pos_result = board_columns_df.filter(
        pl.col("id").cast(str) == end_col_id
    ).select("position")
    end_pos = end_pos_result.row(0)[0] if not end_pos_result.is_empty() else 999

    middle_status_ids = (
        board_columns_df.filter(
            (pl.col("position") >= start_pos) & (pl.col("position") < end_pos)
        )
        .select("status_id")
        .drop_nulls()
        .to_series()
        .to_list()
    )

    return {
        "start_status_ids": start_statuses,
        "end_status_ids": end_statuses,
        "middle_status_ids": middle_status_ids,
        "start_position": start_pos,
        "end_position": end_pos,
        "commitment_rule_id": rule["commitment_rule_id"],
    }


def identify_commitment_points_heuristic(
    board_columns_df: pl.DataFrame,
) -> Dict[str, Any]:
    """
    Fallback heuristic when no rules exist.
    Matches standard 'In Progress' and 'Done' column patterns.
    """
    if board_columns_df.is_empty():
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": 0,
            "end_position": 999,
            "commitment_rule_id": None,
        }

    # Find "In Progress" type column
    start_cols = board_columns_df.filter(
        pl.col("name")
        .str.to_lowercase()
        .str.contains(
            "in progress|в работе|progress|active"
        )  # 'в работе' means 'in progress'
    )
    if start_cols.is_empty():
        start_pos = 0
        start_statuses = []
    else:
        # Take the first matched column's position
        start_pos = start_cols.select("position").min().item()
        start_statuses = (
            board_columns_df.filter(pl.col("position") == start_pos)
            .select("status_id")
            .drop_nulls()
            .to_series()
            .to_list()
        )

    # Find "Done" type column
    end_cols = board_columns_df.filter(
        pl.col("name")
        .str.to_lowercase()
        .str.contains("done|готово|closed|resolved|completed")  # 'готово' means 'done'
    )
    if end_cols.is_empty():
        end_pos = 999
        end_statuses = []
    else:
        # Take the first matched column's position
        end_pos = end_cols.select("position").min().item()
        end_statuses = (
            board_columns_df.filter(pl.col("position") == end_pos)
            .select("status_id")
            .drop_nulls()
            .to_series()
            .to_list()
        )

    middle_status_ids = []
    if start_statuses and end_statuses and start_pos < end_pos:
        middle_status_ids = (
            board_columns_df.filter(
                (pl.col("position") >= start_pos) & (pl.col("position") < end_pos)
            )
            .select("status_id")
            .drop_nulls()
            .to_series()
            .to_list()
        )

    return {
        "start_status_ids": start_statuses,
        "end_status_ids": end_statuses,
        "middle_status_ids": middle_status_ids,
        "start_position": start_pos,
        "end_position": end_pos,
        "commitment_rule_id": None,
    }
