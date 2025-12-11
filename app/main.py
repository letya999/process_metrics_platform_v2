"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, integrations, metrics, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Process Metrics Platform",
    description="Admin API for managing data integrations and metrics configuration",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(integrations.router, prefix="/api/v1", tags=["Integrations"])
app.include_router(projects.router, prefix="/api/v1", tags=["Projects"])
app.include_router(metrics.router, prefix="/api/v1", tags=["Metrics"])
