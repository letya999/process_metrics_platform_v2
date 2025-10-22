"""Pydantic models for DLT Jira sync configuration and DTOs.

These are intentionally small, well-typed models used by the Prefect/ETL
orchestration code and unit tests.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectWithCredentials(BaseModel):
    """Representation of a project joined with its integration credentials."""

    project_id: UUID
    tool_integration_id: Optional[UUID] = None
    external_id: str
    external_key: str
    name: Optional[str] = None
    is_active: bool = True
    credentials: Dict[str, Any] = Field(default_factory=dict)


class JiraSyncConfig(BaseModel):
    """Top-level config for a jira_sync run.

    Fields:
        project_uuids: list of project UUIDs to sync
        date_from/date_to: optional ISO dates for the window
        dataset_name: target dataset for the pipeline
    """

    project_uuids: List[UUID]
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    dataset_name: str = Field(default="raw_jira_cloud_dlt")

    model_config = {"extra": "forbid"}


class SyncCheckpoint(BaseModel):
    """Represents an integration_sync_checkpoints row."""

    id: Optional[UUID] = None
    tool_integration_id: UUID
    project_id: Optional[UUID] = None
    entity_type: str
    last_synced_at: Optional[str] = None
    sync_metadata: Optional[Dict[str, Any]] = None


class JiraSyncResult(BaseModel):
    """Result summary for a single project sync run."""

    project_id: UUID
    status: str
    summary: Dict[str, Any]


class Release(BaseModel):
    """Representation of a Jira Release/Version."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    released: Optional[bool] = None
    releaseDate: Optional[str] = None


class Board(BaseModel):
    """Representation of a Jira Board associated with a project."""

    id: int
    name: Optional[str] = None
    type: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
