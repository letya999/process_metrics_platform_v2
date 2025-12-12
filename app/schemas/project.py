"""Pydantic schemas for project API endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    owner_user_id: Optional[UUID] = None
    tool_integration_id: Optional[UUID] = None
    external_key: str
    external_id: str
    name: str
    external_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
