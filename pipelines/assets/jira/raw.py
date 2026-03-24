"""Raw Jira assets - dlt source for loading data from Jira API.

This module implements the raw layer (Bronze) of the medallion architecture.
Data is loaded as-is from Jira API into the raw_jira schema using dlt.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import dlt
from dagster import AssetExecutionContext, asset
from dlt.sources.helpers import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(requests.HTTPError),
    reraise=True,
)
def _get_with_retry(url: str, **kwargs):
    """Execute GET request with exponential backoff retry."""
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response


@dlt.source(name="jira")
def jira_source(
    base_url: str,
    email: str,
    api_token: str,
    projects: list[str] | None = None,
):
    """dlt source for Jira Cloud API.

    Args:
        base_url: Jira Cloud instance URL (e.g., https://company.atlassian.net)
        email: User email for authentication
        api_token: Jira API token
        projects: List of project keys to sync (None = all accessible projects)

    Yields:
        dlt resources for issues, sprints, and changelogs
    """

    def _safe_updated_jql_value(
        raw_value: str | None, lookback_days: int
    ) -> str | None:
        """Build conservative JQL timestamp for incremental fetch.

        We re-read a configurable lookback window to recover from incremental
        state drift and out-of-order updates.
        """
        if not raw_value or raw_value == "1970-01-01T00:00:00.000+0000":
            return None

        parsed: datetime | None = None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(raw_value, fmt)
                break
            except ValueError:
                continue

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        lookback_point = parsed.astimezone(timezone.utc) - timedelta(
            days=max(0, lookback_days)
        )
        # Jira JQL accepts "YYYY-MM-DD HH:MM" in UTC.
        return lookback_point.strftime("%Y-%m-%d %H:%M")

    # Define incremental configuration to avoid B008 (function call in default arg)
    issues_incremental = dlt.sources.incremental(
        "fields.updated", initial_value="1970-01-01T00:00:00.000+0000"
    )

    @dlt.resource(name="issues", write_disposition="merge", primary_key="id")
    def get_issues(updated_at=issues_incremental) -> Iterator[dict[str, Any]]:
        """Fetch issues from Jira API with changelog."""
        jql = ""
        jql_parts = []
        issues_lookback_days = int(os.getenv("JIRA_ISSUES_LOOKBACK_DAYS", "45"))
        if projects:
            project_list = ",".join(projects)
            jql_parts.append(f"project in ({project_list})")

        # Add incremental filter to JQL for efficiency
        # Note: dlt handles the actual filtering, but adding it to JQL saves bandwidth
        from_updated = _safe_updated_jql_value(
            updated_at.last_value, issues_lookback_days
        )
        if from_updated:
            jql_parts.append(f'updated >= "{from_updated}"')

        if jql_parts:
            jql = " AND ".join(jql_parts)
            jql = f"{jql} ORDER BY updated ASC, key ASC"
        else:
            jql = "ORDER BY updated ASC, key ASC"

        max_results = 100
        next_page_token = None

        # 3.4: Limit fields whitelist
        default_fields = (
            "summary,description,issuetype,status,priority,assignee,reporter,creator,"
            "created,updated,resolutiondate,resolution,parent,subtasks,issuelinks,"
            "comment,worklog,labels,fixVersions,customfield_10020,customfield_10016,"
            "customfield_10028"
        )
        fields_to_fetch = os.getenv("JIRA_FIELDS_OVERRIDE", default_fields)

        while True:
            params = {
                "jql": jql,
                "maxResults": max_results,
                "expand": "changelog,renderedFields",
                "fields": fields_to_fetch,
            }
            # Add nextPageToken only if we have one (not on first request)
            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = _get_with_retry(
                f"{base_url}/rest/api/3/search/jql",
                auth=(email, api_token),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            issues = data.get("issues", [])
            for issue in issues:
                yield issue

            # Check if there are more results using isLast flag
            if data.get("isLast", True):
                break

            # Get nextPageToken for next iteration
            # Note: nextPageToken might not be in response if isLast is True
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

    @dlt.resource(name="projects", write_disposition="merge", primary_key="id")
    def get_projects() -> Iterator[dict[str, Any]]:
        """Fetch all accessible projects from Jira API."""
        start_at = 0
        max_results = 50

        while True:
            response = _get_with_retry(
                f"{base_url}/rest/api/3/project/search",
                auth=(email, api_token),
                params={
                    "startAt": start_at,
                    "maxResults": max_results,
                    "expand": "description,lead",
                },
            )
            response.raise_for_status()
            data = response.json()

            project_list = data.get("values", [])
            for project in project_list:
                if projects is None or project.get("key") in projects:
                    yield project

            # Check if there are more results
            if data.get("isLast", True):
                break
            start_at += max_results

    @dlt.resource(name="sprints", write_disposition="merge", primary_key="id")
    def get_sprints() -> Iterator[dict[str, Any]]:
        """Fetch sprints from all boards in specified projects."""
        # First get all boards
        boards_response = _get_with_retry(
            f"{base_url}/rest/agile/1.0/board",
            auth=(email, api_token),
            params={"maxResults": 100},
        )
        boards_response.raise_for_status()
        boards_data = boards_response.json()

        for board in boards_data.get("values", []):
            board_id = board.get("id")
            board_project = board.get("location", {}).get("projectKey")

            # Filter by project if specified
            if projects and board_project not in projects:
                continue

            # Get sprints for this board
            start_at = 0
            while True:
                try:
                    sprints_response = _get_with_retry(
                        f"{base_url}/rest/agile/1.0/board/{board_id}/sprint",
                        auth=(email, api_token),
                        params={"startAt": start_at, "maxResults": 50},
                    )
                    sprints_response.raise_for_status()
                    sprints_data = sprints_response.json()

                    for sprint in sprints_data.get("values", []):
                        sprint["board_id"] = board_id
                        sprint["board_name"] = board.get("name")
                        sprint["project_key"] = board_project
                        yield sprint

                    if sprints_data.get("isLast", True):
                        break
                    start_at += 50
                except requests.HTTPError:
                    # Board might not support sprints (Kanban boards)
                    break

    @dlt.resource(name="users", write_disposition="merge", primary_key="accountId")
    def get_users() -> Iterator[dict[str, Any]]:
        """Fetch users that are assignable to issues in specified projects."""
        for project_key in projects or []:
            start_at = 0
            while True:
                response = _get_with_retry(
                    f"{base_url}/rest/api/3/user/assignable/search",
                    auth=(email, api_token),
                    params={
                        "project": project_key,
                        "startAt": start_at,
                        "maxResults": 100,
                    },
                )
                response.raise_for_status()
                users = response.json()

                if not users:
                    break

                for user in users:
                    yield user

                if len(users) < 100:
                    break
                start_at += 100

    @dlt.resource(name="versions", write_disposition="merge", primary_key="id")
    def get_versions() -> Iterator[dict[str, Any]]:
        """Fetch project versions (releases) from Jira API.

        For each project: GET /rest/api/3/project/{projectKey}/versions
        """
        # First get all projects
        projects_response = _get_with_retry(
            f"{base_url}/rest/api/3/project/search",
            auth=(email, api_token),
            params={"maxResults": 100},
        )
        projects_response.raise_for_status()
        projects_data = projects_response.json()

        for project in projects_data.get("values", []):
            project_key = project.get("key")
            project_id = project.get("id")

            # Filter by project if specified
            if projects and project_key not in projects:
                continue

            try:
                # Get versions for this project
                versions_response = _get_with_retry(
                    f"{base_url}/rest/api/3/project/{project_key}/versions",
                    auth=(email, api_token),
                )
                versions_response.raise_for_status()
                versions = versions_response.json()

                for version in versions:
                    version["project_id"] = project_id
                    version["project_key"] = project_key
                    yield version

            except requests.HTTPError:
                # Some projects may not have versions enabled
                continue

    @dlt.resource(
        name="board_configurations",
        write_disposition="merge",
        primary_key="board_id",
    )
    def get_board_configurations() -> Iterator[dict[str, Any]]:
        """Fetch board configurations from Jira Agile API.

        For each board: GET /rest/agile/1.0/board/{boardId}/configuration
        """
        # First get all boards
        boards_response = _get_with_retry(
            f"{base_url}/rest/agile/1.0/board",
            auth=(email, api_token),
            params={"maxResults": 100},
        )
        boards_response.raise_for_status()
        boards_data = boards_response.json()

        for board in boards_data.get("values", []):
            board_id = board.get("id")
            board_project = board.get("location", {}).get("projectKey")

            # Filter by project if specified
            if projects and board_project not in projects:
                continue

            try:
                # Get configuration for this board
                config_response = _get_with_retry(
                    f"{base_url}/rest/agile/1.0/board/{board_id}/configuration",
                    auth=(email, api_token),
                )
                config_response.raise_for_status()
                config = config_response.json()

                yield {
                    "board_id": board_id,
                    "board_name": board.get("name"),
                    "board_type": board.get("type"),
                    "project_key": board_project,
                    "columns_config": config.get("columnConfig", {}),
                    "filter_id": config.get("filter", {}).get("id"),
                    "sub_query": config.get("subQuery", {}).get("query"),
                }

            except requests.HTTPError:
                # Some boards may not have configuration accessible
                continue

    @dlt.resource(
        name="fields",
        write_disposition="merge",
        primary_key="id",
    )
    def get_fields() -> Iterator[dict[str, Any]]:
        """Fetch all field definitions from Jira API.

        GET /rest/api/3/field
        """
        response = _get_with_retry(
            f"{base_url}/rest/api/3/field",
            auth=(email, api_token),
        )
        response.raise_for_status()
        fields = response.json()

        for field in fields:
            yield field

    return (
        get_issues,
        get_projects,
        get_sprints,
        get_users,
        get_versions,
        get_board_configurations,
        get_fields,
    )


def run_jira_pipeline(
    base_url: str,
    email: str,
    api_token: str,
    projects: list[str] | None = None,
    destination_schema: str = "raw_jira",
    pipeline_name: str = "jira_raw",
) -> dict[str, Any]:
    """Run the Jira dlt pipeline to load data into raw layer.

    Args:
        base_url: Jira Cloud instance URL
        email: User email for authentication
        api_token: Jira API token
        projects: List of project keys to sync
        destination_schema: Target schema name

    Returns:
        Pipeline load info
    """
    # Get PostgreSQL credentials from environment
    db_host = os.getenv("DAGSTER_POSTGRES_HOST", "postgres")
    db_port = os.getenv("DAGSTER_POSTGRES_PORT", "5432")
    db_name = os.getenv(
        "DAGSTER_POSTGRES_DB", os.getenv("POSTGRES_DB", "process_metrics")
    )
    db_user = os.getenv("DAGSTER_POSTGRES_USER", os.getenv("POSTGRES_USER", "postgres"))
    db_password = os.getenv(
        "DAGSTER_POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres")
    )

    # Set dlt environment variables (dlt reads these automatically)
    os.environ["DESTINATION__POSTGRES__CREDENTIALS__HOST"] = db_host
    os.environ["DESTINATION__POSTGRES__CREDENTIALS__PORT"] = db_port
    os.environ["DESTINATION__POSTGRES__CREDENTIALS__DATABASE"] = db_name
    os.environ["DESTINATION__POSTGRES__CREDENTIALS__USERNAME"] = db_user
    os.environ["DESTINATION__POSTGRES__CREDENTIALS__PASSWORD"] = db_password

    # Create dlt pipeline
    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="postgres",
        dataset_name=destination_schema,
    )

    # Create source
    source = jira_source(
        base_url=base_url,
        email=email,
        api_token=api_token,
        projects=projects,
    )

    # Run the pipeline
    load_info = pipeline.run(source)

    return {
        "pipeline_name": pipeline.pipeline_name,
        "destination": str(pipeline.destination),
        "dataset_name": pipeline.dataset_name,
        "load_info": str(load_info),
        "row_counts": (
            load_info.load_packages[0].jobs if load_info.load_packages else {}
        ),
    }


@asset(
    group_name="jira_raw",
    description=(
        "Load raw Jira data from Jira API (issues, projects, sprints, "
        "users, versions, board configs)"
    ),
    compute_kind="dlt",
)
def raw_jira_data(context: AssetExecutionContext) -> dict[str, Any]:
    """Dagster asset that loads raw data from Jira API using dlt.

    This asset loads:
    - issues (with changelog)
    - projects
    - sprints
    - users
    - versions (releases)
    - board_configurations

    Data is loaded into the raw_jira schema as append-only.

    Configuration sources (in priority order):
    1. Config file (config/projects.yaml)
    2. Environment variables (JIRA_BASE_URL, JIRA_PROJECTS, etc.)
    """
    # Try config file first
    base_url = None
    email = None
    api_token = None
    projects = None

    try:
        from config import get_config, get_project_keys

        config = get_config()
        project_keys = get_project_keys()

        if project_keys and config.jira_instances:
            # Get first enabled project's instance for credentials
            # (all-projects sync uses first instance)
            first_project = config.get_enabled_projects()[0]
            instance = config.get_project_instance(first_project)

            base_url = instance.base_url
            email = instance.email
            api_token = instance.get_api_token()
            projects = project_keys

            context.log.info(
                f"Using config file: {len(projects)} projects from "
                f"{first_project.jira_instance} instance"
            )
    except Exception as e:
        context.log.info(f"Config file not available, falling back to env: {e}")

    # Fallback to environment variables
    if not base_url:
        base_url = os.getenv("JIRA_BASE_URL", "")
    if not email:
        email = os.getenv("JIRA_USER_EMAIL", "")
    if not api_token:
        api_token = os.getenv("JIRA_API_TOKEN", "")
    if not projects:
        projects_str = os.getenv("JIRA_PROJECTS", "")
        projects = [p.strip() for p in projects_str.split(",") if p.strip()] or None

    if not all([base_url, email, api_token]):
        context.log.warning(
            "Jira credentials not configured. "
            "Set up config/projects.yaml or environment variables."
        )
        return {"status": "skipped", "reason": "credentials_not_configured"}

    context.log.info(f"Starting Jira sync for projects: {projects or 'all'}")

    results = []

    # If projects are specified, run a separate pipeline for each to maintain isolated incremental state.
    # If no projects specified (sync all), we must use one pipeline (shared state).
    # But usually 'projects' is populated from config.

    projects_to_sync = projects if projects else [None]

    for project_key in projects_to_sync:
        try:
            # Determine pipeline name
            # If project_key is None, it's a global sync (legacy/fallback)
            p_name = f"jira_raw_{project_key}" if project_key else "jira_raw_global"
            p_list = [project_key] if project_key else None

            context.log.info(
                f"Syncing project: {project_key or 'ALL'} (Pipeline: {p_name})"
            )

            result = run_jira_pipeline(
                base_url=base_url,
                email=email,
                api_token=api_token,
                projects=p_list,
                pipeline_name=p_name,
            )
            results.append(result)
            context.log.info(
                f"Project {project_key or 'ALL'} sync completed: {result['load_info']}"
            )

        except Exception as e:
            context.log.error(f"Project {project_key or 'ALL'} sync failed: {str(e)}")
            # Raise immediately or continue?
            # For sequential requirement, maybe better to fail hard so we don't calculate partial data?
            # User asked "update consistently all data schemas", so failing is safer.
            raise

    return {"status": "success", "projects_synced": len(results), "details": results}


# Import partitions for optional partitioned asset
try:
    from pipelines.partitions import project_partitions

    @asset(
        group_name="jira_raw_partitioned",
        description="Load raw Jira data for a single project (partitioned)",
        compute_kind="dlt",
        partitions_def=project_partitions,
    )
    def raw_jira_project_data(context: AssetExecutionContext) -> dict[str, Any]:
        """Dagster asset that loads raw data for a single Jira project.

        This asset is partitioned by project key, allowing:
        - Individual project syncs
        - Parallel syncs (via Dagster concurrency)
        - Mix of different Jira instances per project

        Use this asset when you want fine-grained control over project syncing.
        """
        project_key = context.partition_key
        context.log.info(f"Starting sync for project partition: {project_key}")

        # Get project configuration
        try:
            from config import get_config

            config = get_config()
            project = config.get_project(project_key)

            if project is None:
                context.log.error(f"Project {project_key} not found in config")
                return {
                    "status": "error",
                    "reason": f"project_not_found: {project_key}",
                }

            if not project.enabled:
                context.log.warning(f"Project {project_key} is disabled, skipping")
                return {"status": "skipped", "reason": "project_disabled"}

            instance = config.get_project_instance(project)

            base_url = instance.base_url
            email = instance.email
            api_token = instance.get_api_token()

            context.log.info(
                f"Using Jira instance '{project.jira_instance}' for {project_key}"
            )

        except Exception as e:
            context.log.warning(f"Config not available, using env vars: {e}")
            base_url = os.getenv("JIRA_BASE_URL", "")
            email = os.getenv("JIRA_USER_EMAIL", "")
            api_token = os.getenv("JIRA_API_TOKEN", "")

        if not all([base_url, email, api_token]):
            context.log.error("Jira credentials not configured")
            return {"status": "error", "reason": "credentials_not_configured"}

        try:
            result = run_jira_pipeline(
                base_url=base_url,
                email=email,
                api_token=api_token,
                projects=[project_key],
                pipeline_name=f"jira_raw_{project_key}",
            )

            context.log.info(f"Project {project_key} sync completed")
            return result

        except Exception as e:
            context.log.error(f"Project {project_key} sync failed: {str(e)}")
            raise

except ImportError:
    # Partitions module not available, skip partitioned asset
    pass
