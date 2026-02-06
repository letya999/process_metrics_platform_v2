"""Tests for configuration management module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config import (
    ConfigurationError,
    _interpolate_env_vars,
    get_config,
    get_enabled_projects,
    get_project,
    get_project_keys,
    load_config_from_file,
    reload_config,
)
from config.schema import (
    JiraInstanceConfig,
    PlatformConfig,
    ProjectConfig,
)


class TestEnvVarInterpolation:
    """Tests for environment variable interpolation."""

    def test_simple_interpolation(self):
        """Test basic ${VAR} interpolation."""
        with patch.dict(os.environ, {"TEST_VAR": "hello"}):
            result = _interpolate_env_vars("${TEST_VAR}")
            assert result == "hello"

    def test_interpolation_with_default(self):
        """Test ${VAR:-default} syntax when var not set."""
        # Ensure var is not set
        os.environ.pop("MISSING_VAR", None)
        result = _interpolate_env_vars("${MISSING_VAR:-default_value}")
        assert result == "default_value"

    def test_interpolation_with_default_var_exists(self):
        """Test ${VAR:-default} when var IS set."""
        with patch.dict(os.environ, {"EXISTING_VAR": "actual"}):
            result = _interpolate_env_vars("${EXISTING_VAR:-default}")
            assert result == "actual"

    def test_interpolation_in_dict(self):
        """Test interpolation in nested dict."""
        with patch.dict(os.environ, {"URL": "https://example.com"}):
            config = {"server": {"url": "${URL}"}}
            result = _interpolate_env_vars(config)
            assert result["server"]["url"] == "https://example.com"

    def test_interpolation_in_list(self):
        """Test interpolation in list."""
        with patch.dict(os.environ, {"ITEM": "value"}):
            config = ["${ITEM}", "static"]
            result = _interpolate_env_vars(config)
            assert result == ["value", "static"]

    def test_no_interpolation_needed(self):
        """Test values without variables pass through."""
        result = _interpolate_env_vars("plain text")
        assert result == "plain text"


class TestJiraInstanceConfig:
    """Tests for JiraInstanceConfig schema."""

    def test_valid_config(self):
        """Test creating valid Jira instance config."""
        config = JiraInstanceConfig(
            base_url="https://company.atlassian.net",
            email="user@company.com",
            api_token_env="JIRA_TOKEN",
        )
        assert config.base_url == "https://company.atlassian.net"
        assert config.email == "user@company.com"

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is stripped from base_url."""
        config = JiraInstanceConfig(
            base_url="https://company.atlassian.net/",
            email="user@company.com",
        )
        assert config.base_url == "https://company.atlassian.net"

    def test_invalid_base_url(self):
        """Test that invalid URL raises error."""
        with pytest.raises(ValueError, match="must start with http"):
            JiraInstanceConfig(
                base_url="company.atlassian.net",
                email="user@company.com",
            )

    def test_get_api_token_from_env(self):
        """Test getting token from environment variable."""
        config = JiraInstanceConfig(
            base_url="https://example.com",
            email="user@example.com",
            api_token_env="TEST_JIRA_TOKEN",
        )
        with patch.dict(os.environ, {"TEST_JIRA_TOKEN": "secret123"}):
            assert config.get_api_token() == "secret123"

    def test_get_api_token_direct(self):
        """Test getting direct api_token."""
        config = JiraInstanceConfig(
            base_url="https://example.com",
            email="user@example.com",
            api_token="direct_token",
        )
        assert config.get_api_token() == "direct_token"

    def test_get_api_token_missing(self):
        """Test error when token not available."""
        config = JiraInstanceConfig(
            base_url="https://example.com",
            email="user@example.com",
            api_token_env="NONEXISTENT_TOKEN_VAR",
        )
        os.environ.pop("NONEXISTENT_TOKEN_VAR", None)
        with pytest.raises(ValueError, match="not found"):
            config.get_api_token()


class TestProjectConfig:
    """Tests for ProjectConfig schema."""

    def test_valid_project(self):
        """Test creating valid project config."""
        project = ProjectConfig(key="PROJ1", name="Test Project")
        assert project.key == "PROJ1"
        assert project.jira_instance == "default"
        assert project.enabled is True

    def test_key_uppercase(self):
        """Test that key is converted to uppercase."""
        project = ProjectConfig(key="proj1")
        assert project.key == "PROJ1"

    def test_invalid_key(self):
        """Test that invalid key raises error."""
        with pytest.raises(ValueError, match="alphanumeric"):
            ProjectConfig(key="invalid@key")


