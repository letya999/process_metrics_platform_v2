"""Unit tests for Jira credential validation logic.

Covers the AUTHENTICATED_FAILED silent-failure behaviour specific to Atlassian:
Jira returns HTTP 200 with an empty result and X-Seraph-Loginreason: AUTHENTICATED_FAILED
instead of a proper 401 when credentials are wrong.
"""

from unittest.mock import MagicMock, patch

import pytest

from pipelines.assets.jira.raw import validate_jira_credentials


def _mock_response(status_code: int, login_reason: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"X-Seraph-Loginreason": login_reason} if login_reason else {}
    resp.text = ""
    return resp


class TestValidateJiraCredentials:
    def test_raises_when_credentials_empty(self):
        with pytest.raises(ValueError, match="incomplete"):
            validate_jira_credentials("", "user@example.com", "token")

    def test_raises_when_token_empty(self):
        with pytest.raises(ValueError, match="incomplete"):
            validate_jira_credentials(
                "https://example.atlassian.net", "user@example.com", ""
            )

    def test_raises_on_authenticated_failed_header(self):
        """Jira returns 200 + AUTHENTICATED_FAILED when the token is wrong/expired."""
        with patch(
            "pipelines.assets.jira.raw.requests.get",
            return_value=_mock_response(200, "AUTHENTICATED_FAILED"),
        ):
            with pytest.raises(ValueError, match="AUTHENTICATED_FAILED"):
                validate_jira_credentials(
                    "https://example.atlassian.net", "user@example.com", "bad-token"
                )

    def test_raises_on_http_401(self):
        with patch(
            "pipelines.assets.jira.raw.requests.get",
            return_value=_mock_response(401),
        ):
            with pytest.raises(ValueError, match="HTTP 401"):
                validate_jira_credentials(
                    "https://example.atlassian.net", "user@example.com", "bad-token"
                )

    def test_raises_on_unexpected_status(self):
        with patch(
            "pipelines.assets.jira.raw.requests.get",
            return_value=_mock_response(500),
        ):
            with pytest.raises(ValueError, match="HTTP 500"):
                validate_jira_credentials(
                    "https://example.atlassian.net", "user@example.com", "token"
                )

    def test_passes_on_200_with_no_failed_header(self):
        """A normal 200 without the failure header means auth succeeded."""
        with patch(
            "pipelines.assets.jira.raw.requests.get",
            return_value=_mock_response(200),
        ):
            # Should not raise
            validate_jira_credentials(
                "https://example.atlassian.net", "user@example.com", "valid-token"
            )

    def test_passes_on_403_permission_restricted(self):
        """403 means authenticated but no project access - still a valid token."""
        with patch(
            "pipelines.assets.jira.raw.requests.get",
            return_value=_mock_response(403),
        ):
            validate_jira_credentials(
                "https://example.atlassian.net", "user@example.com", "valid-token"
            )
