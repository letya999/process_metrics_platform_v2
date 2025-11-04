"""Flow configuration schemas with strict type hints."""
from datetime import datetime
from enum import Enum
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineRunStatus(str, Enum):
    """Pipeline run status."""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ProjectWithIntegration(BaseModel):
    """Project with integration credentials."""

    project_id: UUID
    project_name: str
    jira_project_key: str
    integration_id: UUID
    base_url: str
    api_token: str


class LoadInfo(BaseModel):
    """DLT load result."""

    rows_loaded: int = Field(ge=0)
    resources_loaded: List[str]
    last_synced_at: datetime
