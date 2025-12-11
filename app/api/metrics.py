"""API routes for metrics configuration and retrieval."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.metrics import (
    LeadTimeItem,
    LeadTimeResponse,
    MetricConfigResponse,
    MetricConfigUpdate,
    ThroughputItem,
    ThroughputResponse,
    VelocityItem,
    VelocityResponse,
)

router = APIRouter()


# Dependency for database session
DBSession = Annotated[AsyncSession, Depends(get_db)]


# Default metric configuration
DEFAULT_METRIC_CONFIG = MetricConfigResponse(
    commitment_statuses=["In Progress", "In Review"],
    done_statuses=["Done", "Closed", "Resolved"],
    estimation_field="story_points",
    lead_time_start_status="Open",
    lead_time_end_status="Done",
)


@router.get("/metrics/config", response_model=MetricConfigResponse)
async def get_metrics_config(
    db: DBSession,
    integration_id: Annotated[
        UUID | None, Query(description="Integration ID for specific config")
    ] = None,
):
    """Get current metrics configuration."""
    # For now, return default config
    # In a full implementation, this would fetch from a metric_configs table
    return DEFAULT_METRIC_CONFIG


@router.put("/metrics/config", response_model=MetricConfigResponse)
async def update_metrics_config(
    db: DBSession,
    config_data: MetricConfigUpdate,
    integration_id: Annotated[
        UUID | None, Query(description="Integration ID to update config for")
    ] = None,
):
    """Update metrics configuration (commitment points, estimation fields, etc.)."""
    # For now, just return updated config merged with defaults
    # In a full implementation, this would persist to metric_configs table
    result = MetricConfigResponse(
        integration_id=integration_id,
        commitment_statuses=(
            config_data.commitment_statuses
            if config_data.commitment_statuses is not None
            else DEFAULT_METRIC_CONFIG.commitment_statuses
        ),
        done_statuses=(
            config_data.done_statuses
            if config_data.done_statuses is not None
            else DEFAULT_METRIC_CONFIG.done_statuses
        ),
        estimation_field=(
            config_data.estimation_field
            if config_data.estimation_field is not None
            else DEFAULT_METRIC_CONFIG.estimation_field
        ),
        lead_time_start_status=(
            config_data.lead_time_start_status
            if config_data.lead_time_start_status is not None
            else DEFAULT_METRIC_CONFIG.lead_time_start_status
        ),
        lead_time_end_status=(
            config_data.lead_time_end_status
            if config_data.lead_time_end_status is not None
            else DEFAULT_METRIC_CONFIG.lead_time_end_status
        ),
    )

    return result


@router.get("/metrics/lead-time", response_model=LeadTimeResponse)
async def get_lead_time_metrics(
    db: DBSession,
    project_id: Annotated[
        UUID | None, Query(description="Filter by project ID")
    ] = None,
    issue_type: Annotated[str | None, Query(description="Filter by issue type")] = None,
    date_from: Annotated[
        date | None, Query(description="Filter from date (resolved_at)")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Filter to date (resolved_at)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Limit results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset results")] = 0,
):
    """Get lead time metrics data from materialized view."""
    # Build query for mv_lead_time
    base_query = """
        SELECT
            issue_id,
            issue_key,
            summary,
            project_id,
            project_key,
            project_name,
            issue_type,
            hierarchy_level,
            status_name,
            status_category,
            jira_created_at as created_at,
            jira_resolved_at as resolved_at,
            lead_time_days,
            lead_time_hours
        FROM metrics.mv_lead_time
        WHERE 1=1
    """

    count_query = "SELECT COUNT(*) FROM metrics.mv_lead_time WHERE 1=1"
    avg_query = """
        SELECT
            AVG(lead_time_days) as avg_days,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lead_time_days) as median_days
        FROM metrics.mv_lead_time WHERE 1=1
    """

    params = {}

    if project_id:
        base_query += " AND project_id = :project_id"
        count_query += " AND project_id = :project_id"
        avg_query += " AND project_id = :project_id"
        params["project_id"] = str(project_id)

    if issue_type:
        base_query += " AND issue_type = :issue_type"
        count_query += " AND issue_type = :issue_type"
        avg_query += " AND issue_type = :issue_type"
        params["issue_type"] = issue_type

    if date_from:
        base_query += " AND jira_resolved_at >= :date_from"
        count_query += " AND jira_resolved_at >= :date_from"
        avg_query += " AND jira_resolved_at >= :date_from"
        params["date_from"] = date_from

    if date_to:
        base_query += " AND jira_resolved_at <= :date_to"
        count_query += " AND jira_resolved_at <= :date_to"
        avg_query += " AND jira_resolved_at <= :date_to"
        params["date_to"] = date_to

    base_query += " ORDER BY jira_resolved_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        # Execute queries
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()

        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        count_result = await db.execute(text(count_query), count_params)
        total_count = count_result.scalar() or 0

        avg_result = await db.execute(text(avg_query), count_params)
        avg_row = avg_result.mappings().first()

        items = [
            LeadTimeItem(
                issue_id=row["issue_id"],
                issue_key=row["issue_key"],
                summary=row["summary"],
                project_id=row["project_id"],
                project_key=row["project_key"],
                project_name=row["project_name"],
                issue_type=row["issue_type"],
                hierarchy_level=row.get("hierarchy_level"),
                status_name=row["status_name"],
                status_category=row["status_category"],
                created_at=row["created_at"],
                resolved_at=row.get("resolved_at"),
                lead_time_days=row.get("lead_time_days"),
                lead_time_hours=row.get("lead_time_hours"),
            )
            for row in rows
        ]

        avg_days = None
        median_days = None
        if avg_row:
            if avg_row.get("avg_days"):
                avg_days = float(avg_row["avg_days"])
            if avg_row.get("median_days"):
                median_days = float(avg_row["median_days"])

        return LeadTimeResponse(
            items=items,
            total_count=total_count,
            avg_lead_time_days=avg_days,
            median_lead_time_days=median_days,
        )

    except Exception as e:
        # If materialized view doesn't exist or is empty, return empty result
        if "does not exist" in str(e) or "relation" in str(e).lower():
            return LeadTimeResponse(
                items=[],
                total_count=0,
                avg_lead_time_days=None,
                median_lead_time_days=None,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching lead time metrics: {str(e)}",
        ) from e


@router.get("/metrics/velocity", response_model=VelocityResponse)
async def get_velocity_metrics(
    db: DBSession,
    project_id: Annotated[
        UUID | None, Query(description="Filter by project ID")
    ] = None,
    sprint_status: Annotated[
        str | None, Query(description="Filter by sprint status")
    ] = None,
    date_from: Annotated[
        date | None, Query(description="Filter from date (start_date)")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Filter to date (end_date)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Limit results")] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset results")] = 0,
):
    """Get velocity metrics data from materialized view."""
    # Build query for mv_velocity
    base_query = """
        SELECT
            sprint_id,
            sprint_external_id,
            sprint_name,
            project_id,
            project_key,
            project_name,
            sprint_status,
            start_date,
            end_date,
            complete_date,
            total_issues,
            completed_issues,
            completion_rate_pct
        FROM metrics.mv_velocity
        WHERE 1=1
    """

    count_query = "SELECT COUNT(*) FROM metrics.mv_velocity WHERE 1=1"
    avg_query = """
        SELECT
            AVG(completion_rate_pct) as avg_completion_rate,
            AVG(total_issues) as avg_issues
        FROM metrics.mv_velocity WHERE 1=1
    """

    params = {}

    if project_id:
        base_query += " AND project_id = :project_id"
        count_query += " AND project_id = :project_id"
        avg_query += " AND project_id = :project_id"
        params["project_id"] = str(project_id)

    if sprint_status:
        base_query += " AND sprint_status = :sprint_status"
        count_query += " AND sprint_status = :sprint_status"
        avg_query += " AND sprint_status = :sprint_status"
        params["sprint_status"] = sprint_status

    if date_from:
        base_query += " AND start_date >= :date_from"
        count_query += " AND start_date >= :date_from"
        avg_query += " AND start_date >= :date_from"
        params["date_from"] = date_from

    if date_to:
        base_query += " AND end_date <= :date_to"
        count_query += " AND end_date <= :date_to"
        avg_query += " AND end_date <= :date_to"
        params["date_to"] = date_to

    base_query += " ORDER BY start_date DESC NULLS LAST LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        # Execute queries
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()

        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        count_result = await db.execute(text(count_query), count_params)
        total_count = count_result.scalar() or 0

        avg_result = await db.execute(text(avg_query), count_params)
        avg_row = avg_result.mappings().first()

        items = [
            VelocityItem(
                sprint_id=row["sprint_id"],
                sprint_external_id=row["sprint_external_id"],
                sprint_name=row["sprint_name"],
                project_id=row["project_id"],
                project_key=row["project_key"],
                project_name=row["project_name"],
                sprint_status=row["sprint_status"],
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
                complete_date=row.get("complete_date"),
                total_issues=row["total_issues"],
                completed_issues=row["completed_issues"],
                completion_rate_pct=(
                    float(row["completion_rate_pct"])
                    if row.get("completion_rate_pct")
                    else 0.0
                ),
            )
            for row in rows
        ]

        avg_completion = None
        avg_issues = None
        if avg_row:
            if avg_row.get("avg_completion_rate"):
                avg_completion = float(avg_row["avg_completion_rate"])
            if avg_row.get("avg_issues"):
                avg_issues = float(avg_row["avg_issues"])

        return VelocityResponse(
            items=items,
            total_count=total_count,
            avg_completion_rate=avg_completion,
            avg_issues_per_sprint=avg_issues,
        )

    except Exception as e:
        # If materialized view doesn't exist or is empty, return empty result
        if "does not exist" in str(e) or "relation" in str(e).lower():
            return VelocityResponse(
                items=[],
                total_count=0,
                avg_completion_rate=None,
                avg_issues_per_sprint=None,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching velocity metrics: {str(e)}",
        ) from e


@router.get("/metrics/throughput", response_model=ThroughputResponse)
async def get_throughput_metrics(
    db: DBSession,
    project_id: Annotated[
        UUID | None, Query(description="Filter by project ID")
    ] = None,
    issue_type: Annotated[str | None, Query(description="Filter by issue type")] = None,
    date_from: Annotated[date | None, Query(description="Filter from date")] = None,
    date_to: Annotated[date | None, Query(description="Filter to date")] = None,
    limit: Annotated[int, Query(ge=1, le=365, description="Limit results (days)")] = 30,
    offset: Annotated[int, Query(ge=0, description="Offset results")] = 0,
):
    """Get throughput metrics data from materialized view."""
    # Build query for mv_throughput
    base_query = """
        SELECT
            resolved_date,
            project_id,
            project_key,
            project_name,
            issue_type,
            hierarchy_level,
            issues_completed,
            avg_lead_time_days
        FROM metrics.mv_throughput
        WHERE 1=1
    """

    count_query = "SELECT COUNT(*) FROM metrics.mv_throughput WHERE 1=1"
    sum_query = """
        SELECT
            SUM(issues_completed) as total_completed,
            AVG(issues_completed) as avg_daily
        FROM metrics.mv_throughput WHERE 1=1
    """

    params = {}

    if project_id:
        base_query += " AND project_id = :project_id"
        count_query += " AND project_id = :project_id"
        sum_query += " AND project_id = :project_id"
        params["project_id"] = str(project_id)

    if issue_type:
        base_query += " AND issue_type = :issue_type"
        count_query += " AND issue_type = :issue_type"
        sum_query += " AND issue_type = :issue_type"
        params["issue_type"] = issue_type

    if date_from:
        base_query += " AND resolved_date >= :date_from"
        count_query += " AND resolved_date >= :date_from"
        sum_query += " AND resolved_date >= :date_from"
        params["date_from"] = date_from

    if date_to:
        base_query += " AND resolved_date <= :date_to"
        count_query += " AND resolved_date <= :date_to"
        sum_query += " AND resolved_date <= :date_to"
        params["date_to"] = date_to

    base_query += " ORDER BY resolved_date DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        # Execute queries
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()

        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        count_result = await db.execute(text(count_query), count_params)
        total_count = count_result.scalar() or 0

        sum_result = await db.execute(text(sum_query), count_params)
        sum_row = sum_result.mappings().first()

        items = [
            ThroughputItem(
                resolved_date=row["resolved_date"],
                project_id=row["project_id"],
                project_key=row["project_key"],
                project_name=row["project_name"],
                issue_type=row["issue_type"],
                hierarchy_level=row.get("hierarchy_level"),
                issues_completed=row["issues_completed"],
                avg_lead_time_days=(
                    float(row["avg_lead_time_days"])
                    if row.get("avg_lead_time_days")
                    else None
                ),
            )
            for row in rows
        ]

        total_completed = 0
        avg_daily = None
        if sum_row:
            if sum_row.get("total_completed"):
                total_completed = int(sum_row["total_completed"])
            if sum_row.get("avg_daily"):
                avg_daily = float(sum_row["avg_daily"])

        return ThroughputResponse(
            items=items,
            total_count=total_count,
            total_issues_completed=total_completed,
            avg_daily_throughput=avg_daily,
        )

    except Exception as e:
        # If materialized view doesn't exist or is empty, return empty result
        if "does not exist" in str(e) or "relation" in str(e).lower():
            return ThroughputResponse(
                items=[],
                total_count=0,
                total_issues_completed=0,
                avg_daily_throughput=None,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching throughput metrics: {str(e)}",
        ) from e


@router.post("/metrics/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_metrics(db: DBSession):
    """Trigger refresh of all metrics materialized views."""
    try:
        await db.execute(text("SELECT metrics.refresh_all_views()"))
        return {"message": "Metrics refresh initiated", "status": "success"}
    except Exception as e:
        if "does not exist" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Metrics schema or views not found. Run migrations first.",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing metrics: {str(e)}",
        ) from e
