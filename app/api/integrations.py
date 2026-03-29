"""API routes for managing data source integrations."""

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import AdminDependency
from app.database import get_db
from app.models.orm import IntegrationTypeModel, ToolIntegration, User
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationResponse,
    IntegrationTypeResponse,
    IntegrationUpdate,
    JiraProjectDiscovery,
    SyncResponse,
    SyncStatusResponse,
)
from app.services.dagster_client import DagsterClient
from app.services.url_safety import validate_and_normalize_instance_url

router = APIRouter()


# Dependency for database session
DBSession = Annotated[AsyncSession, Depends(get_db)]


def _integration_to_response(
    integration: ToolIntegration, type_name: str | None = None
) -> IntegrationResponse:
    """Convert ORM model to response schema."""
    return IntegrationResponse(
        id=integration.id,
        user_id=integration.user_id,
        integration_type_id=integration.integration_type_id,
        integration_type_name=type_name,
        instance_url=integration.instance_url,
        user_email=integration.user_email,
        is_active=integration.is_active,
        last_sync_at=integration.last_sync_at,
        last_sync_status=integration.last_sync_status,
        last_error=integration.last_error,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.get("/integration-types", response_model=list[IntegrationTypeResponse])
async def list_integration_types(db: DBSession):
    """List all available integration types."""
    result = await db.execute(
        select(IntegrationTypeModel).where(IntegrationTypeModel.is_active.is_(True))
    )
    types = result.scalars().all()
    return types


@router.get("/integrations", response_model=list[IntegrationResponse])
async def list_integrations(
    db: DBSession,
    _admin: AdminDependency,
    user_id: Annotated[UUID | None, Query(description="Filter by user ID")] = None,
    is_active: Annotated[
        bool | None, Query(description="Filter by active status")
    ] = None,
):
    """List all configured integrations."""
    query = select(ToolIntegration).options(
        selectinload(ToolIntegration.integration_type)
    )

    if user_id is not None:
        query = query.where(ToolIntegration.user_id == user_id)
    if is_active is not None:
        query = query.where(ToolIntegration.is_active == is_active)

    result = await db.execute(query)
    integrations = result.scalars().all()

    return [
        _integration_to_response(
            integration,
            type_name=(
                integration.integration_type.name
                if integration.integration_type
                else None
            ),
        )
        for integration in integrations
    ]


@router.post(
    "/integrations",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    db: DBSession,
    _admin: AdminDependency,
    integration_data: IntegrationCreate,
    user_id: Annotated[UUID, Query(description="User ID creating the integration")],
):
    """Create a new integration."""
    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Verify integration type exists
    type_result = await db.execute(
        select(IntegrationTypeModel).where(
            IntegrationTypeModel.id == integration_data.integration_type_id
        )
    )
    integration_type = type_result.scalar_one_or_none()
    if not integration_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration type {integration_data.integration_type_id} not found",
        )

    normalized_instance_url = None
    if integration_data.instance_url:
        try:
            normalized_instance_url = validate_and_normalize_instance_url(
                integration_data.instance_url
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid instance_url: {exc}",
            ) from exc

    # Create integration
    # For dev/test, store token directly (in production, use secret_reference)
    integration = ToolIntegration(
        user_id=user_id,
        integration_type_id=integration_data.integration_type_id,
        instance_url=normalized_instance_url,
        user_email=integration_data.user_email,
        secret_provider=integration_data.secret_provider,
    )

    # Handle token storage based on provider
    if integration_data.secret_provider == "hardcoded":  # noqa: S105
        integration.api_token_unsafe = integration_data.api_token
        integration.secret_reference = None
    else:
        # For other providers, store reference to secret
        integration.secret_reference = f"INTEGRATION_TOKEN_{integration.id}"
        integration.api_token_unsafe = None

    db.add(integration)
    await db.flush()
    await db.refresh(integration)

    return _integration_to_response(integration, type_name=integration_type.name)


