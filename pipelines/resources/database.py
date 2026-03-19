"""Database resource for Dagster pipelines."""

import os
from functools import lru_cache

from dagster import ConfigurableResource
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@lru_cache(maxsize=4)
def _build_engine(conn_str: str) -> Engine:
    """Build and cache SQLAlchemy engines by connection string."""
    return create_engine(
        conn_str,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    )


class DatabaseResource(ConfigurableResource):
    """Database resource for connecting to PostgreSQL."""

    connection_string: str = ""

    def get_engine(self) -> Engine:
        """Get SQLAlchemy engine."""
        conn_str = self.connection_string or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/process_metrics",
        )
        return _build_engine(conn_str)


database_resource = DatabaseResource()
