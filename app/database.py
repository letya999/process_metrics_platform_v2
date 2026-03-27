"""Database configuration and session management."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _to_async_database_url(database_url: str) -> str:
    """Convert sync PostgreSQL URL to asyncpg URL when needed."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://")
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://")
    return database_url


def get_database_url() -> str:
    """Read database URL from environment."""
    return os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/process_metrics"
    )


def get_async_database_url() -> str:
    """Get async database URL from environment."""
    return _to_async_database_url(get_database_url())


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create and cache async engine."""
    return create_async_engine(
        get_async_database_url(),
        echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Create and cache async session factory."""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def reset_db_state_for_tests() -> None:
    """Clear cached DB objects to allow env-driven reinitialization in tests."""
    if hasattr(get_session_maker, "cache_clear"):
        get_session_maker.cache_clear()
    if hasattr(get_engine, "cache_clear"):
        get_engine.cache_clear()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session."""
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for getting async database session."""
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database connection (called on startup)."""
    # Test connection
    async with get_engine().begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Close database connection (called on shutdown)."""
    await get_engine().dispose()
