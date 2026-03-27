"""API routes for project management."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminDependency
from app.database import get_db
from app.models.orm import Project, ToolIntegration, User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter()


# Dependency for database session
DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    db: DBSession,
    _admin: AdminDependency,
    user_id: Annotated[
        UUID | None, Query(description="Filter by owner user ID")
    ] = None,
    integration_id: Annotated[
        UUID | None, Query(description="Filter by integration ID")
    ] = None,
    is_active: Annotated[
        bool | None, Query(description="Filter by active status")
    ] = None,
):
    """List all projects available for sync."""
    query = select(Project)

    if user_id is not None:
        query = query.where(Project.owner_user_id == user_id)
    if integration_id is not None:
        query = query.where(Project.tool_integration_id == integration_id)
    if is_active is not None:
        query = query.where(Project.is_active == is_active)

    result = await db.execute(query)
    projects = result.scalars().all()
    return projects


@router.post(
    "/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED
)
async def create_project(
    db: DBSession,
    _admin: AdminDependency,
    project_data: ProjectCreate,
    user_id: Annotated[UUID, Query(description="User ID creating the project")],
):
    """Create a new project."""
    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Verify integration exists
    integration_result = await db.execute(
        select(ToolIntegration).where(
            ToolIntegration.id == project_data.tool_integration_id
        )
    )
    integration = integration_result.scalar_one_or_none()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {project_data.tool_integration_id} not found",
        )

    # Check if project with same external_id already exists for this integration
    existing_result = await db.execute(
        select(Project).where(
            Project.tool_integration_id == project_data.tool_integration_id,
            Project.external_id == project_data.external_id,
        )
    )
    if existing_result.scalar_one_or_none():
        ext_id = project_data.external_id
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with external_id {ext_id} already exists",
        )

    # Create project
    project = Project(
        owner_user_id=user_id,
        tool_integration_id=project_data.tool_integration_id,
        external_key=project_data.external_key,
        external_id=project_data.external_id,
        name=project_data.name,
        external_url=project_data.external_url,
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(db: DBSession, project_id: UUID, _admin: AdminDependency):
    """Get project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    return project


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    db: DBSession,
    project_id: UUID,
    _admin: AdminDependency,
    update_data: ProjectUpdate,
):
    """Update project sync settings."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Update fields if provided
    if update_data.name is not None:
        project.name = update_data.name
    if update_data.external_url is not None:
        project.external_url = update_data.external_url
    if update_data.is_active is not None:
        project.is_active = update_data.is_active

    await db.flush()
    await db.refresh(project)

    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(db: DBSession, project_id: UUID, _admin: AdminDependency):
    """Delete a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    await db.delete(project)
    return None
