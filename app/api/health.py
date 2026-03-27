"""Health check endpoint."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import get_db_context

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness endpoint for load balancers and monitoring."""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check():
    """Readiness endpoint that validates database connectivity."""
    try:
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "reason": "database_unavailable"},
        )
    return {"status": "healthy"}
