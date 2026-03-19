"""
Commitment Resolver: Dynamic lookup of start and end columns for flow metrics.
Replaces hardcoded string heuristics with database-driven rules.
"""

from typing import Any, Dict, Optional

import polars as pl
from sqlalchemy import text
from sqlalchemy.engine import Engine


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
            text(
                """
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
            """
            ),
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
        .str.contains("in progress|в работе|progress|active")
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
        .str.contains("done|готово|closed|resolved|completed")
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
