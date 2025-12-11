"""Database resource for Dagster pipelines."""

import os

from dagster import ConfigurableResource
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


class DatabaseResource(ConfigurableResource):
    """Database resource for connecting to PostgreSQL."""

    connection_string: str = ""

    def get_engine(self) -> Engine:
        """Get SQLAlchemy engine."""
        conn_str = self.connection_string or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/process_metrics",
        )
        return create_engine(conn_str)


database_resource = DatabaseResource()
