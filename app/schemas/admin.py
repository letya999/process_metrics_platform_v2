"""Pydantic schemas for admin studio API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type literal
    expires_at: datetime
    user_id: UUID
    email: str


class AdminMeResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    is_admin: bool


class ProjectCatalogItem(BaseModel):
    project_id: UUID
    project_key: str
    project_name: str


class BoardCatalogItem(BaseModel):
    board_id: UUID
    board_name: str
    project_id: UUID


class BoardColumnCatalogItem(BaseModel):
    column_id: UUID
    board_id: UUID
    column_name: str
    position: int | None = None
    status_id: UUID | None = None
    status_name: str | None = None
    status_category: str | None = None


class StatusCatalogItem(BaseModel):
    status_id: UUID
    project_id: UUID
    status_name: str
    category: str | None = None


class FieldKeyCatalogItem(BaseModel):
    field_key_id: UUID
    project_id: UUID
    external_key: str
    name: str


class IssueTypeCatalogItem(BaseModel):
    issue_type_id: UUID
    project_id: UUID
    issue_type_name: str


class SchemaMapColumn(BaseModel):
    column_name: str
    data_type: str


class SchemaMapTable(BaseModel):
    table_name: str
    columns: list[SchemaMapColumn]


class SchemaRelation(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class SchemaMapResponse(BaseModel):
    tables: list[SchemaMapTable]
    relations: list[SchemaRelation]


class CalculationContract(BaseModel):
    calc_code: str
    metric_code: str
    unit_code: str
    uses_commitment_points: bool
    requires_unit_binding: str
    requires_commitment: str
    supports_slicing: bool
    required_settings_types: list[str]


class CommitmentRuleUpsert(BaseModel):
    id: UUID | None = None
    project_id: UUID | None = None
    board_id: UUID | None = None
    calc_code: str
    start_column_id: UUID
    end_column_id: UUID


class CommitmentRuleResponse(BaseModel):
    id: UUID
    project_id: UUID | None = None
    board_id: UUID | None = None
    calc_code: str
    target_calculation_name: str
    start_column_id: UUID
    end_column_id: UUID
    start_column_name_snapshot: str
    end_column_name_snapshot: str


class CalculationSettingUpsert(BaseModel):
    id: UUID | None = None
    project_id: UUID | None = None
    calc_code: str
    settings_type: str
    settings_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CalculationSettingResponse(BaseModel):
    id: UUID
    project_id: UUID | None = None
    calc_code: str
    metric_code: str
    settings_type: str
    settings_json: dict[str, Any]
    enabled: bool


class UnitBindingUpsert(BaseModel):
    project_id: UUID | None = None
    display_symbol: str | None = None
    source_field_id: UUID | None = None
    source_entity: str | None = None


class UnitBindingResponse(BaseModel):
    id: UUID
    project_id: UUID | None = None
    unit_code: str
    display_symbol: str
    source_field_id: UUID | None = None
    source_entity: str | None = None


class SliceRuleUpsert(BaseModel):
    id: UUID | None = None
    project_id: UUID | None = None
    rule_name: str
    target_definition_id: UUID | None = None
    target_definition_name: str | None = None
    source_table: str
    group_by_source_column: str
    enabled: bool = True


class SliceRuleResponse(BaseModel):
    id: UUID
    project_id: UUID | None = None
    rule_name: str
    target_definition_id: UUID | None = None
    target_definition_name: str | None = None
    source_table: str
    group_by_source_column: str
    enabled: bool


class ValidationIssue(BaseModel):
    project_id: UUID
    project_key: str
    severity: str
    code: str
    calc_code: str | None = None
    details: str


class ValidationResponse(BaseModel):
    issues: list[ValidationIssue]


class AdminJobItem(BaseModel):
    job_name: str
    title: str
    description: str


class AdminJobLaunchRequest(BaseModel):
    job_name: str


class AdminJobLaunchResponse(BaseModel):
    job_name: str
    run_id: str
    status: str


class AdminBatchJobLaunchRequest(BaseModel):
    job_names: list[str]


class AdminBatchJobLaunchItem(BaseModel):
    job_name: str
    run_id: str | None = None
    status: str
    error: str | None = None


class AdminRunStepStatus(BaseModel):
    step_key: str
    status: str | None = None
    start_time: float | None = None
    end_time: float | None = None


class AdminRunEvent(BaseModel):
    timestamp: float | None = None
    level: str | None = None
    event_type: str | None = None
    message: str | None = None


class AdminRunDetailsResponse(BaseModel):
    run_id: str
    status: str
    start_time: float | None = None
    end_time: float | None = None
    duration_seconds: float | None = None
    total_steps: int
    completed_steps: int
    failed_steps: int
    running_steps: int
    progress_pct: float
    steps: list[AdminRunStepStatus]
    errors: list[AdminRunEvent]
