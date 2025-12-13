"""Raw Jira assets - dlt source for loading data from Jira API.

This module implements the raw layer (Bronze) of the medallion architecture.
Data is loaded as-is from Jira API into the raw_jira schema using dlt.
"""

import os
from typing import Any, Iterator

import dlt
from dagster import AssetExecutionContext, asset
from dlt.sources.helpers import requests


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

    @dlt.resource(name="issues", write_disposition="merge", primary_key="id")
    def get_issues() -> Iterator[dict[str, Any]]:
        """Fetch issues from Jira API with changelog."""
        jql = ""
        if projects:
            project_list = ",".join(projects)
            jql = f"project in ({project_list})"

        max_results = 100
        next_page_token = None

        while True:
            params = {
                "jql": jql,
                "maxResults": max_results,
                "expand": "changelog,renderedFields",
                "fields": "*all",
            }
            # Add nextPageToken only if we have one (not on first request)
            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = requests.get(
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
            response = requests.get(
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
        boards_response = requests.get(
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
                    sprints_response = requests.get(
                        f"{base_url}/rest/agile/1.0/board/{board_id}/sprint",
                        auth=(email, api_token),
                        params={"startAt": start_at, "maxResults": 50},
                    )
                    sprints_response.raise_for_status()
                    sprints_data = sprints_response.json()

                    for sprint in sprints_data.get("values", []):
                        sprint["board_id"] = board_id
                        sprint["board_name"] = board.get("name")
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
                response = requests.get(
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
        projects_response = requests.get(
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
                versions_response = requests.get(
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
        boards_response = requests.get(
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
                config_response = requests.get(
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
        response = requests.get(
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
        pipeline_name="jira_raw",
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
        "row_counts": load_info.load_packages[0].jobs
        if load_info.load_packages
        else {},
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
    """
    # Get configuration from environment
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_USER_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")

    if not all([base_url, email, api_token]):
        context.log.warning(
            "Jira credentials not configured. "
            "Set JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN environment variables."
        )
        return {"status": "skipped", "reason": "credentials_not_configured"}

    # Get projects to sync (could be from config or run config)
    projects_str = os.getenv("JIRA_PROJECTS", "")
    projects = [p.strip() for p in projects_str.split(",") if p.strip()] or None

    context.log.info(f"Starting Jira sync for projects: {projects or 'all'}")

    try:
        result = run_jira_pipeline(
            base_url=base_url,
            email=email,
            api_token=api_token,
            projects=projects,
        )

        context.log.info(f"Jira sync completed: {result['load_info']}")
        return result

    except Exception as e:
        context.log.error(f"Jira sync failed: {str(e)}")
        raise
