"""Integration tests for Dagster assets.

Tests the Dagster assets can be loaded and executed.
"""

from unittest.mock import MagicMock, patch


class TestJiraRawAsset:
    """Tests for raw Jira data asset."""

    def test_raw_jira_data_skips_without_credentials(self, jira_env_vars, monkeypatch):
        """Test that raw_jira_data skips when credentials not configured."""
        # Remove credentials
        monkeypatch.delenv("JIRA_BASE_URL", raising=False)
        monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

        from pipelines.assets.jira.raw import raw_jira_data

        # Create mock context
        mock_context = MagicMock()
        mock_context.log = MagicMock()

        result = raw_jira_data.op.compute_fn.decorated_fn(mock_context)

        assert result["status"] == "skipped"
        assert result["reason"] == "credentials_not_configured"

    @patch("pipelines.assets.jira.raw.validate_jira_credentials")
    @patch("pipelines.assets.jira.raw.run_jira_pipeline")
    def test_raw_jira_data_runs_with_credentials(
        self, mock_pipeline, mock_validate_credentials, jira_env_vars, monkeypatch
    ):
        """Test that raw_jira_data runs when credentials configured."""
        monkeypatch.setenv("JIRA_PROJECTS", "PROJ")
        mock_pipeline.return_value = {
            "pipeline_name": "jira_raw",
            "destination": "postgres",
            "dataset_name": "raw_jira",
            "load_info": "Success",
            "row_counts": {"issues": 100},
        }

        from pipelines.assets.jira.raw import raw_jira_data

        mock_context = MagicMock()
        mock_context.log = MagicMock()

        result = raw_jira_data.op.compute_fn.decorated_fn(mock_context)

        assert result["status"] == "success"
        assert result["details"][0]["pipeline_name"] == "jira_raw"
        assert mock_pipeline.called
        mock_validate_credentials.assert_called_once()


class TestJiraCleanAssets:
    """Tests for clean Jira data assets."""

    def test_clean_jira_issues_executes(self, mock_database_resource):
        """Test that clean_jira_issues asset can execute."""
        from pipelines.assets.jira.clean import _utils as clean_utils
        from pipelines.assets.jira.clean import clean_jira_issues

        mock_context = MagicMock()
        mock_context.log = MagicMock()

        # Keep table-exists checks deterministic and isolated for this test run.
        clean_utils._TABLE_EXISTS_CACHE.clear()

        # Mock DB responses in the same order queries are executed in asset code.
        def _result(*, first=None, scalar=None, fetchall=None):
            result = MagicMock()
            result.first.return_value = first
            result.scalar.return_value = scalar
            result.fetchall.return_value = fetchall if fetchall is not None else []
            return result

        mock_conn = MagicMock()
        execute_results = iter(
            [
                _result(first=("integration-id",)),  # system integration lookup
                _result(),  # sync users
                _result(scalar=True),  # history table exists check
                _result(),  # extract users from changelog
                _result(),  # extract users from issue fields
                _result(fetchall=[]),  # optional columns lookup
                _result(scalar=0),  # dropped issues count
                _result(scalar=0),  # null created date count
                _result(fetchall=[]),  # insert/update issues returning ids
            ]
        )

        def _execute_side_effect(*_args, **_kwargs):
            # Keep integration test resilient to benign extra SQL checks in asset code.
            try:
                return next(execute_results)
            except StopIteration:
                return _result(fetchall=[], scalar=0)

        mock_conn.execute.side_effect = _execute_side_effect
        mock_database_resource.get_engine.return_value.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_database_resource.get_engine.return_value.connect.return_value.__exit__ = (
            MagicMock(return_value=False)
        )

        result = clean_jira_issues.op.compute_fn.decorated_fn(
            mock_context, mock_database_resource
        )

        assert result["status"] == "success"

    def test_clean_jira_sprints_executes(self, mock_database_resource):
        """Test that clean_jira_sprints asset can execute."""
        from pipelines.assets.jira.clean import clean_jira_sprints

        mock_context = MagicMock()
        mock_context.log = MagicMock()

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_database_resource.get_engine.return_value.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_database_resource.get_engine.return_value.connect.return_value.__exit__ = (
            MagicMock(return_value=False)
        )

        result = clean_jira_sprints.op.compute_fn.decorated_fn(
            mock_context, mock_database_resource
        )

        assert result["status"] == "success"


