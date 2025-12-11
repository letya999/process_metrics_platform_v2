"""API routes for project management."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/projects")
async def list_projects():
    """List all projects available for sync."""
    # TODO: Implement with database
    return {"projects": []}


@router.get("/projects/{project_id}")
async def get_project(project_id: int):
    """Get project by ID."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/projects/{project_id}")
async def update_project(project_id: int):
    """Update project sync settings."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")
