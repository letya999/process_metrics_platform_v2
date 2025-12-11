"""API routes for managing data source integrations."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/integrations")
async def list_integrations():
    """List all configured integrations."""
    # TODO: Implement with database
    return {"integrations": []}


@router.post("/integrations")
async def create_integration():
    """Create a new integration."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: int):
    """Get integration by ID."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/integrations/{integration_id}")
async def update_integration(integration_id: int):
    """Update an integration."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/integrations/{integration_id}")
async def delete_integration(integration_id: int):
    """Delete an integration."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/integrations/{integration_id}/sync")
async def trigger_sync(integration_id: int):
    """Trigger a sync for an integration via Dagster."""
    # TODO: Implement with DagsterClient
    raise HTTPException(status_code=501, detail="Not implemented")
