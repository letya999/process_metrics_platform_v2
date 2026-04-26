"""Admin API for metrics configuration studio."""

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminDependency
from app.database import get_db
from app.limiter import limiter
from app.schemas.admin import (
    AdminBatchJobLaunchItem,
    AdminBatchJobLaunchRequest,
    AdminJobItem,
    AdminJobLaunchRequest,
    AdminJobLaunchResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminMeResponse,
    AdminRunDetailsResponse,
    AdminRunEvent,
    AdminRunStepStatus,
    BoardCatalogItem,
    BoardColumnCatalogItem,
    CalculationContract,
    CalculationSettingResponse,
    CalculationSettingUpsert,
    CommitmentRuleResponse,
    CommitmentRuleUpsert,
    FieldKeyCatalogItem,
    IssueTypeCatalogItem,
    ProjectCatalogItem,
    SchemaMapColumn,
    SchemaMapResponse,
    SchemaMapTable,
    SchemaRelation,
    SliceRuleResponse,
    SliceRuleUpsert,
    StatusCatalogItem,
    UnitBindingResponse,
    UnitBindingUpsert,
    ValidationIssue,
    ValidationResponse,
)
from app.services.admin_auth import (
    AdminSession,
    create_access_token,
    get_session,
    hash_password,
    parse_bearer_token,
    revoke_token,
    save_session,
    verify_password,
)
from app.services.dagster_client import DagsterClient
from app.services.google_auth import (
    build_google_redirect_url,
    exchange_code_for_email,
    verify_state_and_get_return_to,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])
DBSession = Annotated[AsyncSession, Depends(get_db)]

REQUIRED_SETTINGS_BY_CALC: dict[str, list[str]] = {
    "flow_active_days": ["flow_status_categories"],
    "flow_wait_days": ["flow_status_categories"],
    "flow_efficiency_pct": ["flow_status_categories"],
    "ttm_days": ["issue_type_filter"],
    "daily_status_entry_count": ["target_status"],
    "field_change_count": ["field_key_id"],
    "defect_density_by_type": ["defect_density_types"],
    "cancellation_rate_weekly": ["cancelled_status_ids"],
    "field_value_sprint_pct": ["field_value_match"],
}

SUPPORTED_ADMIN_JOBS: list[dict[str, str]] = [
    {
        "job_name": "jira_sync_job",
        "title": "Jira Sync (Raw -> Clean -> Metrics)",
        "description": "Run full Jira ETL chain and metrics refresh.",
    },
    {
        "job_name": "jira_raw_job",
        "title": "Jira Raw",
        "description": "Load raw Jira data only.",
    },
    {
        "job_name": "jira_clean_job",
        "title": "Jira Clean",
        "description": "Transform raw Jira data to clean layer only.",
    },
    {
        "job_name": "metrics_refresh_job",
        "title": "Metrics Refresh",
        "description": "Recalculate metrics layer only.",
    },
]

METRIC_RECALC_JOBS: list[dict[str, str]] = [
    {
        "job_name": "recalculate_lead_time_job",
        "title": "Lead Time",
        "description": "Recalculate Lead Time facts and refresh view",
    },
    {
        "job_name": "recalculate_velocity_job",
        "title": "Velocity",
        "description": "Recalculate Velocity facts and refresh view",
    },
    {
        "job_name": "recalculate_throughput_job",
        "title": "Throughput",
        "description": "Recalculate Throughput facts and refresh view",
    },
    {
        "job_name": "recalculate_cfd_job",
        "title": "CFD",
        "description": "Recalculate Cumulative Flow Diagram facts",
    },
    {
        "job_name": "recalculate_backlog_growth_job",
        "title": "Backlog Growth",
        "description": "Recalculate Backlog Growth facts",
    },
    {
        "job_name": "recalculate_time_to_market_job",
        "title": "Time to Market",
        "description": "Recalculate Time to Market facts",
    },
    {
        "job_name": "recalculate_sprint_health_job",
        "title": "Sprint Health",
        "description": "Recalculate sprint health metrics (scope changes, burndown, spillover)",
    },
    {
        "job_name": "recalculate_flow_dynamics_job",
        "title": "Flow Dynamics",
        "description": "Recalculate flow dynamics metrics (daily status entry, field changes)",
    },
    {
        "job_name": "recalculate_quality_metrics_job",
        "title": "Quality Metrics",
        "description": "Recalculate quality metrics (defect density, backflow rate)",
    },
    {
        "job_name": "recalculate_delivery_metrics_job",
        "title": "Delivery Metrics",
        "description": "Recalculate delivery metrics (release burnup scope/done)",
    },
    {
        "job_name": "recalculate_cycle_time_extended_job",
        "title": "Cycle Time Extended",
        "description": "Recalculate extended cycle time metrics (lifetime, custom CT, epic delivery)",
    },
    {
        "job_name": "recalculate_waste_metrics_job",
        "title": "Waste Metrics",
        "description": "Recalculate waste metrics (cancellation rate)",
    },
    {
        "job_name": "recalculate_estimation_metrics_job",
        "title": "Estimation Metrics",
        "description": "Recalculate estimation metrics (estimate volatility)",
    },
    {
        "job_name": "recalculate_input_flow_job",
        "title": "Input Flow",
        "description": "Recalculate input flow metrics (weekly issue intake)",
    },
    {
        "job_name": "recalculate_aging_extended_job",
        "title": "Aging Extended",
        "description": "Recalculate extended aging metrics (blocked time, stale days)",
    },
]


