#!/usr/bin/env python3
"""
DLT Jira Loader - Manual import script for Jira Cloud data
"""
# ruff: noqa: E501, C901

import argparse
import base64
import gc
import os
import re
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import dlt
import psycopg2
import yaml
from dlt.sources.helpers import requests
from dotenv import load_dotenv


def make_auth_headers(jira_user: str, jira_token: str) -> Dict[str, str]:
    """Create Basic Auth headers usable outside of jira_source."""
    auth_string = f"{jira_user}:{jira_token}"
    auth_b64 = base64.b64encode(auth_string.encode("ascii")).decode("ascii")
    return {"Authorization": f"Basic {auth_b64}", "Accept": "application/json"}


# @anchor:dlt_jira_loader:main
def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    with open(config_path, "r") as file:
        return yaml.safe_load(file)


# @anchor:dlt_jira_loader:database_config
def _parse_db_url(url: str) -> Dict[str, str]:
    p = urlparse(url)
    user = unquote(p.username) if p.username else None
    password = unquote(p.password) if p.password else None
    host = p.hostname or "localhost"
    port = str(p.port or 5432)
    dbname = p.path.lstrip("/") if p.path else ""
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": dbname,
    }


def get_database_config_from_env() -> Dict[str, str]:
    """Resolve DB config with this priority:
    1) Full URL via POSTGRES_URL / DATABASE_URL / AIRFLOW_CONN_POSTGRES_DEFAULT
    2) Secret file for password via POSTGRES_PASSWORD_FILE (or _PATH)
    3) Individual POSTGRES_* env vars

    Raises RuntimeError if required credentials are missing.
    """
    # 1) full URL (preferred)
    for key in ("POSTGRES_URL", "DATABASE_URL", "AIRFLOW_CONN_POSTGRES_DEFAULT"):
        url = os.getenv(key)
        if url:
            # normalize common airflow conn prefix
            if url.startswith("postgresql+psycopg2://"):
                url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
            return _parse_db_url(url)

    # 2) secret file for password
    pwd = None
    pwd_file = os.getenv("POSTGRES_PASSWORD_FILE") or os.getenv(
        "POSTGRES_PASSWORD_PATH"
    )
    if pwd_file and os.path.exists(pwd_file):
        try:
            with open(pwd_file, "r", encoding="utf-8") as fh:
                pwd = fh.read().strip()
        except Exception:
            pwd = None

    # 3) fall back to individual envs
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    db = os.getenv("POSTGRES_DB")

    # If none of the critical pieces are present, fail early
    if not (host and user and db) and not pwd:
        raise RuntimeError(
            "Database credentials not found. Set POSTGRES_URL or POSTGRES_HOST/POSTGRES_USER/POSTGRES_DB and a password (via POSTGRES_PASSWORD_FILE)."
        )

    return {
        "host": host or "localhost",
        "port": port or "5432",
        "user": user or "admin",
        "password": pwd or os.getenv("POSTGRES_PASSWORD", None),
        "database": db or "metrics",
    }


# @anchor:dlt_jira_loader:env_loader
def ensure_env_loaded():
    """Load .env from repository root if present"""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(this_dir, "../.."))
    env_path = os.path.join(repo_root, ".env")
    try:
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            # Also try default load (cwd)
            load_dotenv()
    except Exception:
        pass


# @anchor:dlt_jira_loader:db_helpers
def _pg_connect(db_cfg: Dict[str, str]):
    return psycopg2.connect(
        host=db_cfg["host"],
        port=int(db_cfg["port"]),
        user=db_cfg["user"],
        password=db_cfg["password"],
        dbname=db_cfg["database"],
    )


# @anchor:dlt_jira_loader:fetch_integration
def fetch_integration_credentials(
    db_cfg: Dict[str, str], user_id: str, integration_uuid: str
) -> Tuple[str, str, str]:
    """Return (jira_url, jira_user, jira_token) from tool_integrations by id and user_id.

    Backwards-compatible: support both direct token in `api_token_unsafe` and secret references
    (secret_provider='env' with secret_reference holding env var name).
    """
    sql = """
        SELECT instance_url, user_email, secret_reference, secret_provider, api_token_unsafe
        FROM tool_integrations
        WHERE id = %s::uuid AND user_id = %s::uuid
    """
    with _pg_connect(db_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (integration_uuid, user_id))
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    "Tool integration not found for given user_id and integration_uuid"
                )
            (
                instance_url,
                user_email,
                secret_reference,
                secret_provider,
                api_token_unsafe,
            ) = row

            # Resolve token: prefer secret_reference when provider='env'
            token = None
            try:
                if (
                    secret_provider
                    and isinstance(secret_provider, str)
                    and secret_provider.lower() == "env"
                    and secret_reference
                ):
                    # secret_reference expected to be env var name (e.g. INTEGRATION_TOKEN_{uuid})
                    token = os.getenv(secret_reference) or os.getenv(
                        secret_reference.upper()
                    )
                    # fallback: try a conventional name formed from integration_uuid
                    if not token:
                        token = os.getenv(f"INTEGRATION_TOKEN_{integration_uuid}")
            except Exception:
                token = None

            if not token and api_token_unsafe:
                token = api_token_unsafe

            if not instance_url or not user_email or not token:
                raise ValueError("Incomplete Jira credentials in tool_integrations")

            return instance_url.rstrip("/"), user_email, token


