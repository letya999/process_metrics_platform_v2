"""DLT source for Jira Cloud.

This module provides a minimal, well-typed DLT source exposing resources:
- issues
- sprints
- comments

The source reads credentials from the provided `config` dict or environment
variables (preferred for secrets). It is intentionally small and synchronous
to remain easy to test; network calls are performed via ``requests``.

Note: this file is a small implementation scaffold. Tests and additional
resources (changelog, custom_fields, versions) should be added later.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

import dlt

from services.dlt_jira_loader.app.clients.jira_client import (
    JiraClient,
    resolve_from_env_or_config,
)
from services.dlt_jira_loader.app.dlt_sources.resources.boards import (
    make_boards_resource,
)
from services.dlt_jira_loader.app.dlt_sources.resources.comments import (
    make_comments_resource,
)
from services.dlt_jira_loader.app.dlt_sources.resources.issues import (
    make_issues_resource,
)
from services.dlt_jira_loader.app.dlt_sources.resources.releases import (
    make_releases_resource,
)
from services.dlt_jira_loader.app.dlt_sources.resources.sprints import (
    make_sprints_resource,
)

# credentials in services/dlt_jira_loader/app/clients/jira_client.py


def jira_source(project_key: str, config: Dict[str, Any]) -> Iterable[dlt.Resource]:
    """Create a DLT source for a single Jira project.

    Args:
        project_key: Jira project key like "PROJ1"
        config: dictionary with credentials and optional api parameters:
            - instance_url
            - user_email
            - api_token

    Returns:
        Iterable of DLT resources: `issues`, `sprints`, `comments`.
    """
    instance_url = resolve_from_env_or_config(
        config, "instance_url", "JIRA_INSTANCE_URL"
    )
    user_email = resolve_from_env_or_config(config, "user_email", "JIRA_USER_EMAIL")
    api_token = resolve_from_env_or_config(config, "api_token", "JIRA_API_TOKEN")

    client = JiraClient(
        instance_url=instance_url, api_token=api_token, email=user_email
    )

    # resource factories (leave parametrization/binding to caller script)
    issues = make_issues_resource(project_key=project_key, client=client)
    sprints = make_sprints_resource(
        client=client
    )  # expects board_id when bound by caller
    comments = make_comments_resource(client=client)
    releases = make_releases_resource(client=client)
    boards = make_boards_resource(client=client, project_key=project_key)

    # return resource callables in the order expected by run_dlt_from_db.py
    return issues, sprints, comments, releases, boards