async def _get_current_admin(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AdminSession:
    token = parse_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    session = get_session(token)
    if not session or not session.is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return session


@router.post("/auth/login", response_model=AdminLoginResponse)
@limiter.limit("10/minute")
async def admin_login(request: Request, payload: AdminLoginRequest, db: DBSession):
    row = (
        (
            await db.execute(
                text(
                    """
                SELECT id, email, display_name, password_hash, is_admin, is_active
                FROM platform.users
                WHERE email = :email
                """
                ),
                {"email": payload.email},
            )
        )
        .mappings()
        .first()
    )

    if not row or not row["is_active"] or not row["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    is_valid, needs_rehash = verify_password(payload.password, row["password_hash"])
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if needs_rehash:
        new_hash = hash_password(payload.password)
        await db.execute(
            text("UPDATE platform.users SET password_hash = :h WHERE id = :id"),
            {"h": new_hash, "id": str(row["id"])},
        )

    session = AdminSession(
        user_id=str(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_admin=True,
        expires_at=datetime.now(UTC),
    )
    try:
        token, expires_at = create_access_token(session)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin auth is not configured",
        ) from exc
    save_session(token, session)

    return AdminLoginResponse(
        access_token=token,
        expires_at=expires_at,
        user_id=row["id"],
        email=row["email"],
    )


@router.get("/auth/me", response_model=AdminMeResponse)
async def admin_me(admin: AdminDependency):
    return AdminMeResponse(
        user_id=UUID(admin.user_id),
        email=admin.email,
        display_name=admin.display_name,
        is_admin=admin.is_admin,
    )


@router.post("/auth/logout")
async def admin_logout(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
):
    token = parse_bearer_token(authorization)
    if token:
        revoke_token(token)
    return {"status": "ok"}


@router.get("/auth/google/redirect")
@limiter.limit("20/minute")
async def admin_google_redirect(request: Request, return_to: str | None = None):
    """Redirect to Google OAuth consent screen."""
    admin_ui_url = os.getenv("ADMIN_UI_URL", "http://localhost:8501")
    safe_return_to = return_to or admin_ui_url
    try:
        url = build_google_redirect_url(safe_return_to)
    except HTTPException:
        raise
    return RedirectResponse(url, status_code=302)


@router.get("/auth/google/callback")
@limiter.limit("20/minute")
async def admin_google_callback(
    request: Request,
    db: DBSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Handle Google OAuth callback, issue JWT, redirect to Streamlit."""
    admin_ui_url = os.getenv("ADMIN_UI_URL", "http://localhost:8501")

    # Google returned an error
    if error or not code or not state:
        return RedirectResponse(
            f"{admin_ui_url}?error=google_auth_cancelled", status_code=302
        )

    # Verify state (CSRF protection)
    return_to = verify_state_and_get_return_to(state)
    if not return_to:
        return RedirectResponse(
            f"{admin_ui_url}?error=google_auth_invalid_state", status_code=302
        )

    # Exchange code for email
    email = await exchange_code_for_email(code)
    if not email:
        return RedirectResponse(
            f"{return_to}?error=google_auth_failed", status_code=302
        )

    # Look up admin user by email
    row = (
        (
            await db.execute(
                text(
                    """
                SELECT id, email, display_name, is_admin, is_active
                FROM platform.users
                WHERE email = :email
                """
                ),
                {"email": email},
            )
        )
        .mappings()
        .first()
    )

    if not row or not row["is_active"] or not row["is_admin"]:
        return RedirectResponse(
            f"{return_to}?error=google_auth_not_authorized", status_code=302
        )

    # Issue JWT (same flow as password login)
    session = AdminSession(
        user_id=str(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_admin=True,
        expires_at=datetime.now(UTC),
    )
    try:
        token, _ = create_access_token(session)
    except RuntimeError:
        return RedirectResponse(
            f"{return_to}?error=google_auth_server_error", status_code=302
        )

    return RedirectResponse(f"{return_to}?token={token}", status_code=302)


@router.get("/catalog/projects", response_model=list[ProjectCatalogItem])
async def catalog_projects(
    db: DBSession,
    _admin: AdminDependency,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT p.id AS project_id, p.external_key AS project_key, p.name AS project_name
                FROM clean_jira.projects p
                ORDER BY p.external_key
                """
                )
            )
        )
        .mappings()
        .all()
    )
    return [ProjectCatalogItem(**row) for row in rows]


