# ruff: noqa: E501
from __future__ import annotations

import inspect
import json
import logging
import os
from typing import Any, Dict, Iterator, Optional

import dlt

logger = logging.getLogger(__name__)


def _extract_description_text(desc: dict | None) -> str:
    """Extract plain text from Jira rich-text description structure.

    Returns empty string when no text found.
    """
    if not desc:
        return ""
    parts: list[str] = []
    for node in desc.get("content") or []:
        for sub in node.get("content") or []:
            if isinstance(sub, dict) and sub.get("type") == "text":
                parts.append(sub.get("text", ""))
    return " ".join(p for p in parts if p).strip()


def extract_scalar(field_value: Any) -> Any:
    """Normalize custom field value to a scalar or None."""
    if field_value is None:
        return None
    if isinstance(field_value, (str, int, float, bool)):
        return field_value
    if isinstance(field_value, dict):
        return (
            field_value.get("value") or field_value.get("id") or field_value.get("name")
        )
    if isinstance(field_value, list):
        for v in field_value:
            if isinstance(v, (str, int, float, bool)):
                return v
    return None


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
        """Fetch issues and return flattened rows: scalars + joined lists + one `raw` JSON column.

        Text fields are coerced to empty string to reduce NULLs; numeric/date fields remain nullable.
        """
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
            "customfield_10036",
        ]

        # Call search_issues in a backward-compatible way: some client mocks don't accept `fields` kw
        try:
            sig = inspect.signature(client.search_issues)
            if "fields" in sig.parameters:
                payload = client.search_issues(
                    jql=jql, start_at=start_at, max_results=max_results, fields=fields
                )
            else:
                payload = client.search_issues(jql, start_at, max_results)
        except (ValueError, TypeError):
            # Fallback: try calling without fields
            payload = client.search_issues(jql, start_at, max_results)

        issues_batch = payload.get("issues", []) if isinstance(payload, dict) else []

        for item in issues_batch:
            # Ensure we never yield rows without an issue key (primary key must not be NULL)
            issue_key = item.get("key")
            if not issue_key:
                # skip malformed/anonymous items
                continue
            f = item.get("fields", {}) or {}
            status = f.get("status") or {}
            issuetype = f.get("issuetype") or {}
            priority = f.get("priority") or {}
            assignee = f.get("assignee") or {}
            reporter = f.get("reporter") or {}
            components = f.get("components") or []
            labels = f.get("labels") or []

            # keep NULLs for missing textual fields (prefer NULL over empty string)
            summary = f.get("summary")
            description_text = _extract_description_text(f.get("description")) or None
            status_name = status.get("name") or None
            status_id = status.get("id") or None
            issue_type_name = issuetype.get("name") or None
            issue_type_id = issuetype.get("id") or None
            priority_name = priority.get("name") or None
            assignee_name = assignee.get("displayName") or None
            reporter_name = reporter.get("displayName") or None

            story_points = extract_scalar(f.get("customfield_10036"))

            labels_str = ",".join(labels) if labels else None
            components_str = (
                ",".join([c.get("name") for c in components if c and c.get("name")])
                if components
                else None
            )

            yield {
                "issue_key": issue_key,
                "issue_id": item.get("id"),
                "summary": summary,
                "description_text": description_text,
                "status": status_name,
                "status_id": status_id,
                "issue_type": issue_type_name,
                "issue_type_id": issue_type_id,
                "priority": priority_name,
                "assignee": assignee_name,
                "reporter": reporter_name,
                "created": f.get("created"),
                "updated": f.get("updated"),
                "resolution_date": f.get("resolutiondate"),
                "story_points": story_points if story_points is not None else None,
                "labels_str": labels_str,
                "components_str": components_str,
                "raw_json": json.dumps(item, default=str),
            }

    return issues
