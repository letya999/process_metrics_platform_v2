# ruff: noqa: E501
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Iterator, Optional

import dlt

logger = logging.getLogger(__name__)


def make_issues_resource(project_key: str, client) -> dlt.Resource:
    WRITE_DISPOSITION = (
        "append"
        if os.getenv("DLT_FORCE_APPEND", "0") in ("1", "true", "True")
        else "merge"
    )

    @dlt.resource(
        write_disposition=WRITE_DISPOSITION,
        table_name="issues",
        primary_key=["issue_key"],
    )
    def issues(created_after: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        # Quick debug prints to verify the resource function is called and where execution stops
        print(
            f"\n!!! issues() CALLED for project={project_key} created_after={created_after} !!!",
            file=sys.stderr,
        )

        start_at = 0
        max_results = 100
        jql = f"project = {project_key} ORDER BY created ASC"
        if created_after:
            jql = f'{jql} AND created >= "{created_after}"'
        fields = [
            "summary",
            "description",
            "issuetype",
            "status",
            "priority",
            "assignee",
            "reporter",
            "created",
            "updated",
            "resolutiondate",
            "labels",
            "components",
        ]

        print(
            f"!!! About to call client.search_issues (start_at={start_at} max_results={max_results}) !!!",
            file=sys.stderr,
        )

        # Single call for debugging to see where execution stops; pagination removed for clarity
        payload = client.search_issues(
            jql=jql, start_at=start_at, max_results=max_results, fields=fields
        )

        try:
            keys = list(payload.keys()) if isinstance(payload, dict) else []
        except Exception:
            keys = []

        print(f"!!! Got response, keys: {keys} !!!", file=sys.stderr)
        print(
            f"!!! Total: {payload.get('total') if isinstance(payload, dict) else 'N/A'} !!!",
            file=sys.stderr,
        )

        issues_batch = payload.get("issues", []) if isinstance(payload, dict) else []

        print(f"!!! Got {len(issues_batch)} issues !!!", file=sys.stderr)

        for item in issues_batch:
            print(f"!!! Yielding issue {item.get('key')} !!!", file=sys.stderr)
            yield {
                "issue_key": item.get("key"),
                "issue_id": item.get("id"),
                "fields": item.get("fields", {}),
                "raw": item,
            }

    return issues