class TestMetricsAssets:
    """Tests for metrics refresh assets."""

    def test_metrics_lead_time_executes(self, mock_database_resource):
        """Test that metrics_lead_time asset can execute."""
        from pipelines.assets.metrics.refresh import metrics_lead_time

        mock_context = MagicMock()
        mock_context.log = MagicMock()

        mock_conn = MagicMock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = {
            "total_issues": 100,
            "avg_lead_time_days": 5.5,
            "min_lead_time_days": 0.5,
            "max_lead_time_days": 30.0,
        }
        mock_database_resource.get_engine.return_value.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_database_resource.get_engine.return_value.connect.return_value.__exit__ = (
            MagicMock(return_value=False)
        )

        result = metrics_lead_time.op.compute_fn.decorated_fn(
            mock_context, mock_database_resource
        )

        assert result["status"] == "success"
        assert result["table"] == "fact_values"

    def test_metrics_velocity_executes(self, mock_database_resource):
        """Test that metrics_velocity asset can execute."""
        from pipelines.assets.metrics.refresh import metrics_velocity

        mock_context = MagicMock()
        mock_context.log = MagicMock()

        mock_conn = MagicMock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = {
            "total_sprints": 10,
            "avg_completion_rate": 75.0,
            "avg_issues_per_sprint": 12.0,
        }
        mock_database_resource.get_engine.return_value.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_database_resource.get_engine.return_value.connect.return_value.__exit__ = (
            MagicMock(return_value=False)
        )

        result = metrics_velocity.op.compute_fn.decorated_fn(
            mock_context, mock_database_resource
        )

        assert result["status"] == "success"
        assert result["table"] == "fact_values"

    def test_metrics_throughput_executes(self, mock_database_resource):
        """Test that metrics_throughput asset can execute."""
        from pipelines.assets.metrics.refresh import metrics_throughput

        mock_context = MagicMock()
        mock_context.log = MagicMock()

        mock_conn = MagicMock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = {
            "days_with_data": 30,
            "total_completed": 150,
            "avg_daily_throughput": 5.0,
        }
        mock_database_resource.get_engine.return_value.connect.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_database_resource.get_engine.return_value.connect.return_value.__exit__ = (
            MagicMock(return_value=False)
        )

        result = metrics_throughput.op.compute_fn.decorated_fn(
            mock_context, mock_database_resource
        )

        assert result["status"] == "success"
        assert result["source"] == "fact_values"


class TestDagsterDefinitions:
    """Tests for Dagster definitions loading."""

    def test_definitions_load(self):
        """Test that Dagster definitions can be loaded."""
        from pipelines.definitions import defs

        assert defs is not None
        assert len(defs.assets) > 0

    def test_definitions_have_resources(self):
        """Test that definitions have required resources."""
        from pipelines.definitions import defs

        # Check resources are defined
        assert "database" in defs.resources

    def test_definitions_have_jobs(self):
        """Test that definitions have jobs."""
        from pipelines.definitions import defs

        assert len(defs.jobs) > 0

    def test_definitions_have_schedules(self):
        """Test that definitions have schedules."""
        from pipelines.definitions import defs

        assert len(defs.schedules) > 0

    def test_jira_sync_job_exists(self):
        """Test that jira_sync_job is defined."""
        from pipelines.jobs.schedules import jira_sync_job

        assert jira_sync_job is not None
        assert jira_sync_job.name == "jira_sync_job"

    def test_metrics_refresh_job_exists(self):
        """Test that metrics_refresh_job is defined."""
        from pipelines.jobs.schedules import metrics_refresh_job

        assert metrics_refresh_job is not None
        assert metrics_refresh_job.name == "metrics_refresh_job"
