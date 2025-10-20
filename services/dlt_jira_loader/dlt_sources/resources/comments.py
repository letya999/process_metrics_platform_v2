from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

import dlt


def make_comments_resource(client) -> dlt.Resource:
    @dlt.resource(write_disposition="merge", primary_key=["issue_key", "comment_id"])
    def comments(issue_key: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        # allow being called without an issue_key during DLT pipeline introspection
        # (DLT may call the resource with no args); return empty iterator in that case.
        if issue_key is None:
            return iter(())
        start_at = 0
        max_results = 50
        while True:
            payload = client.get_comments(
                issue_key=issue_key, start_at=start_at, max_results=max_results
            )
            comments_batch = payload.get("comments", [])
            if not comments_batch:
                break
            for c in comments_batch:
                yield {
                    "issue_key": issue_key,
                    "comment_id": c.get("id"),
                    "author": c.get("author", {}),
                    "body": c.get("body"),
                    "created": c.get("created"),
                    "raw": c,
                }
            start_at += len(comments_batch)
            if len(comments_batch) < max_results:
                break

    return comments
