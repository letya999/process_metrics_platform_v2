"""Pydantic schemas for metrics API endpoints."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetricConfigUpdate(BaseModel):
    """Request schema for updating metric configuration."""

    commitment_statuses: Optional[list[str]] = Field(
        None, description="Statuses that mark commitment"
    )
    done_statuses: Optional[list[str]] = Field(
        None, description="Statuses that mark completion"
    )
    estimation_field: Optional[str] = Field(
        None, description="Field used for story points estimation"
    )
    lead_time_start_status: Optional[str] = Field(
        None, description="Status that marks lead time start"
    )
    lead_time_end_status: Optional[str] = Field(
        None, description="Status that marks lead time end"
    )


class MetricConfigResponse(BaseModel):
    """Response schema for metric configuration."""

    integration_id: Optional[UUID] = None
    commitment_statuses: list[str] = Field(default_factory=list)
    done_statuses: list[str] = Field(default_factory=list)
    estimation_field: Optional[str] = None
    lead_time_start_status: Optional[str] = None
    lead_time_end_status: Optional[str] = None


class LeadTimeItem(BaseModel):
    """Individual lead time record."""

    model_config = ConfigDict(from_attributes=True)

    issue_id: UUID
    issue_key: str
    summary: str
    project_id: UUID
    project_key: str
    project_name: str
    issue_type: str
    hierarchy_level: Optional[str] = None
    status_name: str
    status_category: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    lead_time_days: Optional[float] = None
    lead_time_hours: Optional[float] = None


class LeadTimeResponse(BaseModel):
    """Response schema for lead time metrics."""

    items: list[LeadTimeItem]
    total_count: int
    avg_lead_time_days: Optional[float] = None
    median_lead_time_days: Optional[float] = None


class VelocityItem(BaseModel):
    """Individual velocity record (per sprint)."""

    model_config = ConfigDict(from_attributes=True)

    sprint_id: UUID
    sprint_external_id: str
    sprint_name: str
    project_id: UUID
    project_key: str
    project_name: str
    sprint_status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    complete_date: Optional[date] = None
    total_issues: int
    completed_issues: int
    completion_rate_pct: float


class VelocityResponse(BaseModel):
    """Response schema for velocity metrics."""

    items: list[VelocityItem]
    total_count: int
    avg_completion_rate: Optional[float] = None
    avg_issues_per_sprint: Optional[float] = None


class ThroughputItem(BaseModel):
    """Individual throughput record (per day)."""

    model_config = ConfigDict(from_attributes=True)

    resolved_date: date
    project_id: UUID
    project_key: str
    project_name: str
    issue_type: str
    hierarchy_level: Optional[str] = None
    issues_completed: int
    avg_lead_time_days: Optional[float] = None


class ThroughputResponse(BaseModel):
    """Response schema for throughput metrics."""

    items: list[ThroughputItem]
    total_count: int
    total_issues_completed: int
    avg_daily_throughput: Optional[float] = None
