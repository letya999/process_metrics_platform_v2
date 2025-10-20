from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

import dlt


def make_releases_resource(client) -> dlt.Resource:
    @dlt.resource(write_disposition="merge", primary_key=["release_id"])
    def releases(project_key: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        # Jira versions endpoint is project-scoped. Example:
        # /rest/api/3/project/{project_key}/versions
        # Client should expose an endpoint to fetch versions for project_key
        versions = client.get_project_versions(project_key=project_key)
        for v in versions:
            yield {
                "release_id": v.get("id"),
                "name": v.get("name"),
                "description": v.get("description"),
                "released": v.get("released"),
                "release_date": v.get("releaseDate"),
                "raw": v,
            }

    return releases
