"""API routes for metrics configuration."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/metrics/config")
async def get_metrics_config():
    """Get current metrics configuration."""
    # TODO: Implement with database
    return {"config": {}}


@router.put("/metrics/config")
async def update_metrics_config():
    """Update metrics configuration (commitment points, estimation fields, etc.)."""
    # TODO: Implement with database
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/metrics/lead-time")
async def get_lead_time_metrics():
    """Get lead time metrics data."""
    # TODO: Implement with database views
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/metrics/velocity")
async def get_velocity_metrics():
    """Get velocity metrics data."""
    # TODO: Implement with database views
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/metrics/throughput")
async def get_throughput_metrics():
    """Get throughput metrics data."""
    # TODO: Implement with database views
    raise HTTPException(status_code=501, detail="Not implemented")
