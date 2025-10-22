"""Prefect extract tasks wrapper for DLT resources.

Provides simple task wrappers that return DLT resource callables for a
given project and time window. The real network calls are performed by the
resource when Prefect/ DLT runs the pipeline; here we only prepare the
resource callables and metadata.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from prefect import task
from prefect.exceptions import MissingContextError

from services.dlt_jira_loader.dlt_sources.jira_cloud import jira_source
from services.dlt_jira_loader.utils.db import resolve_integration_secret
from services.dlt_jira_loader.models.config import ProjectWithCredentials


@task(name="extract.prepare_resources")
def prepare_resources(
    project: ProjectWithCredentials,
    date_from: str,
    date_to: str,
    config_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Iterable]:
    """Prepare DLT resource callables for a project.

    Args:
        project: project row with `external_key` and `credentials`.
        date_from/date_to: ISO strings for window (not used by all resources).
        config_overrides: optional config entries merged into credentials.

    Returns:
        Dict mapping resource names
        to DLT resource callables (callables expected by DLT).
    """
    try:
        # ensure logger doesn't raise when called inside non-Prefect context
        _logger = logging.getLogger(__name__)
    except MissingContextError:
        _logger = logging.getLogger(__name__)
    cfg = dict(project.credentials or {})
    # Resolve secret strictly from env when tool_integration_id present
    if getattr(project, "tool_integration_id", None):
        try:
            token = resolve_integration_secret(str(project.tool_integration_id))
            # do not log token; only inject into config for dlt source
            cfg["api_token"] = token
        except Exception:
            # Keep behavior deterministic for tests: if resolver fails and token
            # is not provided via credentials/env, jira_source will raise.
            pass
    if config_overrides:
        cfg.update(config_overrides)

    # include window metadata for resources that support date filters
    cfg["date_from"] = date_from
    cfg["date_to"] = date_to

    resources = jira_source(project.external_key, cfg)

    # resources is an iterable of resource callables (issues, sprints, comments,
    # ...)
    names: List[str] = [
        "issues",
        "sprints",
        "comments",
        "releases",
        "boards",
    ]

    return dict(zip(names, resources))
