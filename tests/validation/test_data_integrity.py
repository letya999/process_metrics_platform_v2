"""Data integrity validation tests.

Tests data quality across raw → clean → metrics layers.
These tests are designed to run against a database with actual data.
"""

import pytest
from sqlalchemy import create_engine, text

# Skip these tests if no database is available
pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-db-tests', default=False)",
    reason="Database tests require --run-db-tests flag",
)


def get_db_engine():
    """Get database engine from environment."""
    import os

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/process_metrics",
    )
    return create_engine(db_url)


class TestRawLayerIntegrity:
    """Tests for raw data layer integrity."""

    @pytest.fixture
    def engine(self):
        """Get database engine."""
        return get_db_engine()

    def test_raw_jira_issues_has_data(self, engine):
        """Test that raw_jira.issues has data after load."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'raw_jira' AND table_name = 'issues'
                )
            """
                )
            )
            table_exists = result.scalar()

            assert table_exists, "raw_jira.issues table must exist"
            result = conn.execute(text("SELECT count(*) FROM raw_jira.issues"))
            count = result.scalar()
            assert count > 0, "raw_jira.issues should contain data"

    def test_raw_jira_projects_has_data(self, engine):
        """Test that raw_jira.projects has data after load."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'raw_jira' AND table_name = 'projects'
                )
            """
                )
            )
            table_exists = result.scalar()

            assert table_exists, "raw_jira.projects table must exist"
            result = conn.execute(text("SELECT count(*) FROM raw_jira.projects"))
            count = result.scalar()
            assert count > 0, "raw_jira.projects should contain data"


class TestCleanLayerIntegrity:
    """Tests for clean data layer integrity."""

    @pytest.fixture
    def engine(self):
        """Get database engine."""
        return get_db_engine()

    def test_clean_issues_no_orphans(self, engine):
        """Test that all clean issues have valid project_id."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.issues i
                WHERE NOT EXISTS (
                    SELECT 1 FROM clean_jira.projects p
                    WHERE p.id = i.project_id
                )
            """
                )
            )
            orphan_count = result.scalar()

        assert orphan_count == 0, f"Found {orphan_count} orphan issues"

    def test_clean_issues_required_fields(self, engine):
        """Test that all clean issues have required fields."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.issues
                WHERE external_key IS NULL
                   OR summary IS NULL
                   OR type_id IS NULL
                   OR status_id IS NULL
                   OR jira_created_at IS NULL
            """
                )
            )
            invalid_count = result.scalar()

        assert invalid_count == 0, f"Found {invalid_count} issues with missing fields"

    def test_clean_issues_valid_type_id(self, engine):
        """Test that all issues reference valid issue types."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.issues i
                WHERE NOT EXISTS (
                    SELECT 1 FROM clean_jira.issue_types t
                    WHERE t.id = i.type_id
                )
            """
                )
            )
            invalid_count = result.scalar()

        assert invalid_count == 0, f"Found {invalid_count} issues with invalid type_id"

    def test_clean_issues_valid_status_id(self, engine):
        """Test that all issues reference valid statuses."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.issues i
                WHERE NOT EXISTS (
                    SELECT 1 FROM clean_jira.issue_statuses s
                    WHERE s.id = i.status_id
                )
            """
                )
            )
            invalid_count = result.scalar()

        assert (
            invalid_count == 0
        ), f"Found {invalid_count} issues with invalid status_id"

    def test_clean_sprints_valid_dates(self, engine):
        """Test that sprints have valid date ranges."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.sprints
                WHERE start_date IS NOT NULL
                  AND end_date IS NOT NULL
                  AND start_date > end_date
            """
                )
            )
            invalid_count = result.scalar()

        assert (
            invalid_count == 0
        ), f"Found {invalid_count} sprints with start > end date"

    def test_clean_sprints_no_orphans(self, engine):
        """Test that all sprints belong to a valid project."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.sprints s
                WHERE NOT EXISTS (
                    SELECT 1 FROM clean_jira.projects p
                    WHERE p.id = s.project_id
                )
            """
                )
            )
            orphan_count = result.scalar()

        assert orphan_count == 0, f"Found {orphan_count} orphan sprints"


