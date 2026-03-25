"""Pytest configuration and shared fixtures.

This module provides fixtures for testing:
- Database connections (mock and real)
- Sample data fixtures
- API test client
"""

from datetime import datetime, timezone
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# =============================================================================
# Sample Data Fixtures
# =============================================================================


def pytest_addoption(parser):
    """Add optional flags for slow/external test suites."""
    parser.addoption(
        "--run-db-tests",
        action="store_true",
        default=False,
        help="Run validation tests that require a live database with seeded data.",
    )


@pytest.fixture
def sample_jira_issue() -> dict[str, Any]:
    """Sample raw Jira issue data for testing."""
    return {
        "id": "10001",
        "key": "PROJ-123",
        "self": "https://company.atlassian.net/rest/api/3/issue/10001",
        "fields": {
            "summary": "Test issue summary",
            "description": "Test issue description",
            "created": "2024-01-15T10:30:00.000+0000",
            "updated": "2024-01-20T15:45:00.000+0000",
            "resolutiondate": "2024-01-20T15:45:00.000+0000",
            "issuetype": {
                "id": "10002",
                "name": "Story",
                "subtask": False,
            },
            "status": {
                "id": "10003",
                "name": "Done",
                "statusCategory": {
                    "id": 3,
                    "key": "done",
                    "name": "Done",
                },
            },
            "priority": {
                "id": "3",
                "name": "Medium",
            },
            "project": {
                "id": "10000",
                "key": "PROJ",
                "name": "Test Project",
            },
            "assignee": {
                "accountId": "user123",
                "displayName": "John Doe",
                "emailAddress": "john@example.com",
            },
            "reporter": {
                "accountId": "user456",
                "displayName": "Jane Smith",
                "emailAddress": "jane@example.com",
            },
            "labels": ["backend", "feature"],
            "components": [{"name": "API"}, {"name": "Database"}],
            "customfield_10016": 5,  # Story points
            "customfield_10020": [  # Sprint
                {
                    "id": 100,
                    "name": "Sprint 1",
                    "state": "closed",
                }
            ],
        },
    }


@pytest.fixture
def sample_jira_sprint() -> dict[str, Any]:
    """Sample raw Jira sprint data for testing."""
    return {
        "id": 100,
        "name": "Sprint 1",
        "state": "closed",
        "startDate": "2024-01-01T00:00:00.000Z",
        "endDate": "2024-01-14T23:59:59.000Z",
        "completeDate": "2024-01-15T10:00:00.000Z",
        "goal": "Complete initial feature set",
        "originBoardId": 1,
    }


@pytest.fixture
def sample_jira_changelog() -> dict[str, Any]:
    """Sample raw Jira changelog data for testing."""
    return {
        "histories": [
            {
                "id": "1001",
                "created": "2024-01-16T09:00:00.000+0000",
                "author": {
                    "accountId": "user123",
                    "displayName": "John Doe",
                },
                "items": [
                    {
                        "field": "status",
                        "fieldtype": "jira",
                        "from": "10000",
                        "fromString": "Open",
                        "to": "10001",
                        "toString": "In Progress",
                    }
                ],
            },
            {
                "id": "1002",
                "created": "2024-01-20T15:45:00.000+0000",
                "author": {
                    "accountId": "user123",
                    "displayName": "John Doe",
                },
                "items": [
                    {
                        "field": "status",
                        "fieldtype": "jira",
                        "from": "10001",
                        "fromString": "In Progress",
                        "to": "10002",
                        "toString": "Done",
                    }
                ],
            },
        ]
    }


@pytest.fixture
def sample_clean_issue() -> dict[str, Any]:
    """Sample clean issue data for testing."""
    return {
        "external_id": "10001",
        "external_key": "PROJ-123",
        "summary": "Test issue summary",
        "description": "Test issue description",
        "status_name": "Done",
        "status_category": "done",
        "issue_type_name": "Story",
        "issue_type_id": "10002",
        "priority_name": "Medium",
        "project_key": "PROJ",
        "project_id": "10000",
        "project_name": "Test Project",
        "assignee_account_id": "user123",
        "assignee_display_name": "John Doe",
        "reporter_account_id": "user456",
        "reporter_display_name": "Jane Smith",
        "labels": ["backend", "feature"],
        "components": ["API", "Database"],
        "story_points": 5,
        "sprint_id": 100,
        "sprint_name": "Sprint 1",
        "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 20, 15, 45, 0, tzinfo=timezone.utc),
        "resolved_at": datetime(2024, 1, 20, 15, 45, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def sample_issues_for_velocity() -> list[dict[str, Any]]:
    """Sample issues for velocity calculation testing."""
    return [
        {"status_name": "Done", "story_points": 5},
        {"status_name": "Done", "story_points": 3},
        {"status_name": "In Progress", "story_points": 8},
        {"status_name": "Done", "story_points": 2},
        {"status_name": "Open", "story_points": None},
    ]


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_db_engine():
    """Mock database engine for unit tests."""
    engine = MagicMock()
    connection = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=connection)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine


@pytest.fixture
def mock_database_resource(mock_db_engine):
    """Mock DatabaseResource for testing."""
    resource = MagicMock()
    resource.get_engine.return_value = mock_db_engine
    return resource


# =============================================================================
# API Test Client
# =============================================================================


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application."""
    # Import here to avoid circular imports
    from app.main import app

    with TestClient(app) as client:
        yield client


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def jira_env_vars(monkeypatch):
    """Set up Jira environment variables for testing."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://test.atlassian.net")
    monkeypatch.setenv("JIRA_USER_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test_token")  # noqa: S106
    monkeypatch.setenv("JIRA_PROJECTS", "PROJ,TEST")


@pytest.fixture(autouse=True)
def database_env_vars(monkeypatch):
    """Set up database environment variables for testing.

    Uses credentials matching the local development environment (.env).
    """
    # Use the complex password from .env which seems to be the one used in the environment
    password = "woJX9+pYcU+y2JApOCcqs5HP"
    db_name = "process_metrics_v2"
    db_url = f"postgresql://postgres:{password}@localhost:5432/{db_name}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    monkeypatch.setenv("POSTGRES_DB", db_name)
    monkeypatch.setenv("DAGSTER_POSTGRES_USER", "postgres")
    monkeypatch.setenv("DAGSTER_POSTGRES_PASSWORD", password)
    monkeypatch.setenv("DAGSTER_POSTGRES_DB", db_name)
    monkeypatch.setenv("DAGSTER_POSTGRES_HOST", "localhost")


@pytest.fixture(autouse=True)
def reset_database_module_state(database_env_vars):
    """Reset cached database engine/session between tests."""
    from app.database import reset_db_state_for_tests

    reset_db_state_for_tests()
    yield
    reset_db_state_for_tests()


@pytest.fixture(autouse=True)
def clear_table_exists_cache():
    """Clear _TABLE_EXISTS_CACHE between tests to prevent cross-test pollution."""
    from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE

    _TABLE_EXISTS_CACHE.clear()
    yield
    _TABLE_EXISTS_CACHE.clear()
