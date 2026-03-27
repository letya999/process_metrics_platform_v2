"""Dagster partitions for multi-project support.

This module defines dynamic partitions that allow running pipelines
on individual projects or all projects at once.
"""

from dagster import (
    DynamicPartitionsDefinition,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    sensor,
)

# Dynamic partitions for projects
# Partitions are managed at runtime based on config file
project_partitions = DynamicPartitionsDefinition(name="jira_projects")


def get_project_partition_keys() -> list[str]:
    """Get list of enabled project keys.

    Priority:
    1. platform.projects in DB (via tool_integrations)
    2. config/projects.yaml (legacy fallback)
    3. JIRA_PROJECTS env var (last resort)
    """
    import os

    try:
        from pipelines.utils.db_config import get_active_projects_from_db

        keys = [p.project_key for p in get_active_projects_from_db()]
        if keys:
            return keys
    except Exception:  # noqa: S110
        pass

    try:
        from config import get_enabled_projects

        keys = [p.key for p in get_enabled_projects()]
        if keys:
            return keys
    except Exception:  # noqa: S110
        pass

    projects_str = os.getenv("JIRA_PROJECTS", "")
    if projects_str:
        return [p.strip() for p in projects_str.split(",") if p.strip()]
    return []


@sensor(name="sync_project_partitions_sensor")
def sync_project_partitions_sensor(
    context: SensorEvaluationContext,
) -> SensorResult | SkipReason:
    """Sensor that syncs project partitions with configuration.

    This sensor runs periodically and ensures that Dagster's dynamic
    partitions match the projects defined in config/projects.yaml.

    It will:
    - Add new partitions for new projects
    - NOT remove partitions for removed projects (to preserve history)
    """
    try:
        config_keys = set(get_project_partition_keys())

        if not config_keys:
            return SkipReason("No projects configured")

        # Get existing partitions
        existing_keys = set(
            context.instance.get_dynamic_partitions(project_partitions.name)
        )

        # Find new projects to add
        new_keys = config_keys - existing_keys

        if not new_keys:
            return SkipReason("All project partitions already exist")

        # Add new partitions
        context.instance.add_dynamic_partitions(
            partitions_def_name=project_partitions.name,
            partition_keys=list(new_keys),
        )

        context.log.info(f"Added {len(new_keys)} new project partitions: {new_keys}")

        return SensorResult(
            run_requests=[],  # No immediate runs, just partition sync
            dynamic_partitions_requests=[],
        )

    except Exception as e:
        context.log.error(f"Failed to sync project partitions: {e}")
        return SkipReason(f"Error syncing partitions: {e}")


def ensure_project_partitions_exist(context) -> None:
    """Ensure all project partitions exist in Dagster.

    Call this at asset execution time to ensure partitions are created.
    This is a fallback if the sensor hasn't run yet.

    Args:
        context: Dagster execution context with access to instance
    """
    try:
        config_keys = set(get_project_partition_keys())
        existing_keys = set(
            context.instance.get_dynamic_partitions(project_partitions.name)
        )

        new_keys = config_keys - existing_keys
        if new_keys:
            context.instance.add_dynamic_partitions(
                partitions_def_name=project_partitions.name,
                partition_keys=list(new_keys),
            )
            context.log.info(f"Created project partitions: {new_keys}")
    except Exception as e:
        context.log.warning(f"Could not ensure partitions exist: {e}")
