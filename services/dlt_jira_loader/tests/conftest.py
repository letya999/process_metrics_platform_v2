"""Pytest fixtures for dlt_jira_loader tests.

This module ensures the `services` package is importable during tests by
adjusting `sys.path` before importing test helpers or pytest fixtures.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import pytest

# Ensure the service package `dlt_jira_loader` is importable during tests.
# Add the `services` directory to sys.path so imports like
# `from dlt_jira_loader.app...` resolve to the folder `services/dlt_jira_loader`.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVICES_PATH = PROJECT_ROOT / "services"

if str(SERVICES_PATH) not in sys.path:
    sys.path.insert(0, str(SERVICES_PATH))


@pytest.fixture(scope="session")
def event_loop():
    """Event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db():
    """Test DB session stub that doesn't require a real database.

    The repository under test executes a simple INSERT and expects a
    result with `scalar_one()`. Provide a lightweight async stub that
    returns a generated UUID for tests.
    """

    class _DummyResult:
        def __init__(self, val):
            self._val = val

        def scalar_one(self):
            return self._val

    class _DummySession:
        async def execute(self, statement, params=None):
            return _DummyResult(uuid4())

        async def close(self):
            return None

    yield _DummySession()


@pytest.fixture
def sample_project_id():
    """Sample project UUID."""
    return uuid4()


@pytest.fixture(autouse=True)
def set_test_database_env(monkeypatch):
    """Ensure tests provide a test DSN via TEST_DATABASE_URL.

    This prevents production code from using defaults during unit tests.
    """
    TEST_DSN = "postgresql+asyncpg://test:test@postgres/test"
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_DSN)
    yield
