"""Unit tests for app.api.metrics branches and response shaping."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import metrics as metrics_api  # noqa: E402
from app.schemas.metrics import MetricConfigUpdate  # noqa: E402


def _make_db():
    """Create a mock database object."""
    db = MagicMock()
    db.execute = AsyncMock()
    return db


def _mappings_all_result(rows):
    """Mock SQLAlchemy result mappings."""
    result = MagicMock()
    mappings = MagicMock()
    mappings.all.return_value = rows
    mappings.first.return_value = rows[0] if rows else None
    result.mappings.return_value = mappings
    return result


def _scalar_result(value):
    """Mock SQLAlchemy scalar result."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.mark.asyncio
async def test_get_and_update_metrics_config():
    """Verify metrics configuration retrieval and updates."""
    db = _make_db()

    default_cfg = await metrics_api.get_metrics_config(db=db, integration_id=None)
    assert default_cfg.commitment_statuses
    assert default_cfg.done_statuses

    updated = await metrics_api.update_metrics_config(
        db=db,
        _admin=MagicMock(),
        integration_id=uuid4(),
        config_data=MetricConfigUpdate(done_statuses=["Done"], estimation_field="sp"),
    )
    assert updated.done_statuses == ["Done"]
    assert updated.estimation_field == "sp"
    assert (
        updated.commitment_statuses
        == metrics_api.DEFAULT_METRIC_CONFIG.commitment_statuses
    )


@pytest.mark.asyncio
async def test_get_lead_time_metrics_success_with_aggregates():
    """Verify successful retrieval of lead time metrics with aggregates."""
    db = _make_db()
    issue_id = uuid4()
    project_id = uuid4()
    now = datetime.now(timezone.utc)
    db.execute.side_effect = [
        _mappings_all_result(
            [
                {
                    "issue_id": issue_id,
                    "issue_key": "ADS-1",
                    "summary": "Fix auth",
                    "project_id": project_id,
                    "project_key": "ADS",
                    "project_name": "Ads",
                    "issue_type": "Story",
                    "hierarchy_level": "task",
                    "status_name": "Done",
                    "status_category": "done",
                    "created_at": now,
                    "resolved_at": now,
                    "lead_time_days": 2.5,
                    "lead_time_hours": 60.0,
                }
            ]
        ),
        _scalar_result(1),
        _mappings_all_result([{"avg_days": 2.5, "median_days": 2.5}]),
    ]

    response = await metrics_api.get_lead_time_metrics(
        db=db,
        project_id=project_id,
        issue_type="Story",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        limit=10,
        offset=0,
    )

    assert response.total_count == 1
    assert response.avg_lead_time_days == 2.5
    assert response.median_lead_time_days == 2.5
    assert response.items[0].issue_key == "ADS-1"
    assert response.items[0].lead_time_hours == 60.0

    first_sql = db.execute.call_args_list[0].args[0].text
    first_params = db.execute.call_args_list[0].args[1]
    assert "dp.project_id = :project_id" in first_sql
    assert "it.name = :issue_type" in first_sql
    assert first_params["issue_type"] == "Story"
    assert first_params["limit"] == 10


@pytest.mark.asyncio
async def test_get_lead_time_metrics_returns_empty_on_error():
    """Verify that lead time metrics query failure raises HTTPException(500)."""
    db = _make_db()
    db.execute.side_effect = RuntimeError("db broken")

    with pytest.raises(HTTPException) as exc:
        await metrics_api.get_lead_time_metrics(db=db)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_velocity_metrics_success_and_filters():
    """Verify successful retrieval of velocity metrics with filters."""
    db = _make_db()
    sprint_id = uuid4()
    project_id = uuid4()
    db.execute.return_value = _mappings_all_result(
        [
            {
                "sprint_id": sprint_id,
                "sprint_external_id": "1001",
                "sprint_name": "Sprint 10",
                "project_id": project_id,
                "project_key": "ADS",
                "project_name": "Ads",
                "sprint_status": "closed",
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 1, 14),
                "complete_date": date(2026, 1, 15),
                "total_issues": 8,
                "completed_issues": 6,
                "completion_rate_pct": 75.0,
            }
        ]
    )

    response = await metrics_api.get_velocity_metrics(
        db=db,
        project_id=project_id,
        sprint_status="closed",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 2, 1),
        limit=5,
        offset=0,
    )

    assert response.total_count == 1
    assert response.items[0].completed_issues == 6
    assert response.items[0].completion_rate_pct == 75.0

    sql = db.execute.call_args.args[0].text
    params = db.execute.call_args.args[1]
    assert "project_id = :project_id" in sql
    assert "sprint_status = :sprint_status" in sql
    assert params["sprint_status"] == "closed"


@pytest.mark.asyncio
async def test_get_velocity_metrics_returns_empty_on_error():
    """Verify that velocity metrics query failure raises HTTPException(500)."""
    db = _make_db()
    db.execute.side_effect = RuntimeError("db broken")

    with pytest.raises(HTTPException) as exc:
        await metrics_api.get_velocity_metrics(db=db)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_throughput_metrics_success_and_total_fallback_issue_type():
    """Verify successful retrieval of throughput metrics."""
    db = _make_db()
    project_id = uuid4()
    db.execute.return_value = _mappings_all_result(
        [
            {
                "resolved_date": date(2026, 1, 10),
                "project_id": project_id,
                "project_key": "ADS",
                "project_name": "Ads",
                "issue_type": None,
                "issues_completed": 3,
            },
            {
                "resolved_date": date(2026, 1, 11),
                "project_id": project_id,
                "project_key": "ADS",
                "project_name": "Ads",
                "issue_type": "Bug",
                "issues_completed": 2,
            },
        ]
    )

    response = await metrics_api.get_throughput_metrics(
        db=db,
        project_id=project_id,
        issue_type=None,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        limit=30,
        offset=0,
    )

    assert response.total_count == 2
    assert response.total_issues_completed == 5
    assert response.items[0].issue_type == "Total"
    assert response.items[1].issue_type == "Bug"

    sql = db.execute.call_args.args[0].text
    assert "vf.slice_rule_name IS NULL" in sql


@pytest.mark.asyncio
async def test_get_throughput_metrics_returns_empty_on_error():
    """Verify that throughput metrics query failure raises HTTPException(500)."""
    db = _make_db()
    db.execute.side_effect = RuntimeError("db broken")

    with pytest.raises(HTTPException) as exc:
        await metrics_api.get_throughput_metrics(db=db)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_refresh_metrics_returns_accepted_message():
    """Verify that metrics refresh trigger returns success status."""
    db = _make_db()
    response = await metrics_api.refresh_metrics(db=db, _admin=MagicMock())
    assert response["status"] == "success"
