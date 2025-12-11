"""SQLAlchemy ORM models for platform schema."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class IntegrationType(str, Enum):
    """Supported integration types."""

    JIRA_CLOUD = "jira_cloud"
    JIRA_SERVER = "jira_server"
    JIRA_DATACENTER = "jira_datacenter"
    LINEAR = "linear"
    ASANA = "asana"
    GITHUB = "github"
    GITLAB = "gitlab"


class ProjectAccessLevel(str, Enum):
    """Project access levels."""

    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"


class ExternalToolType(str, Enum):
    """External BI tool types."""

    METABASE = "metabase"
    SUPERSET = "superset"
    GRAFANA = "grafana"


class ExternalToolRole(str, Enum):
    """User roles in external BI tools."""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base):
    """User model for platform authentication."""

    __tablename__ = "users"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_password_change: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Relationships
    tool_integrations: Mapped[list["ToolIntegration"]] = relationship(
        "ToolIntegration", back_populates="user"
    )
    owned_projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="owner"
    )
    project_access: Mapped[list["ProjectAccess"]] = relationship(
        "ProjectAccess", back_populates="user", foreign_keys="ProjectAccess.user_id"
    )


class IntegrationTypeModel(Base):
    """Reference table for integration types."""

    __tablename__ = "integration_types"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    tool_integrations: Mapped[list["ToolIntegration"]] = relationship(
        "ToolIntegration", back_populates="integration_type"
    )


class ToolIntegration(Base):
    """User connections to external systems with API credentials."""

    __tablename__ = "tool_integrations"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("platform.users.id", ondelete="CASCADE"), nullable=False
    )
    integration_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("platform.integration_types.id"),
        nullable=False,
    )

    # Connection parameters
    instance_url: Mapped[Optional[str]] = mapped_column(Text)
    user_email: Mapped[Optional[str]] = mapped_column(Text)

    # Secure token storage (preferred)
    secret_reference: Mapped[Optional[str]] = mapped_column(Text)
    secret_provider: Mapped[Optional[str]] = mapped_column(Text, default="env")

    # Fallback insecure storage (deprecated, dev/test only)
    api_token_unsafe: Mapped[Optional[str]] = mapped_column(Text)

    api_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    api_token_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[Optional[str]] = mapped_column(Text)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tool_integrations")
    integration_type: Mapped["IntegrationTypeModel"] = relationship(
        "IntegrationTypeModel", back_populates="tool_integrations"
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="tool_integration"
    )


class Project(Base):
    """Projects imported from external systems."""

    __tablename__ = "projects"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("platform.users.id", ondelete="CASCADE"), nullable=False
    )
    tool_integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("platform.tool_integrations.id", ondelete="CASCADE"),
        nullable=False,
    )

    external_key: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    external_url: Mapped[Optional[str]] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_projects")
    tool_integration: Mapped["ToolIntegration"] = relationship(
        "ToolIntegration", back_populates="projects"
    )
    access_list: Mapped[list["ProjectAccess"]] = relationship(
        "ProjectAccess", back_populates="project"
    )


class ProjectAccess(Base):
    """Granular project access control."""

    __tablename__ = "project_access"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("platform.projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("platform.users.id", ondelete="CASCADE"), nullable=False
    )
    access_level: Mapped[str] = mapped_column(String(20), nullable=False)

    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("platform.users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="access_list")
    user: Mapped["User"] = relationship(
        "User", back_populates="project_access", foreign_keys=[user_id]
    )
    granter: Mapped[Optional["User"]] = relationship("User", foreign_keys=[granted_by])


class AuditLog(Base):
    """Audit trail of all user actions."""

    __tablename__ = "audit_log"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("platform.users.id", ondelete="SET NULL")
    )

    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")


class Pipeline(Base):
    """Pipeline definitions for orchestration."""

    __tablename__ = "pipelines"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_cron: Mapped[Optional[str]] = mapped_column(Text)

    prefect_flow_id: Mapped[Optional[str]] = mapped_column(Text)
    prefect_deployment_id: Mapped[Optional[str]] = mapped_column(Text)

    config: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="pipeline"
    )


class PipelineRun(Base):
    """Pipeline execution history."""

    __tablename__ = "pipeline_runs"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("platform.pipelines.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("platform.projects.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)

    prefect_flow_run_id: Mapped[Optional[str]] = mapped_column(Text)
    prefect_state: Mapped[Optional[dict]] = mapped_column(JSONB)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column()

    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_trace: Mapped[Optional[str]] = mapped_column(Text)

    metrics: Mapped[Optional[dict]] = mapped_column(JSONB)
    config: Mapped[Optional[dict]] = mapped_column(JSONB)

    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("platform.users.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="runs")
    project: Mapped[Optional["Project"]] = relationship("Project")
    triggered_by_user: Mapped[Optional["User"]] = relationship("User")
    tasks: Mapped[list["PipelineTask"]] = relationship(
        "PipelineTask", back_populates="pipeline_run"
    )


class PipelineTask(Base):
    """Individual task execution within pipeline runs."""

    __tablename__ = "pipeline_tasks"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("platform.pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)

    prefect_task_run_id: Mapped[Optional[str]] = mapped_column(Text)
    prefect_state: Mapped[Optional[dict]] = mapped_column(JSONB)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column()

    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_trace: Mapped[Optional[str]] = mapped_column(Text)

    metrics: Mapped[Optional[dict]] = mapped_column(JSONB)
    input_params: Mapped[Optional[dict]] = mapped_column(JSONB)
    output_result: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship(
        "PipelineRun", back_populates="tasks"
    )