@router.get("/catalog/boards", response_model=list[BoardCatalogItem])
async def catalog_boards(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT id AS board_id, name AS board_name, project_id
                FROM clean_jira.boards
                WHERE project_id = :project_id
                ORDER BY name
                """
                ),
                {"project_id": str(project_id)},
            )
        )
        .mappings()
        .all()
    )
    return [BoardCatalogItem(**row) for row in rows]


@router.get("/catalog/board-columns", response_model=list[BoardColumnCatalogItem])
async def catalog_board_columns(
    db: DBSession,
    _admin: AdminDependency,
    board_id: UUID,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT
                    bc.id AS column_id,
                    bc.board_id,
                    bc.name AS column_name,
                    bc.position,
                    bcs.status_id,
                    s.name AS status_name,
                    s.category AS status_category
                FROM clean_jira.board_columns bc
                LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
                LEFT JOIN clean_jira.issue_statuses s ON s.id = bcs.status_id
                WHERE bc.board_id = :board_id
                ORDER BY bc.position, bc.name
                """
                ),
                {"board_id": str(board_id)},
            )
        )
        .mappings()
        .all()
    )
    return [BoardColumnCatalogItem(**row) for row in rows]


@router.get("/catalog/statuses", response_model=list[StatusCatalogItem])
async def catalog_statuses(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT id AS status_id, project_id, name AS status_name, category
                FROM clean_jira.issue_statuses
                WHERE project_id = :project_id
                ORDER BY name
                """
                ),
                {"project_id": str(project_id)},
            )
        )
        .mappings()
        .all()
    )
    return [StatusCatalogItem(**row) for row in rows]


@router.get("/catalog/field-keys", response_model=list[FieldKeyCatalogItem])
async def catalog_field_keys(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT id AS field_key_id, project_id, external_key, name
                FROM clean_jira.field_keys
                WHERE project_id = :project_id
                ORDER BY external_key
                """
                ),
                {"project_id": str(project_id)},
            )
        )
        .mappings()
        .all()
    )
    return [FieldKeyCatalogItem(**row) for row in rows]


@router.get("/catalog/issue-types", response_model=list[IssueTypeCatalogItem])
async def catalog_issue_types(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT id AS issue_type_id, project_id, name AS issue_type_name
                FROM clean_jira.issue_types
                WHERE project_id = :project_id
                ORDER BY name
                """
                ),
                {"project_id": str(project_id)},
            )
        )
        .mappings()
        .all()
    )
    return [IssueTypeCatalogItem(**row) for row in rows]


@router.get("/catalog/clean-jira-schema-map", response_model=SchemaMapResponse)
async def catalog_clean_jira_schema_map(
    db: DBSession,
    _admin: AdminDependency,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'clean_jira'
                ORDER BY table_name, ordinal_position
                """
                )
            )
        )
        .mappings()
        .all()
    )

    grouped: dict[str, list[SchemaMapColumn]] = {}
    for row in rows:
        grouped.setdefault(row["table_name"], []).append(
            SchemaMapColumn(column_name=row["column_name"], data_type=row["data_type"])
        )
    tables = [
        SchemaMapTable(table_name=table_name, columns=columns)
        for table_name, columns in grouped.items()
    ]
    relation_rows = (
        (
            await db.execute(
                text(
                    """
                SELECT
                    tc.table_name AS from_table,
                    kcu.column_name AS from_column,
                    ccu.table_name AS to_table,
                    ccu.column_name AS to_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'clean_jira'
                ORDER BY tc.table_name, kcu.column_name
                """
                )
            )
        )
        .mappings()
        .all()
    )
    relations = [SchemaRelation(**row) for row in relation_rows]
    return SchemaMapResponse(tables=tables, relations=relations)


@router.get("/contracts/catalog", response_model=list[CalculationContract])
async def contract_catalog(
    db: DBSession,
    _admin: AdminDependency,
):
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT d.metric_code, c.calc_code, c.unit_code, c.uses_commitment_points
                FROM metrics.calculations c
                JOIN metrics.definitions d ON d.id = c.definition_id
                ORDER BY d.metric_code, c.calc_code
                """
                )
            )
        )
        .mappings()
        .all()
    )

    contracts: list[CalculationContract] = []
    for row in rows:
        unit_code = row["unit_code"]
        calc_code = row["calc_code"]
        requires_unit_binding = "required" if unit_code == "story_points" else "none"
        requires_commitment = "required" if row["uses_commitment_points"] else "none"
        required_settings = REQUIRED_SETTINGS_BY_CALC.get(calc_code, [])
        contracts.append(
            CalculationContract(
                calc_code=calc_code,
                metric_code=row["metric_code"],
                unit_code=unit_code,
                uses_commitment_points=bool(row["uses_commitment_points"]),
                requires_unit_binding=requires_unit_binding,
                requires_commitment=requires_commitment,
                supports_slicing=True,
                required_settings_types=required_settings,
            )
        )
    return contracts


@router.get("/commitment-rules", response_model=list[CommitmentRuleResponse])
async def list_commitment_rules(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID | None = None,
    board_id: UUID | None = None,
    calc_code: str | None = None,
):
    query = """
        SELECT cr.id, cr.project_id, cr.board_id, c.calc_code,
               cr.target_calculation_name,
               cr.start_column_id, cr.end_column_id,
               cr.start_column_name_snapshot, cr.end_column_name_snapshot
        FROM metrics.commitment_rules cr
        JOIN metrics.calculations c ON c.id = cr.target_calculation_id
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if project_id:
        query += " AND cr.project_id = :project_id"
        params["project_id"] = str(project_id)
    if board_id:
        query += " AND cr.board_id = :board_id"
        params["board_id"] = str(board_id)
    if calc_code:
        query += " AND c.calc_code = :calc_code"
        params["calc_code"] = calc_code
    query += " ORDER BY c.calc_code, cr.project_id, cr.board_id"

    rows = (await db.execute(text(query), params)).mappings().all()
    return [CommitmentRuleResponse(**row) for row in rows]


