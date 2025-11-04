# ruff: noqa: E501
from __future__ import annotations

import os
from typing import Any, Dict, Iterator, Optional

import dlt


def make_boards_resource(client, project_key: Optional[str] = None) -> dlt.Resource:
    WRITE_DISPOSITION = (
        "append"
        if os.getenv("DLT_FORCE_APPEND", "0") in ("1", "true", "True")
        else "merge"
    )

    @dlt.resource(
        write_disposition=WRITE_DISPOSITION,
        table_name="boards",
        primary_key=["board_id"],
    )
    def boards() -> Iterator[Dict[str, Any]]:
        # Jira boards can be searched by project key via the agile API.
        # Example path: /rest/agile/1.0/board?projectKeyOrId={key}
        board_list = client.find_boards(project_key=project_key)

        # normalize possible responses: list of boards or dict with 'values'
        if isinstance(board_list, dict):
            candidates = board_list.get("values") or board_list.get("boards") or []
        elif isinstance(board_list, list):
            candidates = board_list
        else:
            # fallback: try to iterate
            try:
                candidates = list(board_list)
            except Exception:
                candidates = []

        for b in candidates:
            # each item should be a dict; guard when it's not
            if not isinstance(b, dict):
                continue
            yield {
                "board_id": b.get("id"),
                "name": b.get("name"),
                "type": b.get("type"),
                "location": b.get("location"),
                "raw": b,
            }

    return boards
