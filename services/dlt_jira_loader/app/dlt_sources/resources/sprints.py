# ruff: noqa: E501
from __future__ import annotations

import os
from typing import Any, Dict, Iterator

import dlt


def make_sprints_resource(client) -> dlt.Resource:
    WRITE_DISPOSITION = (
        "append"
        if os.getenv("DLT_FORCE_APPEND", "0") in ("1", "true", "True")
        else "merge"
    )

    @dlt.resource(
        write_disposition=WRITE_DISPOSITION,
        table_name="sprints",
        primary_key=["sprint_id"],
    )
    def sprints(board_id: int) -> Iterator[Dict[str, Any]]:
        start_at = 0
        max_results = 100
        while True:
            payload = client.get_sprints(
                board_id=board_id, start_at=start_at, max_results=max_results
            )
            sprint_batch = payload.get("values", [])
            if not sprint_batch:
                break
            for s in sprint_batch:
                yield {
                    "sprint_id": s.get("id"),
                    "name": s.get("name"),
                    "state": s.get("state"),
                    "raw": s,
                }
            start_at += len(sprint_batch)
            if len(sprint_batch) < max_results:
                break

    return sprints