@router.post("/commitment-rules", response_model=CommitmentRuleResponse)
async def upsert_commitment_rule(
    payload: CommitmentRuleUpsert,
    db: DBSession,
    _admin: AdminDependency,
):
    calc = (
        (
            await db.execute(
                text(
                    "SELECT id, calc_code FROM metrics.calculations WHERE calc_code = :calc_code"
                ),
                {"calc_code": payload.calc_code},
            )
        )
        .mappings()
        .first()
    )
    if not calc:
        raise HTTPException(status_code=404, detail="Calculation not found")

    col_rows = (
        (
            await db.execute(
                text(
                    """
                SELECT id, name FROM clean_jira.board_columns
                WHERE id IN (:start_id, :end_id)
                """
                ),
                {
                    "start_id": str(payload.start_column_id),
                    "end_id": str(payload.end_column_id),
                },
            )
        )
        .mappings()
        .all()
    )
    names = {str(r["id"]): r["name"] for r in col_rows}

    if payload.id:
        sql = text(
            """
            UPDATE metrics.commitment_rules
            SET project_id=:project_id,
                board_id=:board_id,
                target_calculation_id=:target_calculation_id,
                target_calculation_name=:target_calculation_name,
                start_column_id=:start_column_id,
                end_column_id=:end_column_id,
                start_column_name_snapshot=:start_column_name_snapshot,
                end_column_name_snapshot=:end_column_name_snapshot,
                updated_at=now()
            WHERE id=:id
            RETURNING id, project_id, board_id,
                :calc_code as calc_code,
                target_calculation_name,
                start_column_id, end_column_id,
                start_column_name_snapshot, end_column_name_snapshot
            """
        )
        params = {
            "id": str(payload.id),
            "project_id": str(payload.project_id) if payload.project_id else None,
            "board_id": str(payload.board_id) if payload.board_id else None,
            "target_calculation_id": str(calc["id"]),
            "target_calculation_name": payload.calc_code,
            "start_column_id": str(payload.start_column_id),
            "end_column_id": str(payload.end_column_id),
            "start_column_name_snapshot": names.get(str(payload.start_column_id), ""),
            "end_column_name_snapshot": names.get(str(payload.end_column_id), ""),
            "calc_code": payload.calc_code,
        }
    else:
        sql = text(
            """
            INSERT INTO metrics.commitment_rules (
                project_id, board_id, target_calculation_id, target_calculation_name,
                start_column_id, end_column_id,
                start_column_name_snapshot, end_column_name_snapshot
            ) VALUES (
                :project_id, :board_id, :target_calculation_id, :target_calculation_name,
                :start_column_id, :end_column_id,
                :start_column_name_snapshot, :end_column_name_snapshot
            )
            RETURNING id, project_id, board_id,
                :calc_code as calc_code,
                target_calculation_name,
                start_column_id, end_column_id,
                start_column_name_snapshot, end_column_name_snapshot
            """
        )
        params = {
            "project_id": str(payload.project_id) if payload.project_id else None,
            "board_id": str(payload.board_id) if payload.board_id else None,
            "target_calculation_id": str(calc["id"]),
            "target_calculation_name": payload.calc_code,
            "start_column_id": str(payload.start_column_id),
            "end_column_id": str(payload.end_column_id),
            "start_column_name_snapshot": names.get(str(payload.start_column_id), ""),
            "end_column_name_snapshot": names.get(str(payload.end_column_id), ""),
            "calc_code": payload.calc_code,
        }

    try:
        row = (await db.execute(sql, params)).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Commitment rule not found")
        return CommitmentRuleResponse(**row)
    except IntegrityError as exc:
        logger.warning("IntegrityError in %s: %s", __name__, exc.orig)
        raise HTTPException(
            status_code=409, detail="Conflict: a record with this key already exists"
        ) from exc


