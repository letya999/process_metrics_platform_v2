"""Async DB engine and session factory for dlt_jira_loader."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..utils.config import get_settings

# Lazy-initialized engine and session factory to avoid import-time side effects
_engine = None
_async_session_factory = None


def _ensure_engine_initialized() -> None:
    """Initialize the SQLAlchemy async engine once at runtime.

    This avoids reading settings at module import time (which breaks tests and
    containerized workers that expect env vars to be present before startup).
    """
    global _engine, _async_session_factory
    if _engine is None or _async_session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, future=True
        )
        _async_session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async session context manager with commit/rollback semantics."""
    _ensure_engine_initialized()
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
