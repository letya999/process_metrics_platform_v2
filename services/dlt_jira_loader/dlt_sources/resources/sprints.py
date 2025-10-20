from __future__ import annotations

from typing import Any, Dict, Iterator

import dlt


def make_sprints_resource(client) -> dlt.Resource:
    @dlt.resource(write_disposition="merge", primary_key=["sprint_id"])
    def sprints(board_id: int) -> Iterator[Dict[str, Any]]:
        start_at = 0
        max_results = 50
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
