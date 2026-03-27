"""Unit tests for pipelines.utils.db_config."""

from unittest.mock import MagicMock, patch

from pipelines.utils.db_config import (
    ProjectCredentials,
    _resolve_token,
    get_active_projects_from_db,
    get_project_credentials,
)

# ── _resolve_token ────────────────────────────────────────────────────────────


class TestResolveToken:
    def test_env_provider_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_JIRA_TOKEN", "secret-from-env")
        token = _resolve_token("env", "MY_JIRA_TOKEN", None)
        assert token == "secret-from-env"

    def test_env_provider_missing_var_returns_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_TOKEN_VAR", raising=False)
        token = _resolve_token("env", "MISSING_TOKEN_VAR", None)
        assert token == ""

    def test_hardcoded_uses_unsafe_field(self):
        token = _resolve_token("hardcoded", None, "raw-token-value")
        assert token == "raw-token-value"

    def test_no_provider_no_unsafe_returns_empty(self):
        token = _resolve_token(None, None, None)
        assert token == ""

    def test_env_provider_takes_precedence_over_unsafe(self, monkeypatch):
        monkeypatch.setenv("ENV_TOKEN", "env-wins")
        token = _resolve_token("env", "ENV_TOKEN", "unsafe-fallback")
        assert token == "env-wins"


# ── get_active_projects_from_db ───────────────────────────────────────────────


def _make_row(key, name, int_id, url, email, provider, ref, unsafe):
    return (key, name, int_id, url, email, provider, ref, unsafe)


def _mock_engine_with_rows(rows):
    """Build a mock SQLAlchemy engine that returns given rows."""
    fetchall_result = MagicMock()
    fetchall_result.fetchall.return_value = rows

    conn_cm = MagicMock()
    conn_cm.__enter__ = MagicMock(return_value=conn_cm)
    conn_cm.__exit__ = MagicMock(return_value=False)
    conn_cm.execute.return_value = fetchall_result

    engine = MagicMock()
    engine.connect.return_value = conn_cm
    return engine


class TestGetActiveProjectsFromDb:
    def test_returns_projects_with_hardcoded_token(self):
        rows = [
            _make_row(
                "ADS",
                "Ads Project",
                "int-1",
                "https://jira.local",
                "user@example.com",
                "hardcoded",
                None,
                "token-abc",
            ),
        ]
        engine = _mock_engine_with_rows(rows)

        with patch("pipelines.resources.database._build_engine", return_value=engine):
            result = get_active_projects_from_db()

        assert len(result) == 1
        assert result[0].project_key == "ADS"
        assert result[0].api_token == "token-abc"
        assert result[0].instance_url == "https://jira.local"

    def test_returns_projects_with_env_token(self, monkeypatch):
        monkeypatch.setenv("PROJ_TOKEN", "env-secret")
        rows = [
            _make_row(
                "PROJ",
                "My Project",
                "int-2",
                "https://jira.io",
                "admin@corp.com",
                "env",
                "PROJ_TOKEN",
                None,
            ),
        ]
        engine = _mock_engine_with_rows(rows)

        with patch("pipelines.resources.database._build_engine", return_value=engine):
            result = get_active_projects_from_db()

        assert len(result) == 1
        assert result[0].api_token == "env-secret"

    def test_skips_project_with_no_resolvable_token(self):
        rows = [
            _make_row(
                "NOPE",
                "No Token",
                "int-3",
                "https://jira.io",
                "u@e.com",
                "env",
                "NONEXISTENT_VAR_XYZ123",
                None,
            ),
        ]
        engine = _mock_engine_with_rows(rows)

        with patch("pipelines.resources.database._build_engine", return_value=engine):
            result = get_active_projects_from_db()

        assert result == []

    def test_returns_empty_on_db_error(self):
        with patch(
            "pipelines.resources.database._build_engine",
            side_effect=RuntimeError("db down"),
        ):
            result = get_active_projects_from_db()

        assert result == []

    def test_multiple_projects_returned_in_order(self, monkeypatch):
        monkeypatch.setenv("T1", "tok1")
        monkeypatch.setenv("T2", "tok2")
        rows = [
            _make_row(
                "ALPHA",
                "Alpha",
                "i1",
                "https://a.jira.io",
                "a@a.com",
                "env",
                "T1",
                None,
            ),
            _make_row(
                "BETA", "Beta", "i2", "https://b.jira.io", "b@b.com", "env", "T2", None
            ),
        ]
        engine = _mock_engine_with_rows(rows)

        with patch("pipelines.resources.database._build_engine", return_value=engine):
            result = get_active_projects_from_db()

        assert [p.project_key for p in result] == ["ALPHA", "BETA"]


# ── get_project_credentials ───────────────────────────────────────────────────


class TestGetProjectCredentials:
    def test_finds_matching_project(self):
        projects = [
            ProjectCredentials("ADS", "Ads", "i1", "https://jira.io", "u@e.com", "tok"),
            ProjectCredentials(
                "MKT", "Marketing", "i2", "https://jira.io", "u@e.com", "tok2"
            ),
        ]
        with patch(
            "pipelines.utils.db_config.get_active_projects_from_db",
            return_value=projects,
        ):
            creds = get_project_credentials("MKT")

        assert creds is not None
        assert creds.project_key == "MKT"
        assert creds.api_token == "tok2"

    def test_returns_none_when_not_found(self):
        projects = [
            ProjectCredentials("ADS", "Ads", "i1", "https://jira.io", "u@e.com", "tok"),
        ]
        with patch(
            "pipelines.utils.db_config.get_active_projects_from_db",
            return_value=projects,
        ):
            creds = get_project_credentials("MISSING")

        assert creds is None

    def test_returns_none_when_db_empty(self):
        with patch(
            "pipelines.utils.db_config.get_active_projects_from_db", return_value=[]
        ):
            creds = get_project_credentials("ADS")

        assert creds is None
