"""
Resolver for commitment points (start/end columns) in flow metrics.
Supports both rule-based resolution from the database and heuristic fallback.
"""

from typing import Dict, Optional

import polars as pl
from sqlalchemy import Engine

from ..utils.polars_db import read_table


def resolve_commitment_columns(
    engine: Engine,
    project_id: str,
    board_id: str,
    calc_code: str,
) -> Optional[Dict]:
    """
    Query commitment_rules for project/board/calc_code.
    Return column IDs and names.
    Priority: project+board > project_only > global.
    """
    query = """
        SELECT
            id as commitment_rule_id,
            start_column_id,
            end_column_id,
            start_column_name_snapshot as start_column_name,
            end_column_name_snapshot as end_column_name
        FROM metrics.commitment_rules
        WHERE (target_calculation_id = (SELECT id FROM metrics.calculations WHERE calc_code = :calc_code))
          AND (project_id = :project_id OR project_id IS NULL)
          AND (board_id = :board_id OR board_id IS NULL)
        ORDER BY
            (project_id IS NOT NULL)::int DESC,
            (board_id IS NOT NULL)::int DESC
        LIMIT 1
    """
    df = read_table(
        engine,
        query,
        params={"calc_code": calc_code, "project_id": project_id, "board_id": board_id},
    )

    if df.is_empty():
        return None

    return df.to_dicts()[0]


def identify_commitment_points_from_rule(
    rule: Dict,
    board_columns_df: pl.DataFrame,
) -> Dict:
    """
    Given a resolved commitment rule, return status_ids and positions.
    """
    start_col_id = rule["start_column_id"]
    end_col_id = rule["end_column_id"]

    # Get all status_ids for the start and end columns
    # In Jira boards, one column can map to multiple statuses
    start_columns = board_columns_df.filter(pl.col("id") == start_col_id)
    end_columns = board_columns_df.filter(pl.col("id") == end_col_id)

    if start_columns.is_empty() or end_columns.is_empty():
        return identify_commitment_points_heuristic(board_columns_df)

    start_position = start_columns["position"].min()
    end_position = end_columns["position"].min()

    start_status_ids = start_columns["status_id"].unique().drop_nulls().to_list()
    end_status_ids = end_columns["status_id"].unique().drop_nulls().to_list()

    # All statuses in columns from start (inclusive) to end (exclusive)
    middle_columns = board_columns_df.filter(
        (pl.col("position") >= start_position) & (pl.col("position") < end_position)
    )
    middle_status_ids = middle_columns["status_id"].unique().drop_nulls().to_list()

    return {
        "start_status_ids": start_status_ids,
        "end_status_ids": end_status_ids,
        "middle_status_ids": middle_status_ids,
        "start_position": start_position,
        "end_position": end_position,
        "commitment_rule_id": rule["commitment_rule_id"],
    }


def identify_commitment_points_heuristic(
    board_columns_df: pl.DataFrame,
) -> Dict:
    """
    Fallback: use string matching ('in progress', 'done').
    """
    if board_columns_df.is_empty():
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": None,
            "end_position": None,
            "commitment_rule_id": None,
        }

    # Find "In Progress" columns
    start_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("in progress")
        | pl.col("name").str.to_lowercase().str.contains("в работе")
    )

    # Find "Done" columns
    end_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("done")
        | pl.col("name").str.to_lowercase().str.contains("готово")
    )

    if start_columns.is_empty() or end_columns.is_empty():
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": None,
            "end_position": None,
            "commitment_rule_id": None,
        }

    start_position = start_columns["position"].min()
    end_position = end_columns["position"].min()

    if start_position >= end_position:
        return {
            "start_status_ids": [],
            "end_status_ids": [],
            "middle_status_ids": [],
            "start_position": None,
            "end_position": None,
            "commitment_rule_id": None,
        }

    start_status_ids = start_columns["status_id"].unique().drop_nulls().to_list()
    end_status_ids = end_columns["status_id"].unique().drop_nulls().to_list()

    middle_columns = board_columns_df.filter(
        (pl.col("position") >= start_position) & (pl.col("position") < end_position)
    )
    middle_status_ids = middle_columns["status_id"].unique().drop_nulls().to_list()

    return {
        "start_status_ids": start_status_ids,
        "end_status_ids": end_status_ids,
        "middle_status_ids": middle_status_ids,
        "start_position": start_position,
        "end_position": end_position,
        "commitment_rule_id": None,
    }
