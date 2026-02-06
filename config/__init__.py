"""Configuration management for Process Metrics Platform.

This module provides configuration loading from YAML files with support for:
- Environment variable interpolation (${VAR_NAME} syntax)
- Multiple Jira instances with different credentials
- Project-level configuration
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.schema import PlatformConfig, ProjectConfig

# Default config file locations
CONFIG_DIR = Path(__file__).parent
DEFAULT_CONFIG_FILE = CONFIG_DIR / "projects.yaml"
EXAMPLE_CONFIG_FILE = CONFIG_DIR / "projects.example.yaml"


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""

    pass


def _interpolate_env_vars(value: Any) -> Any:
    """Recursively interpolate environment variables in config values.

    Supports ${VAR_NAME} and ${VAR_NAME:-default} syntax.

    Args:
        value: Configuration value (string, dict, list, or primitive)

    Returns:
        Value with environment variables replaced
    """
    if isinstance(value, str):
        # Pattern: ${VAR_NAME} or ${VAR_NAME:-default}
        pattern = r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}"

        def replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.getenv(var_name)
            if env_value is not None:
                return env_value
            if default is not None:
                return default
            # Return original placeholder if not found (will fail validation)
            return match.group(0)

        return re.sub(pattern, replace, value)

    elif isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [_interpolate_env_vars(item) for item in value]

    return value


def load_config_from_file(config_path: Path | str | None = None) -> PlatformConfig:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to YAML config file. If None, uses default location.

    Returns:
        Validated PlatformConfig object

    Raises:
        ConfigurationError: If config file is missing or invalid
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_FILE

    config_path = Path(config_path)

    if not config_path.exists():
        # Try example config as fallback (for development)
        if EXAMPLE_CONFIG_FILE.exists():
            config_path = EXAMPLE_CONFIG_FILE
        else:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}\n"
                f"Please copy {EXAMPLE_CONFIG_FILE} to {DEFAULT_CONFIG_FILE} "
                "and configure your projects."
            )

    try:
        with open(config_path, encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {e}") from e

    # Interpolate environment variables
    interpolated_config = _interpolate_env_vars(raw_config)

    # Validate with Pydantic
    try:
        return PlatformConfig.model_validate(interpolated_config)
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_config() -> PlatformConfig:
    """Get cached platform configuration.

    Uses LRU cache to avoid re-reading config file on every call.
    Call get_config.cache_clear() to force reload.

    Returns:
        Validated PlatformConfig object
    """
    # Check for config path override via environment
    config_path = os.getenv("PLATFORM_CONFIG_PATH")
    return load_config_from_file(config_path)


def get_enabled_projects() -> list[ProjectConfig]:
    """Get list of enabled projects from configuration.

    Returns:
        List of ProjectConfig objects where enabled=True
    """
    config = get_config()
    return [p for p in config.projects if p.enabled]


def get_project_keys() -> list[str]:
    """Get list of enabled project keys.

    Returns:
        List of project key strings
    """
    return [p.key for p in get_enabled_projects()]


def get_project(key: str) -> ProjectConfig | None:
    """Get project configuration by key.

    Args:
        key: Project key (e.g., "PROJ1")

    Returns:
        ProjectConfig if found, None otherwise
    """
    config = get_config()
    return config.get_project(key)


def reload_config() -> PlatformConfig:
    """Force reload of configuration from file.

    Clears the cache and re-reads the config file.

    Returns:
        Fresh PlatformConfig object
    """
    get_config.cache_clear()
    return get_config()


# For backward compatibility with code that reads from env
def get_jira_projects_from_config() -> list[str] | None:
    """Get Jira project keys from config, with fallback to env var.

    This provides backward compatibility during migration from
    env-based to config-based project management.

    Returns:
        List of project keys, or None if not configured
    """
    try:
        keys = get_project_keys()
        if keys:
            return keys
    except ConfigurationError:
        pass

    # Fallback to environment variable
    projects_str = os.getenv("JIRA_PROJECTS", "")
    if projects_str:
        return [p.strip() for p in projects_str.split(",") if p.strip()]

    return None
