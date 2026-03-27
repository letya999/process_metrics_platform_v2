"""Pydantic schemas for integration API endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IntegrationTypeResponse(BaseModel):
    """Response schema for integration type."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool


class IntegrationCreate(BaseModel):
    """Request schema for creating an integration."""

    integration_type_id: UUID = Field(..., description="ID of the integration type")
    instance_url: Optional[str] = Field(
        None, description="Instance URL for self-hosted systems"
    )
    user_email: Optional[str] = Field(
        None, description="User email in the integrated system"
    )
    api_token: str = Field(..., description="API token for authentication")
    secret_provider: str = Field(
        default="hardcoded",
        description="Secret provider: env, vault, aws_secrets, hardcoded",
    )


class IntegrationUpdate(BaseModel):
    """Request schema for updating an integration."""

    instance_url: Optional[str] = Field(
        None, description="Instance URL for self-hosted systems"
    )
    user_email: Optional[str] = Field(
        None, description="User email in the integrated system"
    )
    api_token: Optional[str] = Field(
        None, description="API token for authentication (if changing)"
    )
    is_active: Optional[bool] = Field(None, description="Whether integration is active")


class IntegrationResponse(BaseModel):
    """Response schema for integration."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    integration_type_id: UUID
    integration_type_name: Optional[str] = None
    instance_url: Optional[str] = None
    user_email: Optional[str] = None
    is_active: bool
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JiraProjectDiscovery(BaseModel):
    """A Jira project returned by the discovery endpoint."""

    key: str
    id: str
    name: str
    url: Optional[str] = None
    already_imported: bool = False


class SyncResponse(BaseModel):
    """Response schema for sync trigger."""

    message: str
    run_id: Optional[str] = None
    status: str


class SyncStatusResponse(BaseModel):
    """Response schema for sync status."""

    run_id: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