class TestMetricsLayerIntegrity:
    """Tests for metrics integrity via generic fact view."""

    @pytest.fixture
    def engine(self):
        """Get database engine."""
        return get_db_engine()

    def test_mv_lead_time_no_nulls(self, engine):
        """Test that lead_time_days values are populated in v_facts."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM metrics.v_facts
                WHERE calc_code = 'lead_time_days'
                  AND slice_rule_name IS NULL
                  AND value IS NULL
            """
                )
            )
            null_count = result.scalar()

        assert null_count == 0, f"Found {null_count} records with NULL lead_time"

    def test_mv_lead_time_positive(self, engine):
        """Test that lead_time_days values are non-negative in v_facts."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM metrics.v_facts
                WHERE calc_code = 'lead_time_days'
                  AND slice_rule_name IS NULL
                  AND value < 0
            """
                )
            )
            negative_count = result.scalar()

        assert (
            negative_count == 0
        ), f"Found {negative_count} records with negative lead_time"

    def test_velocity_completion_rate_valid(self, engine):
        """Test that completion rates derived from v_facts are between 0 and 100."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                WITH sprint_metrics AS (
                    SELECT
                        project_key,
                        entity_id AS sprint_id,
                        full_date,
                        MAX(CASE WHEN calc_code = 'velocity_planned_count' THEN value END) AS planned_issues,
                        MAX(CASE WHEN calc_code = 'velocity_completed_count' THEN value END) AS completed_issues
                    FROM metrics.v_facts
                    WHERE metric_code = 'velocity'
                      AND slice_rule_name IS NULL
                    GROUP BY project_key, entity_id, full_date
                )
                SELECT count(*)
                FROM sprint_metrics
                WHERE planned_issues > 0
                  AND (
                      (completed_issues / planned_issues * 100) < 0
                      OR (completed_issues / planned_issues * 100) > 100
                  )
            """
                )
            )
            invalid_count = result.scalar()

        assert (
            invalid_count == 0
        ), f"Found {invalid_count} records with invalid completion_rate"

    def test_velocity_consistent_counts(self, engine):
        """Test that velocity completed issues do not exceed planned issues."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                WITH sprint_metrics AS (
                    SELECT
                        project_key,
                        entity_id AS sprint_id,
                        full_date,
                        MAX(CASE WHEN calc_code = 'velocity_planned_count' THEN value END) AS planned_issues,
                        MAX(CASE WHEN calc_code = 'velocity_completed_count' THEN value END) AS completed_issues
                    FROM metrics.v_facts
                    WHERE metric_code = 'velocity'
                      AND slice_rule_name IS NULL
                    GROUP BY project_key, entity_id, full_date
                )
                SELECT count(*)
                FROM sprint_metrics
                WHERE completed_issues > planned_issues
            """
                )
            )
            invalid_count = result.scalar()

        assert (
            invalid_count == 0
        ), f"Found {invalid_count} records where completed > total"

    def test_mv_throughput_no_future_dates(self, engine):
        """Test that throughput records in v_facts don't have future dates."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM metrics.v_facts
                WHERE calc_code = 'throughput_count'
                  AND slice_rule_name IS NULL
                  AND full_date > CURRENT_DATE
            """
                )
            )
            future_count = result.scalar()

        assert future_count == 0, f"Found {future_count} records with future dates"

    def test_mv_throughput_positive_counts(self, engine):
        """Test that throughput counts in v_facts are positive."""
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT count(*) FROM metrics.v_facts
                WHERE calc_code = 'throughput_count'
                  AND slice_rule_name IS NULL
                  AND value <= 0
            """
                )
            )
            invalid_count = result.scalar()

        assert invalid_count == 0, f"Found {invalid_count} records with invalid counts"


class TestCrossLayerConsistency:
    """Tests for consistency across data layers."""

    @pytest.fixture
    def engine(self):
        """Get database engine."""
        return get_db_engine()

    def test_metrics_match_clean_layer(self, engine):
        """Test that lead_time facts count matches resolved issues in clean layer."""
        with engine.connect() as conn:
            # Count resolved issues in clean layer
            clean_result = conn.execute(
                text(
                    """
                SELECT count(*) FROM clean_jira.issues i
                JOIN clean_jira.issue_statuses s ON i.status_id = s.id
                WHERE s.category = 'done'
            """
                )
            )
            clean_count = clean_result.scalar() or 0

            # Count in lead_time facts
            metrics_result = conn.execute(
                text(
                    """
                    SELECT count(*) FROM metrics.v_facts
                    WHERE calc_code = 'lead_time_days'
                      AND slice_rule_name IS NULL
                    """
                )
            )
            metrics_count = metrics_result.scalar() or 0

        assert (
            clean_count == metrics_count
        ), f"Mismatch: clean={clean_count}, metrics={metrics_count}"