# @anchor:dlt_jira_loader:fetch_projects
def fetch_projects_by_ids(
    db_cfg: Dict[str, str],
    project_ids: List[str],
    user_id: str,
    integration_uuid: Optional[str],
) -> List[Dict[str, Any]]:
    """Return list of dicts: {id, external_key, external_url, tool_integration_id}"""
    if not project_ids:
        return []
    placeholders = ",".join(["%s"] * len(project_ids))
    params: List[Any] = [*project_ids, user_id]
    sql = f"""
        SELECT id::text, external_key, external_url, tool_integration_id::text
        FROM projects
        WHERE id IN ({placeholders})
          AND user_id = %s::uuid
    """
    if integration_uuid:
        sql += " AND tool_integration_id = %s::uuid"
        params.append(integration_uuid)
    with _pg_connect(db_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "external_key": r[1],
                    "external_url": (r[2] or "").rstrip("/"),
                    "tool_integration_id": r[3],
                }
                for r in rows
            ]


# @anchor:dlt_jira_loader:jira_source
@dlt.source
def jira_source(
    jira_url: str,
    jira_user: str,
    jira_token: str,
    project_key: str,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
):
    """DLT source for Jira Cloud data"""

    def get_auth_headers():
        """Create proper Basic Auth headers"""
        return make_auth_headers(jira_user, jira_token)

    # @anchor:dlt_jira_loader:jira_issues
    @dlt.resource(write_disposition="merge", primary_key=["issue_key"])
    def issues():
        """Extract issues from Jira Cloud"""
        headers = get_auth_headers()

        url = f"{jira_url}/rest/api/3/search/jql"
        jql_parts = [f"project = {project_key}"]
        # Include updated/resolutiondate in addition to created to capture edits/closures
        if created_from:
            jql_parts.append(
                f'(created >= "{created_from}" OR updated >= "{created_from}" OR resolutiondate >= "{created_from}")'
            )
        if created_to:
            jql_parts.append(
                f'(created <= "{created_to}" OR updated <= "{created_to}" OR resolutiondate <= "{created_to}")'
            )
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
            "customfield_10016",
            "customfield_10020",
            "customfield_10036",
        ]
        payload = {"jql": " AND ".join(jql_parts), "maxResults": 100, "fields": fields}
        print(f"Final JQL for issues: {payload['jql']}")

        total_processed = 0
        start_at = 0
        max_results = payload.get("maxResults", 100)
        while True:
            payload["startAt"] = start_at
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            issues_batch = data.get("issues", [])
            if not issues_batch:
                break
            batch_len = len(issues_batch)
            total_processed += batch_len
            print(f"Processing batch: {batch_len} issues (total: {total_processed})")

            for issue in issues_batch:
                fields = issue.get("fields", {})
                status = fields.get("status", {})
                issue_type = fields.get("issuetype", {})
                priority = fields.get("priority", {})
                assignee = fields.get("assignee", {})
                reporter = fields.get("reporter", {})
                components = fields.get("components", [])

                # Extract custom fields dynamically
                custom_fields = {}
                custom_fields_list = []
                for field_key, field_value in fields.items():
                    if field_key.startswith("customfield_") and field_value is not None:
                        custom_fields[field_key] = field_value
                        # also add to list for DLT to create a flat table
                        custom_fields_list.append(
                            {"field_id": field_key, "value": field_value}
                        )

                yield {
                    "issue_key": issue.get("key"),
                    "issue_id": issue.get("id"),
                    "summary": fields.get("summary"),
                    "description": fields.get("description"),
                    "status": status.get("name") if status else None,
                    "status_id": status.get("id") if status else None,
                    "issue_type": issue_type.get("name") if issue_type else None,
                    "issue_type_id": issue_type.get("id") if issue_type else None,
                    "priority": priority.get("name") if priority else None,
                    "assignee": assignee.get("displayName") if assignee else None,
                    "reporter": reporter.get("displayName") if reporter else None,
                    "created": fields.get("created"),
                    "updated": fields.get("updated"),
                    "resolution_date": fields.get("resolutiondate"),
                    "story_points": fields.get("customfield_10036"),
                    "labels": fields.get("labels", []),
                    "components": [
                        comp.get("name")
                        for comp in components
                        if comp and comp.get("name")
                    ],
                    "custom_fields": custom_fields,  # All custom fields as nested object
                    "custom_fields_list": custom_fields_list,  # Flat list of (field_id, value) pairs
                    "raw_data": issue,  # Keep full raw data
                }

            # advance pagination
            start_at += batch_len
            if batch_len < max_results:
                print(f"All issues processed. Total: {total_processed}")
                break
            # free page memory aggressively
            del data, issues_batch
            gc.collect()

    # @anchor:dlt_jira_loader:jira_issues_updated
    @dlt.resource(write_disposition="merge", primary_key=["issue_key"])
    def issues_updated():
        """Force a pass strictly by updated window to guarantee coverage of edits"""
        if not (created_from or created_to):
            return
        headers = get_auth_headers()
        url = f"{jira_url}/rest/api/3/search/jql"
        jql_parts = [f"project = {project_key}"]
        if created_from:
            jql_parts.append(f'updated >= "{created_from}"')
        if created_to:
            jql_parts.append(f'updated <= "{created_to}"')
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
            "customfield_10016",
            "customfield_10020",
            "customfield_10036",
        ]
        payload = {"jql": " AND ".join(jql_parts), "maxResults": 100, "fields": fields}
        print(f"Final JQL for issues_updated: {payload['jql']}")
        total_processed = 0
        start_at = 0
        max_results = payload.get("maxResults", 100)
        while True:
            payload["startAt"] = start_at
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            issues_batch = data.get("issues", [])
            if not issues_batch:
                break
            batch_len = len(issues_batch)
            total_processed += batch_len
            print(
                f"Processing updated batch: {batch_len} issues (total: {total_processed})"
            )
            for issue in issues_batch:
                f = issue.get("fields", {})
                status = f.get("status", {}) or {}
                issue_type = f.get("issuetype", {}) or {}
                assignee = f.get("assignee", {}) or {}
                reporter = f.get("reporter", {}) or {}
                components = f.get("components", []) or []
                custom_fields = {}
                custom_fields_list = []
                for fk, fv in f.items():
                    if fk.startswith("customfield_") and fv is not None:
                        custom_fields[fk] = fv
                        custom_fields_list.append({"field_id": fk, "value": fv})
                yield {
                    "issue_key": issue.get("key"),
                    "issue_id": issue.get("id"),
                    "summary": f.get("summary"),
                    "description": f.get("description"),
                    "status": status.get("name"),
                    "status_id": status.get("id"),
                    "issue_type": issue_type.get("name"),
                    "issue_type_id": issue_type.get("id"),
                    "priority": (f.get("priority") or {}).get("name")
                    if f.get("priority")
                    else None,
                    "assignee": assignee.get("displayName"),
                    "reporter": reporter.get("displayName"),
                    "created": f.get("created"),
                    "updated": f.get("updated"),
                    "resolutiondate": f.get("resolutiondate"),
                    "story_points": f.get("customfield_10036"),
                    "labels": f.get("labels", []),
                    "components": [
                        c.get("name") for c in components if c and c.get("name")
                    ],
                    "custom_fields": custom_fields,
                    "custom_fields_list": custom_fields_list,
                    "raw_data": issue,
                }
            start_at += batch_len
            if batch_len < max_results:
                break

    # @anchor:dlt_jira_loader:jira_issues_resolved
    @dlt.resource(write_disposition="merge", primary_key=["issue_key"])
    def issues_resolved():
        """Force a pass strictly by resolutiondate window to guarantee coverage of closures"""
        if not (created_from or created_to):
            return
        headers = get_auth_headers()
        url = f"{jira_url}/rest/api/3/search/jql"
        jql_parts = [f"project = {project_key}", "resolutiondate IS NOT EMPTY"]
        if created_from:
            jql_parts.append(f'resolutiondate >= "{created_from}"')
        if created_to:
            jql_parts.append(f'resolutiondate <= "{created_to}"')
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
            "customfield_10016",
            "customfield_10020",
            "customfield_10036",
        ]
        payload = {"jql": " AND ".join(jql_parts), "maxResults": 100, "fields": fields}
        print(f"Final JQL for issues_resolved: {payload['jql']}")
        total_processed = 0
        start_at = 0
        max_results = payload.get("maxResults", 100)
        while True:
            payload["startAt"] = start_at
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            issues_batch = data.get("issues", [])
            if not issues_batch:
                break
            batch_len = len(issues_batch)
            total_processed += batch_len
            print(
                f"Processing resolved batch: {batch_len} issues (total: {total_processed})"
            )
            for issue in issues_batch:
                f = issue.get("fields", {})
                status = f.get("status", {}) or {}
                issue_type = f.get("issuetype", {}) or {}
                assignee = f.get("assignee", {}) or {}
                reporter = f.get("reporter", {}) or {}
                components = f.get("components", []) or []
                custom_fields = {}
                custom_fields_list = []
                for fk, fv in f.items():
                    if fk.startswith("customfield_") and fv is not None:
                        custom_fields[fk] = fv
                        custom_fields_list.append({"field_id": fk, "value": fv})
                yield {
                    "issue_key": issue.get("key"),
                    "issue_id": issue.get("id"),
                    "summary": f.get("summary"),
                    "description": f.get("description"),
                    "status": status.get("name"),
                    "status_id": status.get("id"),
                    "issue_type": issue_type.get("name"),
                    "issue_type_id": issue_type.get("id"),
                    "priority": (f.get("priority") or {}).get("name")
                    if f.get("priority")
                    else None,
                    "assignee": assignee.get("displayName"),
                    "reporter": reporter.get("displayName"),
                    "created": f.get("created"),
                    "updated": f.get("updated"),
                    "resolutiondate": f.get("resolutiondate"),
                    "story_points": f.get("customfield_10036"),
                    "labels": f.get("labels", []),
                    "components": [
                        c.get("name") for c in components if c and c.get("name")
                    ],
                    "custom_fields": custom_fields,
                    "custom_fields_list": custom_fields_list,
                    "raw_data": issue,
                }
            start_at += batch_len
            if batch_len < max_results:
                break

    # @anchor:dlt_jira_loader:jira_projects
    @dlt.resource(write_disposition="merge", primary_key=["project_key"])
    def projects():
        """Extract project information"""
        headers = get_auth_headers()

        url = f"{jira_url}/rest/api/3/project/{project_key}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        project = response.json()

        yield {
            "project_key": project["key"],
            "project_id": project["id"],
            "project_name": project["name"],
            "project_type": project["projectTypeKey"],
            "lead": project.get("lead", {}).get("displayName"),
            "created": project.get("created"),
            "raw_data": project,
        }

    # @anchor:dlt_jira_loader:jira_project_statuses
    @dlt.resource(write_disposition="merge", primary_key=["project_key", "status_id"])
    def project_statuses():
        """Extract project statuses"""
        headers = get_auth_headers()

        url = f"{jira_url}/rest/api/3/project/{project_key}/statuses"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        statuses_data = response.json()

        print(f"Statuses API response structure: {type(statuses_data)}")
        print(
            f"Statuses data length: {len(statuses_data) if isinstance(statuses_data, list) else 'Not a list'}"
        )

        # API возвращает список статусов
        for status in statuses_data:
            yield {
                "project_key": project_key,
                "status_id": status.get("id"),
                "status_name": status.get("name"),
                "status_description": status.get("description"),
                "status_category": status.get("statusCategory", {}).get("name"),
                "status_color": status.get("statusCategory", {}).get("colorName"),
                "raw_data": status,
            }

    # @anchor:dlt_jira_loader:jira_sprints
    @dlt.resource(write_disposition="merge", primary_key=["project_key", "sprint_id"])
    def sprints():
        """Extract sprints from boards and project"""
        headers = get_auth_headers()

        total_sprints = 0
        processed_sprints = set()  # Для отслеживания уже обработанных спринтов

        # Method 1: Get sprints from boards (existing method)
        try:
            boards_url = f"{jira_url}/rest/agile/1.0/board"
            boards_params = {"projectKeyOrId": project_key}

            boards_response = requests.get(
                boards_url, headers=headers, params=boards_params
            )
            boards_response.raise_for_status()
            boards_data = boards_response.json()

            for board in boards_data.get("values", []):
                board_id = board["id"]

                # Get sprints for this board with pagination
                sprints_url = f"{jira_url}/rest/agile/1.0/board/{board_id}/sprint"
                sprints_params = {"startAt": 0, "maxResults": 50}

                while True:
                    sprints_response = requests.get(
                        sprints_url, headers=headers, params=sprints_params
                    )
                    sprints_response.raise_for_status()
                    sprints_data = sprints_response.json()

                    sprints_batch = sprints_data.get("values", [])
                    print(
                        f"Processing sprints batch: {len(sprints_batch)} sprints for board {board_id}"
                    )

                    for sprint in sprints_batch:
                        sprint_key = (project_key, sprint.get("id"))
                        if sprint_key not in processed_sprints:
                            processed_sprints.add(sprint_key)
                            total_sprints += 1
                            yield {
                                "project_key": project_key,
                                "board_id": board_id,
                                "board_name": board.get("name"),
                                "sprint_id": sprint.get("id"),
                                "sprint_name": sprint.get("name"),
                                "sprint_state": sprint.get("state"),
                                "sprint_start_date": sprint.get("startDate"),
                                "sprint_end_date": sprint.get("endDate"),
                                "sprint_complete_date": sprint.get("completeDate"),
                                "sprint_goal": sprint.get("goal"),
                                "raw_data": sprint,
                            }

                    # Check if we've processed all sprints for this board
                    if len(sprints_batch) < 50:
                        break

                    sprints_params["startAt"] += 50
        except Exception as e:
            print(f"Warning: Could not get sprints from boards: {e}")

        # Method 2: Get sprints directly from project (alternative method)
        try:
            # Try to get sprints directly from project
            project_sprints_url = f"{jira_url}/rest/agile/1.0/sprint"
            project_sprints_params = {
                "projectKeyOrId": project_key,
                "startAt": 0,
                "maxResults": 100,
            }

            while True:
                project_sprints_response = requests.get(
                    project_sprints_url, headers=headers, params=project_sprints_params
                )
                project_sprints_response.raise_for_status()
                project_sprints_data = project_sprints_response.json()

                project_sprints_batch = project_sprints_data.get("values", [])
                print(
                    f"Processing project sprints batch: {len(project_sprints_batch)} sprints"
                )

                for sprint in project_sprints_batch:
                    sprint_key = (project_key, sprint.get("id"))
                    if sprint_key not in processed_sprints:
                        processed_sprints.add(sprint_key)
                        total_sprints += 1
                        yield {
                            "project_key": project_key,
                            "board_id": None,
                            "board_name": None,
                            "sprint_id": sprint.get("id"),
                            "sprint_name": sprint.get("name"),
                            "sprint_state": sprint.get("state"),
                            "sprint_start_date": sprint.get("startDate"),
                            "sprint_end_date": sprint.get("endDate"),
                            "sprint_complete_date": sprint.get("completeDate"),
                            "sprint_goal": sprint.get("goal"),
                            "raw_data": sprint,
                        }

                # Check if we've processed all sprints
                if len(project_sprints_batch) < 100:
                    break

                project_sprints_params["startAt"] += 100
        except Exception as e:
            print(f"Warning: Could not get sprints from project: {e}")

        print(f"Total sprints processed: {total_sprints}")

    # @anchor:dlt_jira_loader:jira_versions
    @dlt.resource(write_disposition="merge", primary_key=["project_key", "version_id"])
    def versions():
        """Extract project versions/releases"""
        headers = get_auth_headers()

        url = f"{jira_url}/rest/api/3/project/{project_key}/versions"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        versions_data = response.json()

        print(f"Processing {len(versions_data)} versions for project {project_key}")

        for version in versions_data:
            yield {
                "project_key": project_key,
                "version_id": version.get("id"),
                "version_name": version.get("name"),
                "version_description": version.get("description"),
                "version_archived": version.get("archived", False),
                "version_released": version.get("released", False),
                "version_release_date": version.get("releaseDate"),
                "version_user_release_date": version.get("userReleaseDate"),
                "version_start_date": version.get("startDate"),
                "version_user_start_date": version.get("userStartDate"),
                "version_overdue": version.get("overdue", False),
                "raw_data": version,
            }

    # @anchor:dlt_jira_loader:jira_boards
    @dlt.resource(write_disposition="merge", primary_key=["board_id"])
    def boards():
        """Extract board information"""
        headers = get_auth_headers()

        url = f"{jira_url}/rest/agile/1.0/board"
        params = {"projectKeyOrId": project_key}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        for board in data.get("values", []):
            yield {
                "board_id": board["id"],
                "board_name": board["name"],
                "board_type": board["type"],
                "project_key": project_key,
                "raw_data": board,
            }

    # @anchor:dlt_jira_loader:jira_fields
    @dlt.resource(write_disposition="merge", primary_key=["id"])
    def fields():
        """Extract field metadata including custom fields"""
        headers = get_auth_headers()

        url = f"{jira_url}/rest/api/3/field"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        fields_data = response.json()

        print(f"Processing {len(fields_data)} fields metadata")

        for field in fields_data:
            yield {
                "id": field.get("id"),
                "name": field.get("name"),
                "custom": field.get("custom", False),
                "orderable": field.get("orderable", False),
                "navigable": field.get("navigable", False),
                "searchable": field.get("searchable", False),
                "clause_names": field.get("clauseNames", []),
                "schema_type": field.get("schema", {}).get("type")
                if field.get("schema")
                else None,
                "schema_system": field.get("schema", {}).get("system")
                if field.get("schema")
                else None,
                "raw_data": field,
            }

    # @anchor:dlt_jira_loader:jira_changelog
    @dlt.resource(write_disposition="merge", primary_key=["issue_key", "change_id"])
    def changelog():
        """Extract issue changelog for history tracking"""
        headers = get_auth_headers()

        # Use enhanced JQL search with expand=changelog to get changelogs in-page
        search_url = f"{jira_url}/rest/api/3/search/jql"
        jql_parts = [f"project = {project_key}"]
        # For changelog, also select issues updated in the window
        if created_from:
            jql_parts.append(
                f'(created >= "{created_from}" OR updated >= "{created_from}" OR resolutiondate >= "{created_from}")'
            )
        if created_to:
            jql_parts.append(
                f'(created <= "{created_to}" OR updated <= "{created_to}" OR resolutiondate <= "{created_to}")'
            )
        payload = {
            "jql": " AND ".join(jql_parts),
            "maxResults": 50,
            "fields": ["key"],
            "expand": "changelog",
        }
        print(f"Final JQL for changelog: {payload['jql']}")

        total_processed = 0
        total_changes = 0
        next_token = None

        while True:
            if next_token:
                payload["nextPageToken"] = next_token
            resp = requests.post(search_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            issues_batch = data.get("issues", [])
            total_processed += len(issues_batch)
            print(
                f"Processing changelog batch: {len(issues_batch)} issues (total: {total_processed})"
            )

            for issue in issues_batch:
                issue_key = issue.get("key")
                ch = issue.get("changelog", {}) or {}
                histories = ch.get("histories", []) or []
                # 1) yield page included via expand
                for history in histories:
                    created = history.get("created")
                    author = history.get("author", {}).get("displayName")
                    for item in history.get("items", []) or []:
                        total_changes += 1
                        yield {
                            "issue_key": issue_key,
                            "change_id": history.get("id"),
                            "change_date": created,
                            "change_author": author,
                            "field": item.get("field"),
                            "field_id": item.get("fieldId"),
                            "field_type": item.get("fieldtype"),
                            "from_value": item.get("fromString"),
                            "to_value": item.get("toString"),
                            "from_value_id": item.get("from"),
                            "to_value_id": item.get("to"),
                            "raw_data": {"history": history, "item": item},
                        }
                # 2) if truncated, fetch remaining pages from issue changelog endpoint
                total_h = ch.get("total")
                returned_h = len(histories)
                if isinstance(total_h, int) and total_h > returned_h:
                    headers = get_auth_headers()
                    per_page = 100
                    start_at = returned_h
                    while start_at < total_h:
                        url = f"{jira_url}/rest/api/3/issue/{issue_key}/changelog"
                        params = {"startAt": start_at, "maxResults": per_page}
                        r = requests.get(url, headers=headers, params=params)
                        r.raise_for_status()
                        data_ch = r.json() or {}
                        page_histories = data_ch.get("values", []) or []
                        if not page_histories:
                            break
                        for history in page_histories:
                            created = history.get("created")
                            author = (history.get("author") or {}).get("displayName")
                            for item in history.get("items", []) or []:
                                total_changes += 1
                                yield {
                                    "issue_key": issue_key,
                                    "change_id": history.get("id"),
                                    "change_date": created,
                                    "change_author": author,
                                    "field": item.get("field"),
                                    "field_id": item.get("fieldId"),
                                    "field_type": item.get("fieldtype"),
                                    "from_value": item.get("fromString"),
                                    "to_value": item.get("toString"),
                                    "from_value_id": item.get("from"),
                                    "to_value_id": item.get("to"),
                                    "raw_data": {"history": history, "item": item},
                                }
                        # advance
                        got = len(page_histories)
                        start_at += got

            next_token = data.get("nextPageToken")
            if not next_token:
                print(
                    f"All changelog processed. Total issues: {total_processed}, Total changes: {total_changes}"
                )
                break
            del data, issues_batch
            gc.collect()

    # @anchor:dlt_jira_loader:issue_custom_fields
    @dlt.resource(write_disposition="merge", primary_key=["issue_key", "field_id"])
    def issue_custom_fields():
        """Extract flat custom field rows (issue_key, field_id, value)"""
        headers = get_auth_headers()
        url = f"{jira_url}/rest/api/3/search/jql"
        payload = {
            "jql": f"project = {project_key}",
            "maxResults": 25,
            "fields": ["*all"],
        }
        total = 0
        start_at = 0
        max_results = payload.get("maxResults", 25)
        while True:
            payload["startAt"] = start_at
            resp = requests.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            issues_batch = data.get("issues", [])
            if not issues_batch:
                break
            batch_len = len(issues_batch)
            total += batch_len
            print(f"Processing CF batch: {batch_len} issues (total: {total})")
            for issue in issues_batch:
                issue_key = issue.get("key")
                issue_id = issue.get("id")
                fields = issue.get("fields", {})
                for fk, fv in fields.items():
                    if fk.startswith("customfield_") and fv is not None:
                        yield {
                            "issue_key": issue_key,
                            "issue_id": issue_id,
                            "field_id": fk,
                            "value": fv,
                            "raw_data": {"field": fk, "value": fv},
                        }
            start_at += batch_len
            if batch_len < max_results:
                break
            del data, issues_batch
            gc.collect()

    # @anchor:integration:jira:cf10036_table
    @dlt.resource(
        name="issues__raw_data__fields__customfield_10036",
        write_disposition="merge",
        primary_key=["issue_key"],
    )
    def cf10036_table():
        """Force a table for scalar Story Points (customfield_10036) to match DAG pattern"""
        headers = get_auth_headers()
        url = f"{jira_url}/rest/api/3/search/jql"
        jql_parts = [f"project = {project_key}"]
        if created_from:
            jql_parts.append(
                f'(created >= "{created_from}" OR updated >= "{created_from}" OR resolutiondate >= "{created_from}")'
            )
        if created_to:
            jql_parts.append(
                f'(created <= "{created_to}" OR updated <= "{created_to}" OR resolutiondate <= "{created_to}")'
            )

        payload = {
            "jql": " AND ".join(jql_parts),
            "maxResults": 25,
            "fields": ["key", "customfield_10036"],
        }

        start_at = 0
        max_results = payload.get("maxResults", 25)
        while True:
            payload["startAt"] = start_at
            resp = requests.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            issues_batch = data.get("issues", [])
            if not issues_batch:
                break
            for issue in issues_batch:
                f = issue.get("fields", {}) or {}
                sp = f.get("customfield_10036")
                if sp is not None:
                    yield {"issue_key": issue.get("key"), "value": sp}
            batch_len = len(issues_batch)
            start_at += batch_len
            if batch_len < max_results:
                break
            del data
            gc.collect()

    # @anchor:integration:jira:board_config
    @dlt.resource(write_disposition="merge", primary_key=["board_id"])
    def board_config():
        """Extract full board configuration for each board of the project and store raw JSON"""
        headers = get_auth_headers()

        boards_url = f"{jira_url}/rest/agile/1.0/board"
        params = {"projectKeyOrId": project_key}

        resp = requests.get(boards_url, headers=headers, params=params)
        resp.raise_for_status()
        boards_data = resp.json()

        for board in boards_data.get("values", []):
            board_id = board.get("id")
            cfg_url = f"{jira_url}/rest/agile/1.0/board/{board_id}/configuration"
            try:
                cfg_resp = requests.get(cfg_url, headers=headers)
                cfg_resp.raise_for_status()
                cfg = cfg_resp.json()
            except Exception as e:
                print(
                    f"Warning: could not fetch configuration for board {board_id}: {e}"
                )
                cfg = None

            yield {
                "board_id": board_id,
                "board_name": board.get("name"),
                "board_type": board.get("type"),
                "project_key": project_key,
                "raw_data": cfg,
            }

    # Ensure issue_custom_fields resource is returned so DLT materializes flat custom fields list
    # Order resources so that issues are fetched via broad window, then explicitly by updated, then by resolutiondate
    return (
        issues,
        issues_updated,
        issues_resolved,
        projects,
        project_statuses,
        sprints,
        versions,
        boards,
        fields,
        changelog,
        issue_custom_fields,
        cf10036_table,
        board_config,
    )


# @anchor:dlt_jira_loader:main_function
def main():
    """Main entry point for DLT Jira import"""
    parser = argparse.ArgumentParser(description="DLT Jira Cloud Data Import")
    parser.add_argument(
        "--config",
        required=False,
        help="Path to config.yaml file (optional, for backward compatibility)",
    )
    parser.add_argument(
        "--project-uuids",
        nargs="*",
        default=None,
        help="List of project UUIDs to import",
    )
    parser.add_argument(
        "--user-id", default=None, help="User UUID that owns the projects/integration"
    )
    parser.add_argument(
        "--integration-uuid",
        default=None,
        help="Tool integration UUID to fetch Jira credentials",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        help="(deprecated) Filter: created >= YYYY-MM-DD (back-compat)",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="(deprecated) Filter: created <= YYYY-MM-DD (back-compat)",
    )
    parser.add_argument(
        "--created-from", default=None, help="Filter: created >= YYYY-MM-DD"
    )
    parser.add_argument(
        "--created-to", default=None, help="Filter: created <= YYYY-MM-DD"
    )
    parser.add_argument(
        "--dataset-name",
        default=os.getenv("DLT_DATASET", "raw_jira"),
        help="Target dataset/schema name in destination",
    )
    parser.add_argument(
        "--debug-issue",
        default=None,
        help="Issue key to debug via direct Jira API call",
    )
    args = parser.parse_args()

    # Load env from repo root
    ensure_env_loaded()

    # Load DB config from env
    db_config = get_database_config_from_env()

    # Optional fallback to config.yaml only for project keys if CLI not provided
    config: Dict[str, Any] = {}
    if args.config:
        try:
            config = load_config(args.config)
        except Exception:
            config = {}

    # Resolve project list
    project_keys: List[str] = []
    project_ids: List[str] = []
    # Back-compat: accept old --date-from/--date-to or config.project.date_from/date_to
    # New canonical flags: --created-from / --created-to or config.project.created_from/created_to
    date_from_flag = args.date_from or args.created_from
    date_to_flag = args.date_to or args.created_to

    cfg_project = config.get("project", {}) or {}
    cfg_from = cfg_project.get("created_from") or cfg_project.get("date_from")
    cfg_to = cfg_project.get("created_to") or cfg_project.get("date_to")

    created_from = date_from_flag or cfg_from
    created_to = date_to_flag or cfg_to

    # If no created_from provided, default to last 5 years to avoid unbounded JQL queries
    if not created_from:
        five_years_ago = (date.today() - timedelta(days=5 * 365)).isoformat()
        created_from = five_years_ago
        print(
            f"Warning: no --created-from provided; defaulting to last 5 years (created_from={created_from})."
            " To override, pass --created-from explicitly."
        )

    # If project UUIDs provided, fetch external_key(s) from DB
    def _normalize_project_uuids(raw: Optional[List[str]]) -> List[str]:
        if not raw:
            return []
        out: List[str] = []
        for item in raw:
            if not item:
                continue
            if isinstance(item, str) and ("," in item or ";" in item):
                parts = re.split(r"[,;]\s*", item)
                out.extend([p.strip() for p in parts if p.strip()])
            else:
                out.append(str(item))
        return out

    if args.project_uuids and args.user_id:
        project_ids = _normalize_project_uuids(args.project_uuids)
        projects = fetch_projects_by_ids(
            db_config, project_ids, args.user_id, args.integration_uuid
        )
        if not projects:
            raise ValueError("No projects found for provided project_uuids and user_id")
        project_keys = [p["external_key"] for p in projects]
        # If integration url is inconsistent, warn (but continue)
        unique_urls = {p["external_url"] for p in projects if p.get("external_url")}
        if len(unique_urls) > 1:
            print(
                f"Warning: Selected projects reference multiple instance URLs: {unique_urls}"
            )
    else:
        # Fallback to config 'project.key'
        project_config = config.get("project", {})
        project_key_config = project_config.get("key")
        if project_key_config is None:
            raise ValueError(
                "Provide --project-uuids + --user-id, or set project.key in config"
            )
        if isinstance(project_key_config, list):
            project_keys = [str(k) for k in project_key_config]
        elif isinstance(project_key_config, str):
            if "," in project_key_config:
                project_keys = [
                    k.strip() for k in project_key_config.split(",") if k.strip()
                ]
            else:
                project_keys = [project_key_config]
        else:
            raise ValueError("project.key must be a string or a list of strings")

    # Resolve Jira credentials: priority DB by integration UUID, else .env
    jira_url: Optional[str] = None
    jira_user: Optional[str] = None
    jira_token: Optional[str] = None
    if args.user_id and args.integration_uuid:
        jira_url, jira_user, jira_token = fetch_integration_credentials(
            db_config, args.user_id, args.integration_uuid
        )
    else:
        # From environment variables only
        jira_url = (os.getenv("JIRA_URL") or "").rstrip("/")
        jira_user = os.getenv("JIRA_USER")
        jira_token = os.getenv("JIRA_TOKEN")
    if not (jira_url and jira_user and jira_token):
        raise ValueError(
            "Jira credentials are missing. Provide --integration-uuid and --user-id or set JIRA_URL/JIRA_USER/JIRA_TOKEN in .env"
        )

    print(f"Starting DLT import for projects: {project_keys}")
    print(
        f"Target database: {db_config['database']} on {db_config['host']}:{db_config['port']}"
    )

    # Create .dlt directory and config files (once)
    dlt_dir = os.path.join(os.getcwd(), ".dlt")
    os.makedirs(dlt_dir, exist_ok=True)

    # Create config.toml file (non-secret values)
    config_content = f"""
[destination.postgres.credentials]
host = "{db_config['host']}"
port = {db_config['port']}
username = "{db_config['user']}"
database = "{db_config['database']}"
"""

    config_file = os.path.join(dlt_dir, "config.toml")
    with open(config_file, "w") as f:
        f.write(config_content)

    # Create secrets.toml file (secret values)
    secrets_content = f"""
[destination.postgres.credentials]
password = "{db_config['password']}"
"""

    secrets_file = os.path.join(dlt_dir, "secrets.toml")
    with open(secrets_file, "w") as f:
        f.write(secrets_content)

    # Create DLT pipeline (single pipeline reused per project)
    pipeline = dlt.pipeline(
        pipeline_name="jira_loader",
        destination="postgres",
        dataset_name=args.dataset_name,
    )

    # Run pipeline for each project key
    overall_success = True
    for pk in project_keys:
        print(f"\n--- Starting import for project: {pk} ---")
        # If debug_issue provided, fetch and print its current remote state before running pipeline
        debug_issue = args.debug_issue or os.getenv("DEBUG_ISSUE_KEY")

        def fetch_and_print_issue(issue_key: str):
            try:
                headers = make_auth_headers(jira_user, jira_token)
                url_issue = f"{jira_url}/rest/api/3/issue/{issue_key}"
                resp = requests.get(
                    url_issue,
                    headers=headers,
                    params={
                        "fields": "created,updated,resolutiondate,status,comment,summary"
                    },
                )
                resp.raise_for_status()
                data = resp.json() or {}
                fields = data.get("fields", {})
                print(
                    f"Remote issue {issue_key} fields: created={fields.get('created')}, updated={fields.get('updated')}, resolutiondate={fields.get('resolutiondate')}, status={fields.get('status',{}).get('name')}"
                )
            except Exception as e:
                print(f"Failed to fetch remote issue {issue_key}: {e}")

        if debug_issue:
            print(f"DEBUG: fetching remote issue before pipeline for {debug_issue}")
            fetch_and_print_issue(debug_issue)
        source = jira_source(
            jira_url=jira_url,
            jira_user=jira_user,
            jira_token=jira_token,
            project_key=pk,
            created_from=created_from,
            created_to=created_to,
        )
        try:
            load_info = pipeline.run(source)
            print(f"Import for project {pk} completed successfully!")
            # Print DLT load summary (tables loaded and counts) when available
            try:
                if hasattr(load_info, "loads_ids") and isinstance(
                    load_info.loads_ids, dict
                ):
                    print(f"DLT loads_ids keys: {list(load_info.loads_ids.keys())}")
                if hasattr(load_info, "load_id"):
                    print(f"DLT load_id: {load_info.load_id}")
                # Some pipeline implementations return stats per table in load_info.report or similar
                if hasattr(load_info, "report"):
                    print(f"DLT load report: {load_info.report}")
            except Exception as e:
                print(f"Failed to print DLT load_info details: {e}")
            # Post-run verification: quick checks to ensure updated/resolved rows were written
            try:
                with _pg_connect(db_config) as conn:
                    with conn.cursor() as cur:
                        if created_from:
                            like_pattern = pk + "-%"
                            q = """
                            SELECT COUNT(*) FROM raw_jira.issues
                            WHERE issue_key LIKE %s
                              AND (
                                (created IS NOT NULL AND created >= %s)
                                OR (updated IS NOT NULL AND updated >= %s)
                                OR (resolution_date IS NOT NULL AND resolution_date >= %s)
                              )
                            """
                            cur.execute(
                                q,
                                (
                                    like_pattern,
                                    created_from,
                                    created_from,
                                    created_from,
                                ),
                            )
                            cnt = cur.fetchone()[0]
                            print(
                                f"Post-run verification: raw_jira.issues matching window for {pk}: {cnt}"
                            )
                            # show top 5 recently-updated for project
                            q2 = """
                            SELECT issue_key, created, updated, resolution_date
                            FROM raw_jira.issues
                            WHERE issue_key LIKE %s
                            ORDER BY COALESCE(updated, created) DESC
                            LIMIT 5
                            """
                            cur.execute(q2, (like_pattern,))
                            rows = cur.fetchall()
                            print(f"Top recent rows for {pk}: {rows}")
                        else:
                            print(
                                "No created_from provided; skipping post-run updated/resolved verification"
                            )
            except Exception as verf_e:
                print(f"Post-run DB verification failed: {verf_e}")
            # fetch and print remote issue after pipeline run as additional check
            if debug_issue:
                print(f"DEBUG: fetching remote issue after pipeline for {debug_issue}")
                fetch_and_print_issue(debug_issue)
            # Print summary per run
            if hasattr(load_info, "load_id"):
                print(f"Load ID: {load_info.load_id}")
            if hasattr(load_info, "loads_ids"):
                loads_ids = load_info.loads_ids
                if isinstance(loads_ids, dict):
                    print(f"Loaded tables for {pk}: {list(loads_ids.keys())}")

        except Exception as e:
            overall_success = False
            print(f"Import failed for project {pk}: {e}")
            # continue to next project
            continue

    if not overall_success:
        print("One or more project imports failed. Check logs.")
        sys.exit(1)
    else:
        print("All project imports completed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