@router.get("/integrations/{integration_id}", response_model=IntegrationResponse)
async def get_integration(db: DBSession, integration_id: UUID, _admin: AdminDependency):
    """Get integration by ID."""
    result = await db.execute(
        select(ToolIntegration)
        .options(selectinload(ToolIntegration.integration_type))
        .where(ToolIntegration.id == integration_id)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    return _integration_to_response(
        integration,
        type_name=(
            integration.integration_type.name if integration.integration_type else None
        ),
    )


@router.put("/integrations/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    db: DBSession,
    integration_id: UUID,
    _admin: AdminDependency,
    update_data: IntegrationUpdate,
):
    """Update an integration."""
    result = await db.execute(
        select(ToolIntegration)
        .options(selectinload(ToolIntegration.integration_type))
        .where(ToolIntegration.id == integration_id)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    # Update fields if provided
    if update_data.instance_url is not None:
        if update_data.instance_url:
            try:
                integration.instance_url = validate_and_normalize_instance_url(
                    update_data.instance_url
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Invalid instance_url: {exc}",
                ) from exc
        else:
            integration.instance_url = None
    if update_data.user_email is not None:
        integration.user_email = update_data.user_email
    if update_data.is_active is not None:
        integration.is_active = update_data.is_active
    if update_data.api_token is not None:
        # Update token storage
        if integration.secret_provider == "hardcoded":  # noqa: S105
            integration.api_token_unsafe = update_data.api_token
        else:
            # For other providers, update reference
            integration.secret_reference = f"INTEGRATION_TOKEN_{integration.id}"

    await db.flush()
    await db.refresh(integration)

    return _integration_to_response(
        integration,
        type_name=(
            integration.integration_type.name if integration.integration_type else None
        ),
    )


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    db: DBSession, integration_id: UUID, _admin: AdminDependency
):
    """Delete an integration."""
    result = await db.execute(
        select(ToolIntegration).where(ToolIntegration.id == integration_id)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    await db.delete(integration)
    return None


@router.get(
    "/integrations/{integration_id}/jira-projects",
    response_model=list[JiraProjectDiscovery],
)
async def list_jira_projects(
    db: DBSession,
    integration_id: UUID,
    _admin: AdminDependency,
):
    """Fetch all Jira projects accessible via the integration credentials.

    Also marks which projects are already imported into platform.projects.
    """
    import os

    from sqlalchemy import select

    from app.models.orm import Project

    result = await db.execute(
        select(ToolIntegration)
        .options(selectinload(ToolIntegration.integration_type))
        .where(ToolIntegration.id == integration_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    # Resolve API token
    if (
        integration.secret_provider == "env"  # noqa: S105
        and integration.secret_reference
    ):
        api_token = os.getenv(integration.secret_reference, "")
    elif integration.api_token_unsafe:
        api_token = integration.api_token_unsafe
    else:
        api_token = ""

    if not api_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Integration has no resolvable API token",
        )

    base_url = (integration.instance_url or "").rstrip("/")
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Integration has no instance_url configured",
        )

    try:
        base_url = validate_and_normalize_instance_url(base_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid instance_url: {exc}",
        ) from exc

    # Fetch project list from Jira
    auth = (integration.user_email or "", api_token)
    jira_projects: list[dict] = []
    start_at = 0
    max_results = 100

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(
                f"{base_url}/rest/api/3/project/search",
                params={"startAt": start_at, "maxResults": max_results},
                auth=auth,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Jira API returned {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
            jira_projects.extend(data.get("values", []))
            if data.get("isLast", True):
                break
            start_at += max_results

    # Find already-imported external_ids for this integration
    imported_result = await db.execute(
        select(Project.external_id).where(Project.tool_integration_id == integration_id)
    )
    imported_ids = {row[0] for row in imported_result.fetchall()}

    return [
        JiraProjectDiscovery(
            key=p["key"],
            id=p["id"],
            name=p["name"],
            url=p.get("self"),
            already_imported=p["id"] in imported_ids,
        )
        for p in jira_projects
    ]


@router.post("/integrations/{integration_id}/sync", response_model=SyncResponse)
async def trigger_sync(db: DBSession, integration_id: UUID, _admin: AdminDependency):
    """Trigger a sync for an integration via Dagster."""
    # Verify integration exists
    result = await db.execute(
        select(ToolIntegration)
        .options(selectinload(ToolIntegration.integration_type))
        .where(ToolIntegration.id == integration_id)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    if not integration.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is not active",
        )

    # Determine job name based on integration type
    int_type = integration.integration_type
    type_name = int_type.name if int_type else ""
    if type_name.startswith("jira"):
        job_name = "jira_sync_job"
    elif type_name.startswith("gitlab"):
        job_name = "gitlab_sync_job"
    else:
        job_name = "generic_sync_job"

    # Trigger Dagster job
    client = DagsterClient()
    try:
        response = await client.trigger_job(
            job_name=job_name,
            run_config={
                "resources": {
                    "integration": {
                        "config": {
                            "integration_id": str(integration_id),
                        }
                    }
                }
            },
        )

        # Parse response
        launch_result = response.get("data", {}).get("launchRun", {})
        typename = launch_result.get("__typename")

        if typename == "LaunchRunSuccess":
            run_info = launch_result.get("run", {})
            run_id = run_info.get("runId")
            run_status = run_info.get("status")

            # Update integration status
            integration.last_sync_status = "running"
            await db.flush()

            return SyncResponse(
                message="Sync triggered successfully",
                run_id=run_id,
                status=run_status,
            )
        else:
            error_msg = launch_result.get("message", "Unknown error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger sync: {error_msg}",
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {str(e)}",
        ) from e


@router.get(
    "/integrations/{integration_id}/sync/{run_id}", response_model=SyncStatusResponse
)
async def get_sync_status(
    db: DBSession, integration_id: UUID, run_id: str, _admin: AdminDependency
):
    """Get the status of a sync run."""
    # Verify integration exists
    result = await db.execute(
        select(ToolIntegration).where(ToolIntegration.id == integration_id)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration {integration_id} not found",
        )

    # Query Dagster for run status
    client = DagsterClient()
    try:
        response = await client.get_run_status(run_id)
        run_result = response.get("data", {}).get("runOrError", {})
        typename = run_result.get("__typename")

        if typename == "Run":
            return SyncStatusResponse(
                run_id=run_result.get("runId"),
                status=run_result.get("status"),
                started_at=run_result.get("startTime"),
                completed_at=run_result.get("endTime"),
            )
        elif typename == "RunNotFoundError":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id} not found",
            )
        else:
            error_msg = run_result.get("message", "Unknown error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get run status: {error_msg}",
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get run status: {str(e)}",
        ) from e
