"""Pydantic schemas for project API endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.orm import ProjectAccessLevel


class ProjectCreate(BaseModel):
    """Request schema for creating a project."""

    tool_integration_id: UUID = Field(..., description="ID of the tool integration")
    external_key: str = Field(..., description="Project key in external system")
    external_id: str = Field(..., description="Project ID in external system")
    name: str = Field(..., description="Project name")
    external_url: Optional[str] = Field(
        None, description="Direct link to project in external system"
    )


class ProjectUpdate(BaseModel):
    """Request schema for updating a project."""

    name: Optional[str] = Field(None, description="Project name")
    external_url: Optional[str] = Field(
        None, description="Direct link to project in external system"
    )
    is_active: Optional[bool] = Field(None, description="Whether project is active")


class ProjectResponse(BaseModel):
    """Response schema for project."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    tool_integration_id: UUID
    external_key: str
    external_id: str
    name: str
    external_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectAccessCreate(BaseModel):
    """Request schema for granting project access."""

    user_id: UUID = Field(..., description="ID of user to grant access")
    access_level: ProjectAccessLevel = Field(
        ..., description="Access level: owner, admin, viewer"
    )


class ProjectAccessResponse(BaseModel):
    """Response schema for project access."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    access_level: str
    granted_by: Optional[UUID] = None
    granted_at: datetime
