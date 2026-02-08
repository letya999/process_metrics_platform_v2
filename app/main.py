"""FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import health, integrations, metrics, projects
from app.database import close_db, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)


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

# Set up Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Define allowed origins
ALLOWED_ORIGINS = [
    "https://metrics.your-domain.com",
    "https://dagster.your-domain.com",
    "https://api.your-domain.com",
]

# Add localhost for development environments
if os.getenv("ENVIRONMENT") != "production":
    ALLOWED_ORIGINS.extend(
        [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000",
        ]
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
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
