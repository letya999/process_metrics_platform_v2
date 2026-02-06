"""Pydantic schemas for platform configuration validation.

This module defines the structure of the projects.yaml configuration file.
"""

import os
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class JiraInstanceConfig(BaseModel):
    """Configuration for a Jira instance connection."""

    base_url: str = Field(
        ...,
        description="Jira Cloud/Server URL (e.g., https://company.atlassian.net)",
    )
    email: str = Field(
        ...,
        description="Email for Jira authentication",
    )
    api_token_env: str = Field(
        default="JIRA_API_TOKEN",
        description="Environment variable name containing the API token",
    )

    # Optional: direct token (not recommended for production)
    api_token: str | None = Field(
        default=None,
        description="Direct API token (only for development, prefer api_token_env)",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Ensure base_url is a valid URL and remove trailing slash."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")

    def get_api_token(self) -> str:
        """Get API token from environment or direct config.

        Returns:
            API token string

        Raises:
            ValueError: If token is not available
        """
        # First check direct token (for dev/testing)
        if self.api_token:
            return self.api_token

        # Then check environment variable
        token = os.getenv(self.api_token_env)
        if token:
            return token

        raise ValueError(
            f"Jira API token not found. Set {self.api_token_env} environment variable "
            "or provide api_token in config."
        )


class ProjectConfig(BaseModel):
    """Configuration for a single project to sync."""

    key: str = Field(
        ...,
        description="Jira project key (e.g., 'PROJ')",
        min_length=1,
        max_length=50,
    )
    name: str | None = Field(
        default=None,
        description="Human-readable project name (optional)",
    )
    jira_instance: str = Field(
        default="default",
        description="Reference to jira_instances key",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this project should be synced",
    )
    sync_schedule: str | None = Field(
        default=None,
        description="Custom cron schedule for this project (optional)",
    )
    # Additional JQL filter for this project
    jql_filter: str | None = Field(
        default=None,
        description="Additional JQL filter to apply when syncing issues",
    )

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Ensure key is uppercase alphanumeric."""
        v = v.upper().strip()
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Project key must be alphanumeric (with _ or - allowed)")
        return v


class SyncConfig(BaseModel):
    """Global synchronization settings."""

    mode: Literal["sequential", "parallel"] = Field(
        default="sequential",
        description="How to sync multiple projects: sequential or parallel",
    )
    max_parallel: int = Field(
        default=3,
        description="Maximum number of parallel syncs (when mode=parallel)",
        ge=1,
        le=10,
    )
    retry_failed: bool = Field(
        default=True,
        description="Automatically retry failed project syncs",
    )
    retry_count: int = Field(
        default=2,
        description="Number of retries for failed syncs",
        ge=0,
        le=5,
    )


class PlatformConfig(BaseModel):
    """Root configuration for the platform."""

    jira_instances: dict[str, JiraInstanceConfig] = Field(
        default_factory=lambda: {},
        description="Named Jira instance configurations",
    )
    projects: list[ProjectConfig] = Field(
        default_factory=list,
        description="List of projects to sync",
    )
    sync: SyncConfig = Field(
        default_factory=SyncConfig,
        description="Global sync settings",
    )

    @model_validator(mode="after")
    def validate_project_instances(self) -> "PlatformConfig":
        """Ensure all projects reference valid Jira instances."""
        instance_names = set(self.jira_instances.keys())

        for project in self.projects:
            if project.jira_instance not in instance_names:
                raise ValueError(
                    f"Project '{project.key}' references unknown Jira instance "
                    f"'{project.jira_instance}'. Available: {instance_names}"
                )

        return self

    def get_project(self, key: str) -> ProjectConfig | None:
        """Get project configuration by key.

        Args:
            key: Project key (case-insensitive)

        Returns:
            ProjectConfig if found, None otherwise
        """
        key_upper = key.upper()
        for project in self.projects:
            if project.key == key_upper:
                return project
        return None

    def get_jira_instance(self, name: str) -> JiraInstanceConfig | None:
        """Get Jira instance configuration by name.

        Args:
            name: Instance name from jira_instances dict

        Returns:
            JiraInstanceConfig if found, None otherwise
        """
        return self.jira_instances.get(name)

    def get_project_instance(self, project: ProjectConfig) -> JiraInstanceConfig:
        """Get the Jira instance for a project.

        Args:
            project: ProjectConfig object

        Returns:
            JiraInstanceConfig for the project

        Raises:
            ValueError: If instance not found
        """
        instance = self.get_jira_instance(project.jira_instance)
        if instance is None:
            raise ValueError(
                f"Jira instance '{project.jira_instance}' not found for project "
                f"'{project.key}'"
            )
        return instance

    def get_enabled_projects(self) -> list[ProjectConfig]:
        """Get list of enabled projects.

        Returns:
            List of ProjectConfig where enabled=True
        """
        return [p for p in self.projects if p.enabled]
