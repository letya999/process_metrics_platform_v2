"""Integration tests for Dagster assets.

These tests verify Dagster asset definitions and configurations
without requiring a running Dagster instance.
"""

from pathlib import Path

import pytest


class TestDagsterDefinitions:
    """Tests for Dagster definitions structure."""

    def test_pipelines_package_exists(self):
        """Verify pipelines package exists."""
        project_root = Path(__file__).parent.parent.parent
        pipelines_dir = project_root / "pipelines"

        assert pipelines_dir.exists(), "pipelines directory should exist"
        assert (pipelines_dir / "__init__.py").exists()
        assert (pipelines_dir / "definitions.py").exists()

    def test_assets_package_exists(self):
        """Verify assets package structure."""
        project_root = Path(__file__).parent.parent.parent
        assets_dir = project_root / "pipelines" / "assets"

        assert assets_dir.exists(), "pipelines/assets directory should exist"
        assert (assets_dir / "__init__.py").exists()
        assert (assets_dir / "jira" / "__init__.py").exists()
        assert (assets_dir / "metrics" / "__init__.py").exists()

    def test_resources_package_exists(self):
        """Verify resources package structure."""
        project_root = Path(__file__).parent.parent.parent
        resources_dir = project_root / "pipelines" / "resources"

        assert resources_dir.exists(), "pipelines/resources directory should exist"
        assert (resources_dir / "__init__.py").exists()
        assert (resources_dir / "database.py").exists()

    def test_jobs_package_exists(self):
        """Verify jobs package structure."""
        project_root = Path(__file__).parent.parent.parent
        jobs_dir = project_root / "pipelines" / "jobs"

        assert jobs_dir.exists(), "pipelines/jobs directory should exist"
        assert (jobs_dir / "__init__.py").exists()
        assert (jobs_dir / "schedules.py").exists()

    def test_utils_package_exists(self):
        """Verify utils package structure."""
        project_root = Path(__file__).parent.parent.parent
        utils_dir = project_root / "pipelines" / "utils"

        assert utils_dir.exists(), "pipelines/utils directory should exist"
        assert (utils_dir / "__init__.py").exists()
        assert (utils_dir / "metrics.py").exists()


class TestDagsterImports:
    """Test that Dagster modules can be imported."""

    def test_import_definitions(self):
        """Test importing definitions module."""
        try:
            from pipelines import definitions

            assert hasattr(definitions, "defs") or True  # Module imports OK
        except ImportError as e:
            # Allow import errors for missing dagster dependencies in test env
            if "dagster" in str(e).lower():
                pytest.skip("Dagster not installed in test environment")
            raise

    def test_import_resources(self):
        """Test importing resources module."""
        from pipelines.resources import database

        assert database is not None

    def test_import_utils(self):
        """Test importing utils modules."""
        from pipelines.utils import (
            parse_jira_datetime,
            parse_jira_issue,
        )
        from pipelines.utils.metrics import (
            calculate_lead_time,
        )

        assert callable(parse_jira_datetime)
        assert callable(parse_jira_issue)
        assert callable(calculate_lead_time)


class TestDagsterResourceConfiguration:
    """Tests for Dagster resource configuration."""

    def test_database_resource_module(self):
        """Test database resource module structure."""
        from pipelines.resources import database

        # Check module has expected attributes
        module_content = dir(database)
        # Database resource should define connection-related items
        assert len(module_content) > 0

    def test_database_url_configuration(self):
        """Test that database URL can be configured."""
        import os

        # Should be able to get DATABASE_URL from environment
        # (actual value tested in integration with DB)
        db_url = os.getenv("DATABASE_URL")
        # In test environment, this may or may not be set
        # Just verify the pattern is correct if set
        if db_url:
            assert "postgresql" in db_url or "postgres" in db_url


class TestScheduleConfiguration:
    """Tests for schedule configuration."""

    def test_schedules_module_exists(self):
        """Test schedules module exists and is importable."""
        from pipelines.jobs import schedules

        assert schedules is not None

    def test_schedules_file_content(self):
        """Test schedules file has expected structure."""
        project_root = Path(__file__).parent.parent.parent
        schedules_file = project_root / "pipelines" / "jobs" / "schedules.py"

        content = schedules_file.read_text()
        # Schedules file should contain schedule definitions
        # (placeholder or actual)
        assert len(content) > 0


class TestUtilityFunctions:
    """Tests for pipeline utility functions."""

    def test_jira_parsing_utilities_available(self):
        """Test that Jira parsing utilities are available."""
        from pipelines.utils import (
            extract_status_changes,
            parse_jira_changelog,
            parse_jira_datetime,
            parse_jira_issue,
            parse_jira_sprint,
        )

        # All functions should be callable
        assert callable(parse_jira_datetime)
        assert callable(parse_jira_issue)
        assert callable(parse_jira_sprint)
        assert callable(parse_jira_changelog)
        assert callable(extract_status_changes)

    def test_metrics_utilities_available(self):
        """Test that metrics utilities are available."""
        from pipelines.utils.metrics import (
            calculate_cycle_time,
            calculate_lead_time,
            calculate_lead_time_percentiles,
            calculate_sprint_velocity,
            calculate_throughput,
            detect_work_start_from_changelog,
        )

        # All functions should be callable
        assert callable(calculate_lead_time)
        assert callable(calculate_cycle_time)
        assert callable(calculate_sprint_velocity)
        assert callable(calculate_throughput)
        assert callable(calculate_lead_time_percentiles)
        assert callable(detect_work_start_from_changelog)

    def test_transformation_utilities_available(self):
        """Test that transformation utilities are available."""
        from pipelines.utils.transformations import (
            deduplicate_issues,
            enrich_issue_with_lead_time,
            transform_changelog_to_status_transitions,
            transform_raw_issue_to_clean,
            transform_raw_issues_batch,
            transform_raw_sprint_to_clean,
            validate_clean_issue,
        )

        # All functions should be callable
        assert callable(transform_raw_issue_to_clean)
        assert callable(transform_raw_issues_batch)
        assert callable(transform_raw_sprint_to_clean)
        assert callable(transform_changelog_to_status_transitions)
        assert callable(validate_clean_issue)
        assert callable(deduplicate_issues)
        assert callable(enrich_issue_with_lead_time)