class TestPlatformConfig:
    """Tests for PlatformConfig schema."""

    def test_valid_config(self):
        """Test creating valid platform config."""
        config = PlatformConfig(
            jira_instances={
                "default": JiraInstanceConfig(
                    base_url="https://example.com",
                    email="user@example.com",
                )
            },
            projects=[
                ProjectConfig(key="PROJ1", jira_instance="default"),
            ],
        )
        assert len(config.projects) == 1
        assert config.projects[0].key == "PROJ1"

    def test_invalid_instance_reference(self):
        """Test error when project references unknown instance."""
        with pytest.raises(ValueError, match="unknown Jira instance"):
            PlatformConfig(
                jira_instances={
                    "default": JiraInstanceConfig(
                        base_url="https://example.com",
                        email="user@example.com",
                    )
                },
                projects=[
                    ProjectConfig(key="PROJ1", jira_instance="nonexistent"),
                ],
            )

    def test_get_project(self):
        """Test getting project by key."""
        config = PlatformConfig(
            jira_instances={
                "default": JiraInstanceConfig(
                    base_url="https://example.com",
                    email="user@example.com",
                )
            },
            projects=[
                ProjectConfig(key="PROJ1"),
                ProjectConfig(key="PROJ2"),
            ],
        )
        project = config.get_project("proj1")  # lowercase should work
        assert project is not None
        assert project.key == "PROJ1"

    def test_get_enabled_projects(self):
        """Test filtering enabled projects."""
        config = PlatformConfig(
            jira_instances={
                "default": JiraInstanceConfig(
                    base_url="https://example.com",
                    email="user@example.com",
                )
            },
            projects=[
                ProjectConfig(key="PROJ1", enabled=True),
                ProjectConfig(key="PROJ2", enabled=False),
                ProjectConfig(key="PROJ3", enabled=True),
            ],
        )
        enabled = config.get_enabled_projects()
        assert len(enabled) == 2
        assert all(p.enabled for p in enabled)


class TestConfigLoading:
    """Tests for config file loading."""

    def test_load_from_yaml(self, tmp_path: Path):
        """Test loading config from YAML file."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(
            """
jira_instances:
  default:
    base_url: https://test.atlassian.net
    email: test@example.com
    api_token: test_token

projects:
  - key: TEST1
    name: Test Project
"""
        )
        config = load_config_from_file(config_file)
        assert "default" in config.jira_instances
        assert len(config.projects) == 1
        assert config.projects[0].key == "TEST1"

    def test_load_with_env_interpolation(self, tmp_path: Path):
        """Test loading config with env var interpolation."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(
            """
jira_instances:
  default:
    base_url: ${TEST_JIRA_URL}
    email: test@example.com
    api_token: token

projects:
  - key: TEST1
"""
        )
        with patch.dict(
            os.environ, {"TEST_JIRA_URL": "https://env-based.atlassian.net"}
        ):
            config = load_config_from_file(config_file)
            assert (
                config.jira_instances["default"].base_url
                == "https://env-based.atlassian.net"
            )

    def test_missing_config_file(self, tmp_path: Path):
        """Test error when config file doesn't exist."""
        with pytest.raises(ConfigurationError, match="not found"):
            load_config_from_file(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path: Path):
        """Test error on invalid YAML."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("invalid: yaml: content:")
        with pytest.raises(ConfigurationError, match="Invalid YAML"):
            load_config_from_file(config_file)

    def test_reload_clears_cache(self, tmp_path: Path):
        """Test that reload_config clears the cache."""
        config_file = tmp_path / "reload_test.yaml"
        config_file.write_text(
            """
jira_instances:
  default:
    base_url: https://first.atlassian.net
    email: test@example.com
    api_token: token

projects:
  - key: FIRST
"""
        )
        with patch.dict(os.environ, {"PLATFORM_CONFIG_PATH": str(config_file)}):
            # Clear any existing cache
            get_config.cache_clear()

            config1 = get_config()
            assert config1.projects[0].key == "FIRST"

            # Modify file
            config_file.write_text(
                """
jira_instances:
  default:
    base_url: https://second.atlassian.net
    email: test@example.com
    api_token: token

projects:
  - key: SECOND
"""
            )
            # Should still return cached version
            config2 = get_config()
            assert config2.projects[0].key == "FIRST"

            # After reload, should get new version
            config3 = reload_config()
            assert config3.projects[0].key == "SECOND"

            # Clear cache to not affect other tests
            get_config.cache_clear()


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_get_enabled_projects_function(self, tmp_path: Path):
        """Test get_enabled_projects helper."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
jira_instances:
  default:
    base_url: https://test.atlassian.net
    email: test@example.com
    api_token: token

projects:
  - key: ENABLED1
    enabled: true
  - key: DISABLED1
    enabled: false
  - key: ENABLED2
    enabled: true
"""
        )
        with patch.dict(os.environ, {"PLATFORM_CONFIG_PATH": str(config_file)}):
            get_config.cache_clear()
            projects = get_enabled_projects()
            assert len(projects) == 2
            assert all(p.key in ["ENABLED1", "ENABLED2"] for p in projects)
            get_config.cache_clear()

    def test_get_project_keys_function(self, tmp_path: Path):
        """Test get_project_keys helper."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
jira_instances:
  default:
    base_url: https://test.atlassian.net
    email: test@example.com
    api_token: token

projects:
  - key: PROJ1
  - key: PROJ2
    enabled: false
  - key: PROJ3
"""
        )
        with patch.dict(os.environ, {"PLATFORM_CONFIG_PATH": str(config_file)}):
            get_config.cache_clear()
            keys = get_project_keys()
            assert keys == ["PROJ1", "PROJ3"]
            get_config.cache_clear()

    def test_get_project_function(self, tmp_path: Path):
        """Test get_project helper."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
jira_instances:
  default:
    base_url: https://test.atlassian.net
    email: test@example.com
    api_token: token

projects:
  - key: MYPROJ
    name: My Project
"""
        )
        with patch.dict(os.environ, {"PLATFORM_CONFIG_PATH": str(config_file)}):
            get_config.cache_clear()
            project = get_project("myproj")
            assert project is not None
            assert project.name == "My Project"

            missing = get_project("NONEXISTENT")
            assert missing is None
            get_config.cache_clear()
