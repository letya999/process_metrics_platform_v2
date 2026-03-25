"""Clean layer maintenance assets for Jira pipeline.

Covers: jira_ghost_cleanup (removes deleted issues from raw layer).
"""

import os
from typing import Any

import requests
from dagster import AssetExecutionContext, asset
from requests.auth import HTTPBasicAuth
from sqlalchemy import bindparam, text

from pipelines.resources.database import DatabaseResource


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data"],
    description="Remove issues from raw layer that no longer exist in Jira API",
)
def jira_ghost_cleanup(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Remove ghost issues from raw_jira.issues.

    Fetches all issue IDs from Jira API and deletes those from raw layer
    that are not in the fetched list.
    """
    jira_url = os.getenv("JIRA_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_api_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_url, jira_email, jira_api_token]):
        context.log.warning(
            "Jira credentials not fully configured (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN). "
            "Skipping ghost cleanup."
        )
        return {"status": "skipped", "reason": "missing_credentials"}

    context.log.info("Fetching all issue IDs from Jira API...")

    # We only need 'id' field to minimize payload
    all_issue_ids = set()
    start_at = 0
    max_results = 100

    try:
        auth = HTTPBasicAuth(jira_email, jira_api_token)
        while True:
            response = requests.get(
                f"{jira_url}/rest/api/3/search",
                params={
                    "jql": "order by id",
                    "fields": "id",
                    "startAt": start_at,
                    "maxResults": max_results,
                },
                auth=auth,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                all_issue_ids.add(issue["id"])

            start_at += len(issues)
            if start_at >= data.get("total", 0):
                break

        context.log.info(f"Fetched {len(all_issue_ids)} issue IDs from Jira API")

        engine = database.get_engine()
        with engine.connect() as conn:
            # M-2: Pagination safety check - compare with DB count
            total_raw_issues = conn.execute(
                text("SELECT COUNT(*) FROM raw_jira.issues")
            ).scalar()
            if (
                total_raw_issues
                and total_raw_issues > 0
                and len(all_issue_ids) < total_raw_issues * 0.9
            ):
                context.log.warning(
                    f"Jira API returned only {len(all_issue_ids)} IDs but DB has {total_raw_issues} issues. "
                    "Aborting ghost cleanup to prevent false deletions."
                )
                return {
                    "status": "aborted_incomplete_api_response",
                    "jira_ids": len(all_issue_ids),
                    "db_count": total_raw_issues,
                }

            if not all_issue_ids:
                context.log.warning(
                    "No issues fetched from Jira. Skipping deletion to be safe."
                )
                return {"status": "skipped", "reason": "no_issues_from_api"}

            # Get current IDs in raw_jira.issues
            result = conn.execute(text("SELECT id::text FROM raw_jira.issues"))
            raw_ids = {row[0] for row in result.fetchall()}

            ids_to_delete = raw_ids - all_issue_ids

            if ids_to_delete:
                context.log.info(f"Found {len(ids_to_delete)} ghost issues to delete")
                # Delete in batches to avoid huge SQL
                delete_list = list(ids_to_delete)
                batch_size = 1000
                total_deleted = 0

                delete_stmt = text(
                    "DELETE FROM raw_jira.issues WHERE id::text IN :ids"
                ).bindparams(bindparam("ids", expanding=True))

                for i in range(0, len(delete_list), batch_size):
                    batch = delete_list[i : i + batch_size]
                    conn.execute(delete_stmt, {"ids": tuple(batch)})
                    total_deleted += len(batch)

                conn.commit()
                context.log.info(f"Successfully deleted {total_deleted} ghost issues")
                return {"status": "success", "deleted_count": total_deleted}
            else:
                context.log.info("No ghost issues found")
                return {"status": "success", "deleted_count": 0}

    except Exception as e:
        context.log.error(f"Error during ghost cleanup: {e}")
        raise  # C-5: Let Dagster handle visibility
