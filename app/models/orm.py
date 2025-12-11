"""SQLAlchemy ORM models for platform schema."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class IntegrationType(str, Enum):
    """Supported integration types."""

    JIRA = "jira"
    GITLAB = "gitlab"
    SLACK = "slack"


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"
    __table_args__ = {"schema": "platform"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    integrations: Mapped[list["Integration"]] = relationship(
        "Integration", back_populates="created_by_user"
    )


class Integration(Base):
    """Integration configuration for data sources (Jira, GitLab, etc.)."""

    __tablename__ = "integrations"
    __table_args__ = {"schema": "platform"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # jira, gitlab, etc.
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    credentials: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # Encrypted in production
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sync_status: Mapped[Optional[str]] = mapped_column(String(50))  # success, failed, running
    config: Mapped[Optional[dict]] = mapped_column(JSONB)  # Additional configuration
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("platform.users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="integrations"
    )
    metric_configs: Mapped[list["MetricConfig"]] = relationship(
        "MetricConfig", back_populates="integration"
    )


class MetricConfig(Base):
    """Metric configuration for an integration."""

    __tablename__ = "metric_configs"
    __table_args__ = {"schema": "platform"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    integration_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("platform.integrations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Jira-specific configuration
    commitment_statuses: Mapped[Optional[list]] = mapped_column(
        JSONB
    )  # Statuses that mark commitment
    done_statuses: Mapped[Optional[list]] = mapped_column(
        JSONB
    )  # Statuses that mark completion
    estimation_field: Mapped[Optional[str]] = mapped_column(
        String(100)
    )  # Story points field
    lead_time_start_status: Mapped[Optional[str]] = mapped_column(String(100))
    lead_time_end_status: Mapped[Optional[str]] = mapped_column(String(100))

    # General configuration
    config: Mapped[Optional[dict]] = mapped_column(JSONB)  # Additional configuration
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    integration: Mapped["Integration"] = relationship(
        "Integration", back_populates="metric_configs"
    )
