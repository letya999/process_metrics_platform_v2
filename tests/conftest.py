"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def sample_jira_issue():
    """Sample Jira issue data for testing."""
    return {
        "id": "10001",
        "key": "PROJ-1",
        "fields": {
            "summary": "Test issue",
            "status": {"name": "Done"},
            "issuetype": {"name": "Story"},
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-02T10:00:00.000+0000",
        },
    }
