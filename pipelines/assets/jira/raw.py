"""Raw Jira assets - dlt source for loading data from Jira API.

This module implements the raw layer (Bronze) of the medallion architecture.
Data is loaded as-is from Jira API into the raw_jira schema using dlt.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import dlt
from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetExecutionContext,
    asset,
    asset_check,
)
from dlt.pipeline.exceptions import PipelineConfigMissing, PipelineStepFailed
from dlt.sources.helpers import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_RETRYABLE_HTTP_EXCEPTIONS = tuple(
    exc
    for exc in (
        requests.HTTPError,
        getattr(requests, "Timeout", None),
        getattr(requests, "ConnectionError", None),
    )
    if exc is not None
)


def _get_http_timeout() -> tuple[float, float]:
    """Get connect/read timeout tuple from environment."""
    connect_timeout_raw = os.getenv("JIRA_HTTP_CONNECT_TIMEOUT_SEC", "5")
    read_timeout_raw = os.getenv("JIRA_HTTP_READ_TIMEOUT_SEC", "60")
    try:
        connect_timeout = float(connect_timeout_raw)
    except (TypeError, ValueError):
        connect_timeout = 5.0
    try:
        read_timeout = float(read_timeout_raw)
    except (TypeError, ValueError):
        read_timeout = 60.0
    return (connect_timeout, read_timeout)


def validate_jira_credentials(base_url: str, email: str, api_token: str) -> None:
    """Verify Jira credentials before starting a sync.

    Atlassian returns HTTP 200 even on auth failure, with the header
    X-Seraph-Loginreason: AUTHENTICATED_FAILED and an empty result set.
    Without this check, a bad token causes silent zero-row loads that are
    indistinguishable from a legitimate empty result.

    Raises:
        ValueError: if credentials are empty or authentication fails.
    """
    if not all([base_url, email, api_token]):
        raise ValueError(
            "Jira credentials incomplete: base_url, email, and api_token are required."
        )

    resp = requests.get(
        f"{base_url}/rest/api/3/project/search",
        params={"maxResults": 1},
        auth=(email, api_token),
        timeout=_get_http_timeout(),
    )

    login_reason = resp.headers.get("X-Seraph-Loginreason", "")
    if "AUTHENTICATED_FAILED" in login_reason or resp.status_code == 401:
        raise ValueError(
            f"Jira authentication failed (HTTP {resp.status_code}, "
            f"X-Seraph-Loginreason: {login_reason}). "
            "Check JIRA_API_TOKEN and JIRA_USER_EMAIL."
        )

    if resp.status_code not in (200, 403):
        raise ValueError(
            f"Unexpected Jira API response: HTTP {resp.status_code}. "
            f"Response: {resp.text[:200]}"
        )


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE_HTTP_EXCEPTIONS),
    reraise=True,
)
def _get_with_retry(url: str, **kwargs):
    """Execute GET request with exponential backoff retry."""
    kwargs.setdefault("timeout", _get_http_timeout())
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response


def _is_missing_relation_error(exc: BaseException) -> bool:
    """Detect PostgreSQL missing relation errors anywhere in exception chain."""
    to_visit = [exc]
    visited: set[int] = set()

    while to_visit:
        current = to_visit.pop()
        if current is None:
            continue
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)

        message = str(current).lower()
        if "relation" in message and "does not exist" in message:
            return True

        # dlt wraps root cause in different places depending on step and adapter.
        nested = getattr(current, "exception", None)
        if isinstance(nested, BaseException):
            to_visit.append(nested)
        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            to_visit.append(cause)
        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            to_visit.append(context)

    return False


def _extract_missing_relation(exc: BaseException) -> tuple[str, str] | None:
    """Extract (schema, table) from PostgreSQL relation-not-found errors."""
    pattern = re.compile(r'relation "([^"]+)"\."([^"]+)" does not exist', re.IGNORECASE)
    to_visit = [exc]
    visited: set[int] = set()

    while to_visit:
        current = to_visit.pop()
        if current is None:
            continue
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)

        match = pattern.search(str(current))
        if match:
            return match.group(1), match.group(2)

        nested = getattr(current, "exception", None)
        if isinstance(nested, BaseException):
            to_visit.append(nested)
        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            to_visit.append(cause)
        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            to_visit.append(context)

    return None


def _dlt_type_to_postgres_type(dlt_type: str) -> str:
    """Map dlt logical types to PostgreSQL types for fallback table creation."""
    mapping = {
        "text": "text",
        "bigint": "bigint",
        "double": "double precision",
        "bool": "boolean",
        "timestamp": "timestamp with time zone",
        "date": "date",
        "time": "time without time zone",
        "binary": "bytea",
        "json": "jsonb",
        "decimal": "numeric",
        "wei": "numeric",
    }
    return mapping.get(dlt_type, "text")


def _create_missing_table_from_pipeline_schema(
    pipeline: dlt.Pipeline, dataset_name: str, table_name: str
) -> bool:
    """Create a missing destination table based on current dlt schema metadata."""
    table_schema = pipeline.default_schema.tables.get(table_name)
    if not table_schema:
        return False

    columns = table_schema.get("columns", {})
    if not columns:
        return False

    col_defs: list[str] = []
    for column_name, column_schema in columns.items():
        data_type = _dlt_type_to_postgres_type(column_schema.get("data_type", "text"))
        nullable = column_schema.get("nullable", True)
        null_sql = "" if nullable else " NOT NULL"
        col_defs.append(f'"{column_name}" {data_type}{null_sql}')

    if not col_defs:
        return False

    create_sql = (
        f'CREATE TABLE IF NOT EXISTS "{dataset_name}"."{table_name}" '
        f'({", ".join(col_defs)});'
    )
    with pipeline.sql_client() as sql_client:
        sql_client.execute_sql(create_sql)
    return True


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
        start_at = 0
        next_page_token: str | None = None

        # 3.4: Limit fields whitelist
        default_fields = (
            "summary,description,issuetype,status,priority,assignee,reporter,creator,"
            "created,updated,resolutiondate,resolution,parent,subtasks,issuelinks,"
            "comment,worklog,labels,fixVersions,customfield_10020,customfield_10016,"
            "customfield_10036,customfield_10187,"
            "customfield_10028,project"
        )
        fields_to_fetch = os.getenv("JIRA_FIELDS_OVERRIDE", default_fields)

        def _iterate_search_jql() -> Iterator[dict[str, Any]]:
            nonlocal start_at, next_page_token

            while True:
                params = {
                    "jql": jql,
                    "maxResults": max_results,
                    "expand": "changelog,renderedFields",
                    "fields": fields_to_fetch,
                }
                if next_page_token:
                    params["nextPageToken"] = next_page_token
                else:
                    params["startAt"] = start_at

                response = _get_with_retry(
                    f"{base_url}/rest/api/3/search/jql",
                    auth=(email, api_token),
                    params=params,
                )
                data = response.json()

                issues = data.get("issues", [])
                for issue in issues:
                    yield issue

                fetched = len(issues)
                total = data.get("total")
                is_last = data.get("isLast")
                token = data.get("nextPageToken")

                if token:
                    next_page_token = token
                    start_at += fetched
                    continue

                next_page_token = None
                start_at += fetched

                if is_last is True:
                    break
                if fetched == 0:
                    break
                if isinstance(total, int) and start_at >= total:
                    break
                if fetched < max_results:
                    break

        try:
            yield from _iterate_search_jql()
            return
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            # Some Jira tenants still expose only the legacy /search endpoint.
            if status_code not in (404, 410):
                raise

        # Fallback to legacy endpoint with startAt/total pagination.
        start_at = 0
        while True:
            params = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "expand": "changelog,renderedFields",
                "fields": fields_to_fetch,
            }

            response = _get_with_retry(
                f"{base_url}/rest/api/3/search",
                auth=(email, api_token),
                params=params,
            )
            data = response.json()

            issues = data.get("issues", [])
            for issue in issues:
                yield issue

            total = data.get("total", 0)
            fetched = len(issues)
            start_at += fetched
            if fetched == 0 or start_at >= total:
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
        # First get all projects (paginated)
        start_at = 0
        max_results = 100
        while True:
            projects_response = _get_with_retry(
                f"{base_url}/rest/api/3/project/search",
                auth=(email, api_token),
                params={"startAt": start_at, "maxResults": max_results},
            )
            projects_response.raise_for_status()
            projects_data = projects_response.json()

            project_list = projects_data.get("values", [])
            for project in project_list:
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

            if projects_data.get("isLast", True):
                break
            start_at += max_results

    @dlt.resource(
        name="board_configurations",
        write_disposition="merge",
        primary_key="board_id",
    )
    def get_board_configurations() -> Iterator[dict[str, Any]]:
        """Fetch board configurations from Jira Agile API.

        For each board: GET /rest/agile/1.0/board/{boardId}/configuration
        """
        # First get all boards (paginated)
        start_at = 0
        max_results = 100
        while True:
            boards_response = _get_with_retry(
                f"{base_url}/rest/agile/1.0/board",
                auth=(email, api_token),
                params={"startAt": start_at, "maxResults": max_results},
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

            if boards_data.get("isLast", True):
                break
            start_at += max_results

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

    # Keep local state/schema in sync with destination.
    # On a fresh pipeline there is no extracted schema yet, so sync_schema can fail
    # with PipelineConfigMissing before the first run().
    pipeline.sync_destination()
    try:
        pipeline.sync_schema()
    except PipelineConfigMissing:
        pass

    def _build_source():
        return jira_source(
            base_url=base_url,
            email=email,
            api_token=api_token,
            projects=projects,
        )

    # Run the pipeline. If load fails due to missing relation, re-sync schema and retry once.
    try:
        load_info = pipeline.run(_build_source())
    except PipelineStepFailed as exc:
        if exc.step == "load" and _is_missing_relation_error(exc):
            relation = _extract_missing_relation(exc)
            table_created = False
            if relation:
                schema_name, table_name = relation
                if schema_name == destination_schema:
                    table_created = _create_missing_table_from_pipeline_schema(
                        pipeline,
                        destination_schema,
                        table_name,
                    )
            if not table_created:
                pipeline.sync_schema()
            load_info = pipeline.run(_build_source())
        else:
            raise

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

    Data is loaded into the raw_jira schema via dlt merge/upsert semantics.

    Configuration sources (in priority order):
    1. platform.projects + platform.tool_integrations (DB)
    2. config/projects.yaml (legacy fallback)
    3. Environment variables (last resort)
    """
    from pipelines.utils.db_config import get_active_projects_from_db

    db_projects = get_active_projects_from_db()

    if db_projects:
        context.log.info(f"DB config: {len(db_projects)} active projects")
        # Group by instance_url so we run one dlt pipeline per instance
        from collections import defaultdict

        by_instance: dict[str, list] = defaultdict(list)
        for p in db_projects:
            by_instance[p.instance_url].append(p)

        results = []
        for instance_url, instance_projects in by_instance.items():
            first = instance_projects[0]
            project_keys = [p.project_key for p in instance_projects]
            context.log.info(f"Syncing {project_keys} via {instance_url}")
            try:
                validate_jira_credentials(
                    first.instance_url, first.user_email, first.api_token
                )
            except ValueError as exc:
                context.log.error(
                    f"Jira credential validation failed for {instance_url}: {exc}"
                )
                raise
            for project_key in project_keys:
                try:
                    result = run_jira_pipeline(
                        base_url=first.instance_url,
                        email=first.user_email,
                        api_token=first.api_token,
                        projects=[project_key],
                        pipeline_name=f"jira_raw_{project_key}",
                    )
                    results.append(result)
                    context.log.info(
                        f"Project {project_key} sync completed: {result['load_info']}"
                    )
                except Exception as e:
                    context.log.error(f"Project {project_key} sync failed: {str(e)}")
                    raise
        return {
            "status": "success",
            "projects_synced": len(results),
            "details": results,
        }

    # Fallback: env vars (for local dev without DB)
    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_USER_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")
    projects_str = os.getenv("JIRA_PROJECTS", "")
    projects = [p.strip() for p in projects_str.split(",") if p.strip()] or None

    if not all([base_url, email, api_token]):
        context.log.warning(
            "Jira credentials not configured. "
            "Add an integration via the admin UI or set environment variables."
        )
        return {"status": "skipped", "reason": "credentials_not_configured"}

    try:
        validate_jira_credentials(base_url, email, api_token)
    except ValueError as exc:
        context.log.error(f"Jira credential validation failed: {exc}")
        raise

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


@asset_check(asset=raw_jira_data)
def check_raw_issues_project_populated(
    context: AssetCheckExecutionContext,
    database,
) -> AssetCheckResult:
    """Verify every issue in raw_jira.issues has a non-empty fields__project__id.

    Missing project IDs cause the clean layer JOIN to silently drop issues,
    which freezes jira_updated_at in clean_jira.issues.
    Root cause is usually a missing 'project' field in the Jira API whitelist.
    """
    from sqlalchemy import text

    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT COUNT(*) FROM raw_jira.issues
            WHERE fields__project__id IS NULL OR fields__project__id = ''
            """
            )
        )
        null_count = result.scalar() or 0

    return AssetCheckResult(
        passed=null_count == 0,
        metadata={"issues_missing_project_id": null_count},
    )


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

        # Get project credentials - DB first, then config fallback, then env
        from pipelines.utils.db_config import get_project_credentials

        creds = get_project_credentials(project_key)

        if creds:
            base_url = creds.instance_url
            email = creds.user_email
            api_token = creds.api_token
            context.log.info(f"Using DB credentials for {project_key} via {base_url}")
        else:
            # Fallback: env vars (for local dev without DB)
            context.log.warning(
                f"Project {project_key} not found in DB, falling back to env vars"
            )
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
