"""API routes for metrics configuration and retrieval."""

import logging
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
logger = logging.getLogger(__name__)


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
    return DEFAULT_METRIC_CONFIG


@router.put("/metrics/config", response_model=MetricConfigResponse)
async def update_metrics_config(
    db: DBSession,
    config_data: MetricConfigUpdate,
    integration_id: Annotated[
        UUID | None, Query(description="Integration ID to update config for")
    ] = None,
):
    """Update metrics configuration."""
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
    """Get lead time metrics data from generic fact store."""
    # Build query over v_facts joined with issues for metadata
    # entity_id in lead_time is external_key
    base_query = """
        SELECT
            i.id AS issue_id,
            vf.entity_id AS issue_key,
            i.summary,
            dp.project_id,
            vf.project_key,
            p.name AS project_name,
            it.name AS issue_type,
            it.hierarchy_level,
            s.name AS status_name,
            sc.name AS status_category,
            i.jira_created_at AS created_at,
            vf.event_end_at AS resolved_at,
            vf.value AS lead_time_days,
            (vf.value * 24) AS lead_time_hours
        FROM metrics.v_facts vf
        JOIN metrics.dim_projects dp ON vf.project_agg_id = dp.id
        JOIN clean_jira.projects p ON dp.project_id = p.id
        JOIN clean_jira.issues i ON vf.entity_id = i.external_key AND p.id = i.project_id
        JOIN clean_jira.issue_types it ON i.type_id = it.id
        JOIN clean_jira.statuses s ON i.status_id = s.id
        JOIN clean_jira.status_categories sc ON s.category_id = sc.id
        WHERE vf.calc_code = 'lead_time_days'
          AND vf.slice_rule_name IS NULL
    """

    count_query = """
        SELECT COUNT(*)
        FROM metrics.v_facts vf
        JOIN metrics.dim_projects dp ON vf.project_agg_id = dp.id
        WHERE vf.calc_code = 'lead_time_days' AND vf.slice_rule_name IS NULL
    """

    avg_query = """
        SELECT
            AVG(value) as avg_days,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as median_days
        FROM metrics.v_facts vf
        JOIN metrics.dim_projects dp ON vf.project_agg_id = dp.id
        WHERE vf.calc_code = 'lead_time_days' AND vf.slice_rule_name IS NULL
    """

    params = {}

    if project_id:
        base_query += " AND dp.project_id = :project_id"
        count_query += " AND dp.project_id = :project_id"
        avg_query += " AND dp.project_id = :project_id"
        params["project_id"] = str(project_id)

    if issue_type:
        base_query += " AND it.name = :issue_type"
        # Sliced metrics would be in vf.slice_value if we queried with slice_rule_name IS NOT NULL
        # But here we filter the base rows by joined issue type for flexibility
        params["issue_type"] = issue_type

    if date_from:
        base_query += " AND vf.event_end_at >= :date_from"
        count_query += " AND vf.event_end_at >= :date_from"
        avg_query += " AND vf.event_end_at >= :date_from"
        params["date_from"] = date_from

    if date_to:
        base_query += " AND vf.event_end_at <= :date_to"
        count_query += " AND vf.event_end_at <= :date_to"
        avg_query += " AND vf.event_end_at <= :date_to"
        params["date_to"] = date_to

    base_query += " ORDER BY vf.event_end_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()

        count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
        total_count = (await db.execute(text(count_query), count_params)).scalar() or 0
        avg_row = (await db.execute(text(avg_query), count_params)).mappings().first()

        items = [
            LeadTimeItem(
                issue_id=row["issue_id"],
                issue_key=row["issue_key"],
                summary=row["summary"],
                project_id=row["project_id"],
                project_key=row["project_key"],
                project_name=row["project_name"],
                issue_type=row["issue_type"],
                hierarchy_level=row["hierarchy_level"],
                status_name=row["status_name"],
                status_category=row["status_category"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
                lead_time_days=float(row["lead_time_days"]),
                lead_time_hours=float(row["lead_time_hours"]),
            )
            for row in rows
        ]

        return LeadTimeResponse(
            items=items,
            total_count=total_count,
            avg_lead_time_days=(
                float(avg_row["avg_days"]) if avg_row and avg_row["avg_days"] else None
            ),
            median_lead_time_days=(
                float(avg_row["median_days"])
                if avg_row and avg_row["median_days"]
                else None
            ),
        )
    except Exception as err:
        logger.exception("Failed to query metrics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error querying metrics",
        ) from err


@router.get("/metrics/velocity", response_model=VelocityResponse)
async def get_velocity_metrics(
    db: DBSession,
    project_id: Annotated[UUID | None, Query()] = None,
    sprint_status: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query()] = 50,
    offset: Annotated[int, Query()] = 0,
):
    """Get velocity metrics data from generic fact store."""
    # Pivot velocity metrics from long format (calc_code)
    base_query = """
        WITH sprint_facts AS (
            SELECT
                vf.entity_id AS sprint_id,
                dp.project_id,
                vf.project_key,
                p.name AS project_name,
                s.external_id AS sprint_external_id,
                s.name AS sprint_name,
                s.state AS sprint_status,
                s.start_date,
                s.end_date,
                s.complete_date,
                MAX(CASE WHEN vf.calc_code = 'velocity_planned_sp' THEN vf.value END) AS planned_story_points,
                MAX(CASE WHEN vf.calc_code = 'velocity_completed_sp' THEN vf.value END) AS completed_story_points,
                MAX(CASE WHEN vf.calc_code = 'velocity_planned_count' THEN vf.value END) AS total_issues,
                MAX(CASE WHEN vf.calc_code = 'velocity_completed_count' THEN vf.value END) AS completed_issues
            FROM metrics.v_facts vf
            JOIN metrics.dim_projects dp ON vf.project_agg_id = dp.id
            JOIN clean_jira.projects p ON dp.project_id = p.id
            JOIN clean_jira.sprints s ON vf.entity_id = s.id::text
            WHERE vf.metric_code = 'velocity'
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
        )
        SELECT
            *,
            CASE WHEN planned_story_points > 0
                 THEN ROUND((completed_story_points * 100.0 / planned_story_points)::numeric, 2)
                 ELSE 0 END AS completion_rate_pct
        FROM sprint_facts
        WHERE 1=1
    """

    params = {}
    if project_id:
        base_query += " AND project_id = :project_id"
        params["project_id"] = str(project_id)
    if sprint_status:
        base_query += " AND sprint_status = :sprint_status"
        params["sprint_status"] = sprint_status
    if date_from:
        base_query += " AND start_date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        base_query += " AND end_date <= :date_to"
        params["date_to"] = date_to

    base_query += " ORDER BY start_date DESC NULLS LAST LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()

        items = [
            VelocityItem(
                sprint_id=row["sprint_id"],
                sprint_external_id=row["sprint_external_id"],
                sprint_name=row["sprint_name"],
                project_id=row["project_id"],
                project_key=row["project_key"],
                project_name=row["project_name"],
                sprint_status=row["sprint_status"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                complete_date=row["complete_date"],
                total_issues=int(row["total_issues"] or 0),
                completed_issues=int(row["completed_issues"] or 0),
                completion_rate_pct=float(row["completion_rate_pct"] or 0),
            )
            for row in rows
        ]
        return VelocityResponse(items=items, total_count=len(items))
    except Exception as err:
        logger.exception("Failed to query velocity metrics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error querying velocity metrics",
        ) from err


@router.get("/metrics/throughput", response_model=ThroughputResponse)
async def get_throughput_metrics(
    db: DBSession,
    project_id: Annotated[UUID | None, Query()] = None,
    issue_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query()] = 30,
    offset: Annotated[int, Query()] = 0,
):
    """Get throughput metrics data from generic fact store."""
    base_query = """
        SELECT
            vf.full_date AS resolved_date,
            dp.project_id,
            vf.project_key,
            p.name AS project_name,
            vf.slice_value AS issue_type,
            vf.value AS issues_completed,
            NULL AS hierarchy_level,
            NULL AS avg_lead_time_days
        FROM metrics.v_facts vf
        JOIN metrics.dim_projects dp ON vf.project_agg_id = dp.id
        JOIN clean_jira.projects p ON dp.project_id = p.id
        WHERE vf.calc_code = 'throughput_count'
    """

    params = {}
    if project_id:
        base_query += " AND dp.project_id = :project_id"
        params["project_id"] = str(project_id)
    if issue_type:
        base_query += " AND vf.slice_value = :issue_type"
        params["issue_type"] = issue_type
    else:
        base_query += " AND vf.slice_rule_name IS NULL"

    if date_from:
        base_query += " AND vf.full_date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        base_query += " AND vf.full_date <= :date_to"
        params["date_to"] = date_to

    base_query += " ORDER BY vf.full_date DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    try:
        result = await db.execute(text(base_query), params)
        rows = result.mappings().all()
        items = [
            ThroughputItem(
                resolved_date=row["resolved_date"],
                project_id=row["project_id"],
                project_key=row["project_key"],
                project_name=row["project_name"],
                issue_type=row["issue_type"] or "Total",
                hierarchy_level=None,
                issues_completed=int(row["issues_completed"]),
                avg_lead_time_days=None,
            )
            for row in rows
        ]
        total_completed = sum(item.issues_completed for item in items)
        return ThroughputResponse(
            items=items,
            total_count=len(items),
            total_issues_completed=total_completed,
        )
    except Exception as err:
        logger.exception("Failed to query throughput metrics")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error querying throughput metrics",
        ) from err


@router.post("/metrics/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_metrics(db: DBSession):
    """Trigger refresh of all metrics."""
    # No-op for standard views
    return {"message": "Metrics refresh initiated", "status": "success"}
