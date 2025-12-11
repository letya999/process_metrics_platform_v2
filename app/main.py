"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, integrations, metrics, projects
from app.database import close_db, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting Process Metrics Platform API")
    try:
        await init_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
        # Continue without DB for health checks

    yield

    # Shutdown
    logger.info("Shutting down Process Metrics Platform API")
    try:
        await close_db()
        logger.info("Database connection closed")
    except Exception as e:
        logger.warning(f"Error closing database connection: {e}")


app = FastAPI(
    title="Process Metrics Platform",
    description="Admin API for managing data integrations and metrics configuration",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to docs."""
    return {
        "message": "Process Metrics Platform API",
        "docs": "/docs",
        "health": "/health",
    }
