# ruff: noqa: E501
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, Optional

import dlt


def _get_write_disposition() -> str:
    return (
        "append"
        if os.getenv("DLT_FORCE_APPEND", "0") in ("1", "true", "True")
        else "merge"
    )


def _normalize_sprint_goal(value: Any) -> Optional[str]:
    if value is None or isinstance(value, dict):
        return None
    return value


def _extract_boards_list(resp: Any) -> list:
    if isinstance(resp, dict):
        return resp.get("values") or []
    if isinstance(resp, list):
        return resp
    return list(resp) if resp else []


def _iterate_sprint_batches(client, board_id: int) -> Iterator[Dict[str, Any]]:
    start_at = 0
    max_results = 100
    while True:
        resp = client.get_sprints(
            board_id=board_id, start_at=start_at, max_results=max_results
        )
        batch = resp.get("values", []) if isinstance(resp, dict) else []
        if not batch:
            break
        for s in batch:
            yield s
        start_at += len(batch)
        if len(batch) < max_results:
            break


def _make_project_sprints_resource(
    client, project_key: str, write_disposition: str
) -> dlt.Resource:
    @dlt.resource(
        write_disposition=write_disposition,
        table_name="sprints",
        primary_key=["project_key", "sprint_id"],
    )
    def sprints() -> Iterator[Dict[str, Any]]:
        processed = set()
        try:
            boards_resp = client.find_boards(project_key=project_key)
            boards = _extract_boards_list(boards_resp)
        except Exception:
            boards = []

        for board in boards:
            board_id = board.get("id")
            for s in _iterate_sprint_batches(client, board_id):
                key = (project_key, s.get("id"))
                if key in processed:
                    continue
                processed.add(key)
                yield {
                    "project_key": project_key,
                    "board_id": board_id,
                    "sprint_id": s.get("id"),
                    "sprint_name": s.get("name"),
                    "sprint_state": s.get("state"),
                    "sprint_start_date": s.get("startDate"),
                    "sprint_end_date": s.get("endDate"),
                    "sprint_complete_date": s.get("completeDate"),
                    "sprint_goal": _normalize_sprint_goal(s.get("goal")),
                    "raw_json": json.dumps(s, default=str),
                }

    return sprints


def _make_board_sprints_resource(client, write_disposition: str) -> dlt.Resource:
    @dlt.resource(
        write_disposition=write_disposition,
        table_name="sprints",
        primary_key=["sprint_id"],
    )
    def sprints(board_id: int) -> Iterator[Dict[str, Any]]:
        for s in _iterate_sprint_batches(client, board_id):
            yield {
                "sprint_id": s.get("id"),
                "sprint_name": s.get("name"),
                "sprint_state": s.get("state"),
                "sprint_start_date": s.get("startDate"),
                "sprint_end_date": s.get("endDate"),
                "sprint_complete_date": s.get("completeDate"),
                "sprint_goal": _normalize_sprint_goal(s.get("goal")),
                "raw_json": json.dumps(s, default=str),
            }

    return sprints


def make_sprints_resource(client, project_key: Optional[str] = None) -> dlt.Resource:
    write_disposition = _get_write_disposition()
    if project_key:
        return _make_project_sprints_resource(client, project_key, write_disposition)
    return _make_board_sprints_resource(client, write_disposition)
