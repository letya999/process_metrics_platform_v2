# ruff: noqa: E501
"""Releases resource (placeholder) -- file created to satisfy formatting edits."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, Optional

import dlt


def make_releases_resource(client) -> dlt.Resource:
    WRITE_DISPOSITION = (
        "append"
        if os.getenv("DLT_FORCE_APPEND", "0") in ("1", "true", "True")
        else "merge"
    )

    @dlt.resource(
        write_disposition=WRITE_DISPOSITION,
        table_name="releases",
        primary_key=["release_id"],
    )
    def releases(project_key: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        # If project_key is not provided, return empty iterator so caller can bind safely
        if not project_key:
            return iter(())

        # Jira versions endpoint is project-scoped. Example:
        # /rest/api/3/project/{project_key}/versions
        # Client should expose an endpoint to fetch versions for project_key
        versions = client.get_project_versions(project_key=project_key)
        # normalize response
        if not versions:
            return iter(())
        for v in versions:
            yield {
                "release_id": v.get("id"),
                "release_name": v.get("name"),
                "release_description": v.get("description"),
                "release_released": v.get("released", False),
                "release_release_date": v.get("releaseDate"),
                "raw_json": json.dumps(v, default=str),
            }

    return releases