@router.delete("/commitment-rules/{rule_id}")
async def delete_commitment_rule(
    rule_id: UUID,
    db: DBSession,
    _admin: AdminDependency,
):
    result = await db.execute(
        text("DELETE FROM metrics.commitment_rules WHERE id=:id"),
        {"id": str(rule_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Commitment rule not found")
    return {"status": "ok"}


@router.get("/calculation-settings", response_model=list[CalculationSettingResponse])
async def list_calculation_settings(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID | None = None,
    calc_code: str | None = None,
    settings_type: str | None = None,
):
    query = """
        SELECT cs.id, cs.project_id, c.calc_code, d.metric_code,
               cs.settings_type, cs.settings_json, cs.enabled
        FROM metrics.calculation_settings cs
        JOIN metrics.calculations c ON c.id = cs.target_calculation_id
        JOIN metrics.definitions d ON d.id = c.definition_id
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if project_id:
        query += " AND cs.project_id = :project_id"
        params["project_id"] = str(project_id)
    if calc_code:
        query += " AND c.calc_code = :calc_code"
        params["calc_code"] = calc_code
    if settings_type:
        query += " AND cs.settings_type = :settings_type"
        params["settings_type"] = settings_type
    query += " ORDER BY c.calc_code, cs.settings_type, cs.project_id"

    rows = (await db.execute(text(query), params)).mappings().all()
    return [CalculationSettingResponse(**row) for row in rows]


@router.post("/calculation-settings", response_model=CalculationSettingResponse)
async def upsert_calculation_setting(
    payload: CalculationSettingUpsert,
    db: DBSession,
    _admin: AdminDependency,
):
    calc = (
        (
            await db.execute(
                text(
                    """
                SELECT c.id, c.calc_code, d.metric_code
                FROM metrics.calculations c
                JOIN metrics.definitions d ON d.id = c.definition_id
                WHERE c.calc_code = :calc_code
                """
                ),
                {"calc_code": payload.calc_code},
            )
        )
        .mappings()
        .first()
    )
    if not calc:
        raise HTTPException(status_code=404, detail="Calculation not found")

    if payload.id:
        sql = text(
            """
            UPDATE metrics.calculation_settings
            SET project_id=:project_id,
                target_calculation_id=:target_calculation_id,
                settings_type=:settings_type,
                settings_json=:settings_json,
                enabled=:enabled,
                updated_at=now()
            WHERE id=:id
            RETURNING id, project_id,
                :calc_code AS calc_code,
                :metric_code AS metric_code,
                settings_type, settings_json, enabled
            """
        )
        params = {
            "id": str(payload.id),
            "project_id": str(payload.project_id) if payload.project_id else None,
            "target_calculation_id": str(calc["id"]),
            "settings_type": payload.settings_type,
            "settings_json": payload.settings_json,
            "enabled": payload.enabled,
            "calc_code": payload.calc_code,
            "metric_code": calc["metric_code"],
        }
    else:
        sql = text(
            """
            INSERT INTO metrics.calculation_settings (
                project_id, target_calculation_id, settings_type, settings_json, enabled
            ) VALUES (
                :project_id, :target_calculation_id, :settings_type, :settings_json, :enabled
            )
            RETURNING id, project_id,
                :calc_code AS calc_code,
                :metric_code AS metric_code,
                settings_type, settings_json, enabled
            """
        )
        params = {
            "project_id": str(payload.project_id) if payload.project_id else None,
            "target_calculation_id": str(calc["id"]),
            "settings_type": payload.settings_type,
            "settings_json": payload.settings_json,
            "enabled": payload.enabled,
            "calc_code": payload.calc_code,
            "metric_code": calc["metric_code"],
        }

    try:
        row = (await db.execute(sql, params)).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Calculation setting not found")
        return CalculationSettingResponse(**row)
    except IntegrityError as exc:
        logger.warning("IntegrityError in %s: %s", __name__, exc.orig)
        raise HTTPException(
            status_code=409, detail="Conflict: a record with this key already exists"
        ) from exc


@router.delete("/calculation-settings/{setting_id}")
async def delete_calculation_setting(
    setting_id: UUID,
    db: DBSession,
    _admin: AdminDependency,
):
    result = await db.execute(
        text("DELETE FROM metrics.calculation_settings WHERE id=:id"),
        {"id": str(setting_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Calculation setting not found")
    return {"status": "ok"}


@router.get("/units", response_model=list[UnitBindingResponse])
async def list_units(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID | None = None,
):
    query = """
        SELECT id, project_id, unit_code, display_symbol, source_field_id, source_entity
        FROM metrics.units
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = str(project_id)
    query += " ORDER BY project_id NULLS FIRST, unit_code"

    rows = (await db.execute(text(query), params)).mappings().all()
    return [UnitBindingResponse(**row) for row in rows]


@router.put("/units/{unit_code}", response_model=UnitBindingResponse)
async def upsert_unit(
    unit_code: str,
    payload: UnitBindingUpsert,
    db: DBSession,
    _admin: AdminDependency,
):
    existing = (
        (
            await db.execute(
                text(
                    """
                SELECT id
                FROM metrics.units
                WHERE unit_code=:unit_code AND (
                    (project_id = :project_id) OR
                    (project_id IS NULL AND :project_id IS NULL)
                )
                """
                ),
                {
                    "unit_code": unit_code,
                    "project_id": (
                        str(payload.project_id) if payload.project_id else None
                    ),
                },
            )
        )
        .mappings()
        .first()
    )

    if existing:
        sql = text(
            """
            UPDATE metrics.units
            SET display_symbol = COALESCE(:display_symbol, display_symbol),
                source_field_id = :source_field_id,
                source_entity = :source_entity,
                updated_at = now()
            WHERE id = :id
            RETURNING id, project_id, unit_code, display_symbol, source_field_id, source_entity
            """
        )
        params = {
            "id": str(existing["id"]),
            "display_symbol": payload.display_symbol,
            "source_field_id": (
                str(payload.source_field_id) if payload.source_field_id else None
            ),
            "source_entity": payload.source_entity,
        }
    else:
        sql = text(
            """
            INSERT INTO metrics.units (
                project_id, unit_code, display_symbol, source_field_id, source_entity
            ) VALUES (
                :project_id, :unit_code, :display_symbol, :source_field_id, :source_entity
            )
            RETURNING id, project_id, unit_code, display_symbol, source_field_id, source_entity
            """
        )
        params = {
            "project_id": str(payload.project_id) if payload.project_id else None,
            "unit_code": unit_code,
            "display_symbol": payload.display_symbol or unit_code,
            "source_field_id": (
                str(payload.source_field_id) if payload.source_field_id else None
            ),
            "source_entity": payload.source_entity,
        }

    try:
        row = (await db.execute(sql, params)).mappings().first()
        return UnitBindingResponse(**row)
    except IntegrityError as exc:
        logger.warning("IntegrityError in %s: %s", __name__, exc.orig)
        raise HTTPException(
            status_code=409, detail="Conflict: a record with this key already exists"
        ) from exc


@router.delete("/units/{unit_id}")
async def delete_unit(
    unit_id: UUID,
    db: DBSession,
    _admin: AdminDependency,
):
    result = await db.execute(
        text("DELETE FROM metrics.units WHERE id=:id"),
        {"id": str(unit_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Unit binding not found")
    return {"status": "ok"}


@router.get("/slice-rules", response_model=list[SliceRuleResponse])
async def list_slice_rules(
    db: DBSession,
    _admin: AdminDependency,
    project_id: UUID | None = None,
    definition_id: UUID | None = None,
):
    query = """
        SELECT id, project_id, rule_name, target_definition_id,
               target_definition_name, source_table,
               group_by_source_column, enabled
        FROM metrics.slice_rules
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = str(project_id)
    if definition_id:
        query += " AND target_definition_id = :definition_id"
        params["definition_id"] = str(definition_id)
    query += " ORDER BY rule_name, project_id"

    rows = (await db.execute(text(query), params)).mappings().all()
    return [SliceRuleResponse(**row) for row in rows]


@router.post("/slice-rules", response_model=SliceRuleResponse)
async def upsert_slice_rule(
    payload: SliceRuleUpsert,
    db: DBSession,
    _admin: AdminDependency,
):
    if payload.id:
        sql = text(
            """
            UPDATE metrics.slice_rules
            SET project_id=:project_id,
                rule_name=:rule_name,
                target_definition_id=:target_definition_id,
                target_definition_name=:target_definition_name,
                source_table=:source_table,
                group_by_source_column=:group_by_source_column,
                enabled=:enabled,
                updated_at=now()
            WHERE id=:id
            RETURNING id, project_id, rule_name, target_definition_id,
                      target_definition_name, source_table,
                      group_by_source_column, enabled
            """
        )
        params = {
            "id": str(payload.id),
            "project_id": str(payload.project_id) if payload.project_id else None,
            "rule_name": payload.rule_name,
            "target_definition_id": (
                str(payload.target_definition_id)
                if payload.target_definition_id
                else None
            ),
            "target_definition_name": payload.target_definition_name,
            "source_table": payload.source_table,
            "group_by_source_column": payload.group_by_source_column,
            "enabled": payload.enabled,
        }
    else:
        sql = text(
            """
            INSERT INTO metrics.slice_rules (
                project_id, rule_name, target_definition_id,
                target_definition_name, source_table,
                group_by_source_column, enabled
            ) VALUES (
                :project_id, :rule_name, :target_definition_id,
                :target_definition_name, :source_table,
                :group_by_source_column, :enabled
            )
            RETURNING id, project_id, rule_name, target_definition_id,
                      target_definition_name, source_table,
                      group_by_source_column, enabled
            """
        )
        params = {
            "project_id": str(payload.project_id) if payload.project_id else None,
            "rule_name": payload.rule_name,
            "target_definition_id": (
                str(payload.target_definition_id)
                if payload.target_definition_id
                else None
            ),
            "target_definition_name": payload.target_definition_name,
            "source_table": payload.source_table,
            "group_by_source_column": payload.group_by_source_column,
            "enabled": payload.enabled,
        }

    try:
        row = (await db.execute(sql, params)).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Slice rule not found")
        return SliceRuleResponse(**row)
    except IntegrityError as exc:
        logger.warning("IntegrityError in %s: %s", __name__, exc.orig)
        raise HTTPException(
            status_code=409, detail="Conflict: a record with this key already exists"
        ) from exc


@router.delete("/slice-rules/{rule_id}")
async def delete_slice_rule(
    rule_id: UUID,
    db: DBSession,
    _admin: AdminDependency,
):
    result = await db.execute(
        text("DELETE FROM metrics.slice_rules WHERE id=:id"),
        {"id": str(rule_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Slice rule not found")
    return {"status": "ok"}


@router.post("/validate", response_model=ValidationResponse)
async def validate_config(
    db: DBSession,
    _admin: AdminDependency,
    project_id: Annotated[UUID | None, Query()] = None,
):
    projects_query = """
        SELECT p.id AS project_id, p.external_key AS project_key
        FROM clean_jira.projects p
    """
    params: dict[str, Any] = {}
    if project_id:
        projects_query += " WHERE p.id = :project_id"
        params["project_id"] = str(project_id)

    projects = (await db.execute(text(projects_query), params)).mappings().all()
    issues: list[ValidationIssue] = []

    commitment_calcs = (
        (
            await db.execute(
                text(
                    "SELECT calc_code FROM metrics.calculations WHERE uses_commitment_points = true"
                )
            )
        )
        .scalars()
        .all()
    )

    for project in projects:
        pid = str(project["project_id"])

        sp_row = (
            (
                await db.execute(
                    text(
                        """
                    SELECT source_field_id
                    FROM metrics.units
                    WHERE unit_code='story_points' AND (project_id=:pid OR project_id IS NULL)
                    ORDER BY project_id NULLS LAST
                    LIMIT 1
                    """
                    ),
                    {"pid": pid},
                )
            )
            .mappings()
            .first()
        )
        if not sp_row or not sp_row["source_field_id"]:
            issues.append(
                ValidationIssue(
                    project_id=project["project_id"],
                    project_key=project["project_key"],
                    severity="warning",
                    code="missing_story_points_unit",
                    details="No source_field_id configured for unit_code=story_points",
                )
            )

        for calc_code in commitment_calcs:
            cnt = (
                await db.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM metrics.commitment_rules cr
                        JOIN metrics.calculations c ON c.id = cr.target_calculation_id
                        WHERE c.calc_code=:calc_code
                          AND (cr.project_id=:pid OR cr.project_id IS NULL)
                        """
                    ),
                    {"calc_code": calc_code, "pid": pid},
                )
            ).scalar()
            if not cnt:
                issues.append(
                    ValidationIssue(
                        project_id=project["project_id"],
                        project_key=project["project_key"],
                        severity="warning",
                        code="missing_commitment_rule",
                        calc_code=calc_code,
                        details=f"No commitment rule found for {calc_code}",
                    )
                )

        for calc_code, settings_types in REQUIRED_SETTINGS_BY_CALC.items():
            for settings_type in settings_types:
                cnt = (
                    await db.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM metrics.calculation_settings s
                            JOIN metrics.calculations c ON c.id = s.target_calculation_id
                            WHERE c.calc_code=:calc_code
                              AND s.settings_type=:settings_type
                              AND s.enabled=true
                              AND (s.project_id=:pid OR s.project_id IS NULL)
                            """
                        ),
                        {
                            "calc_code": calc_code,
                            "settings_type": settings_type,
                            "pid": pid,
                        },
                    )
                ).scalar()
                if not cnt:
                    issues.append(
                        ValidationIssue(
                            project_id=project["project_id"],
                            project_key=project["project_key"],
                            severity="warning",
                            code="missing_calc_setting",
                            calc_code=calc_code,
                            details=f"Missing enabled setting type '{settings_type}'",
                        )
                    )

    return ValidationResponse(issues=issues)


@router.get("/jobs", response_model=list[AdminJobItem])
async def list_admin_jobs(_admin: AdminDependency):
    return [AdminJobItem(**job) for job in SUPPORTED_ADMIN_JOBS]


@router.post("/jobs/launch", response_model=AdminJobLaunchResponse)
async def launch_admin_job(
    payload: AdminJobLaunchRequest,
    _admin: AdminDependency,
):
    supported = {job["job_name"] for job in SUPPORTED_ADMIN_JOBS}
    if payload.job_name not in supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported job_name: {payload.job_name}",
        )

    client = DagsterClient()
    try:
        response = await client.trigger_job(job_name=payload.job_name)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to launch Dagster job: {str(exc)}",
        ) from exc

    launch_result = response.get("data", {}).get("launchRun", {})
    typename = launch_result.get("__typename")
    if typename == "LaunchRunSuccess":
        run_info = launch_result.get("run", {})
        run_id = run_info.get("runId")
        run_status = run_info.get("status", "UNKNOWN")
        if not run_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Dagster launch did not return runId",
            )
        return AdminJobLaunchResponse(
            job_name=payload.job_name,
            run_id=run_id,
            status=run_status,
        )

    error_msg = launch_result.get("message", "Unknown Dagster launch error")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to launch job: {error_msg}",
    )


@router.get("/jobs/runs/{run_id}", response_model=AdminRunDetailsResponse)
async def get_admin_job_run_details(
    run_id: str,
    _admin: AdminDependency,
):
    client = DagsterClient()
    try:
        response = await client.get_run_details(run_id=run_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read Dagster run details: {str(exc)}",
        ) from exc

    run_or_error = response.get("data", {}).get("runOrError", {})
    typename = run_or_error.get("__typename")
    if typename == "RunNotFoundError":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )
    if typename != "Run":
        error_msg = run_or_error.get("message", "Unknown Dagster run error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read run details: {error_msg}",
        )

    step_rows = run_or_error.get("stepStats") or []
    step_models = [
        AdminRunStepStatus(
            step_key=s.get("stepKey", ""),
            status=s.get("status"),
            start_time=s.get("startTime"),
            end_time=s.get("endTime"),
        )
        for s in step_rows
    ]
    total_steps = len(step_models)
    completed_steps = sum(
        1
        for s in step_models
        if (s.status or "").upper() in {"SUCCESS", "FAILURE", "SKIPPED", "CANCELED"}
    )
    failed_steps = sum(1 for s in step_models if (s.status or "").upper() == "FAILURE")
    running_steps = sum(
        1
        for s in step_models
        if (s.status or "").upper() in {"STARTED", "STARTING", "IN_PROGRESS"}
    )
    progress_pct = round((completed_steps / total_steps) * 100, 2) if total_steps else 0

    start_time = run_or_error.get("startTime")
    end_time = run_or_error.get("endTime")
    duration_seconds: float | None = None
    if start_time and end_time:
        duration_seconds = max(0.0, float(end_time) - float(start_time))

    raw_events = (
        run_or_error.get("eventConnection", {}).get("events")
        if run_or_error.get("eventConnection")
        else []
    ) or []
    error_events = []
    for e in raw_events:
        level = (e.get("level") or "").upper()
        event_type = (e.get("eventType") or "").upper()
        if level in {"ERROR", "CRITICAL"} or "FAIL" in event_type:
            error_events.append(
                AdminRunEvent(
                    timestamp=e.get("timestamp"),
                    level=e.get("level"),
                    event_type=e.get("eventType"),
                    message=e.get("message"),
                )
            )

    return AdminRunDetailsResponse(
        run_id=run_or_error.get("runId", run_id),
        status=run_or_error.get("status", "UNKNOWN"),
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
        total_steps=total_steps,
        completed_steps=completed_steps,
        failed_steps=failed_steps,
        running_steps=running_steps,
        progress_pct=progress_pct,
        steps=step_models,
        errors=error_events,
    )


@router.get("/metric-jobs", response_model=list[AdminJobItem])
async def list_metric_recalc_jobs(_admin: AdminDependency):
    return [AdminJobItem(**job) for job in METRIC_RECALC_JOBS]


@router.post("/metric-jobs/launch-batch", response_model=list[AdminBatchJobLaunchItem])
async def launch_metric_batch(
    payload: AdminBatchJobLaunchRequest,
    _admin: AdminDependency,
):
    supported = {job["job_name"] for job in METRIC_RECALC_JOBS}
    unknown = [j for j in payload.job_names if j not in supported]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported metric job names: {unknown}",
        )

    client = DagsterClient()
    results: list[AdminBatchJobLaunchItem] = []
    for job_name in payload.job_names:
        try:
            response = await client.trigger_job(job_name=job_name)
            launch_result = response.get("data", {}).get("launchRun", {})
            typename = launch_result.get("__typename")
            if typename == "LaunchRunSuccess":
                run_info = launch_result.get("run", {})
                run_id = run_info.get("runId")
                run_status = run_info.get("status", "UNKNOWN")
                results.append(
                    AdminBatchJobLaunchItem(
                        job_name=job_name,
                        run_id=run_id,
                        status=run_status,
                    )
                )
            else:
                error_msg = launch_result.get("message", "Unknown Dagster launch error")
                results.append(
                    AdminBatchJobLaunchItem(
                        job_name=job_name,
                        status="LAUNCH_FAILED",
                        error=error_msg,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            results.append(
                AdminBatchJobLaunchItem(
                    job_name=job_name,
                    status="LAUNCH_FAILED",
                    error=str(exc),
                )
            )
    return results
