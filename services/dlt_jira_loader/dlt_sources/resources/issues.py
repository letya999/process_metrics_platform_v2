from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

import dlt


def make_issues_resource(project_key: str, client) -> dlt.Resource:
    @dlt.resource(write_disposition="merge", primary_key=["issue_key"])
    def issues(created_after: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        start_at = 0
        max_results = 50
        jql = f'project = "{project_key}" ORDER BY created ASC'
        if created_after:
            jql = f'{jql} AND created >= "{created_after}"'
        while True:
            payload = client.search_issues(
                jql=jql, start_at=start_at, max_results=max_results
            )
            issues_batch = payload.get("issues", [])
            if not issues_batch:
                break
            for item in issues_batch:
                yield {
                    "issue_key": item.get("key"),
                    "issue_id": item.get("id"),
                    "fields": item.get("fields", {}),
                    "raw": item,
                }
            start_at += len(issues_batch)
            if len(issues_batch) < max_results:
                break

    return issues
