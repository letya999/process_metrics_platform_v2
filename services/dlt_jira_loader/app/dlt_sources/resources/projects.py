"""Projects resource for DLT Jira source."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, Optional

import dlt


def make_projects_resource(client, project_key: Optional[str] = None) -> dlt.Resource:
    WRITE_DISPOSITION = (
        "append"
        if os.getenv("DLT_FORCE_APPEND", "0") in ("1", "true", "True")
        else "merge"
    )

    @dlt.resource(
        write_disposition=WRITE_DISPOSITION,
        table_name="projects",
        primary_key=["project_key"],
    )
    def projects() -> Iterator[Dict[str, Any]]:
        if not project_key:
            return iter(())
        try:
            proj = client.get_project(project_key=project_key)
        except Exception:
            return iter(())
        yield {
            "project_key": proj.get("key"),
            "project_id": proj.get("id"),
            "project_name": proj.get("name"),
            "project_type": proj.get("projectTypeKey"),
            "lead": (proj.get("lead") or {}).get("displayName"),
            "created": proj.get("created"),
            "raw_json": json.dumps(proj, default=str),
        }

    return projects
