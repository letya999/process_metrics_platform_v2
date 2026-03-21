"""
Unit tests for Time to Market (TTM) calculation logic.
TTM is now a filtered version of Lead Time.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import polars as pl

from pipelines.calculations import lead_time as lead_time_logic
from pipelines.calculations.time_to_market import load_issue_type_filter


class TestTimeToMarketLogic:
    @patch("pipelines.calculations.time_to_market.read_table")
    def test_load_issue_type_filter_returns_default_when_no_settings(
        self, mock_read_table
    ):
        """Mock engine returns empty DataFrame -> returns ["Epic"]"""
        mock_read_table.return_value = pl.DataFrame()

        # We pass a MagicMock as engine because read_table is mocked anyway
        result = load_issue_type_filter(MagicMock(), "ttm_days")
        assert result == ["Epic"]

    @patch("pipelines.calculations.time_to_market.read_table")
    def test_load_issue_type_filter_returns_global_setting(self, mock_read_table):
        """Mock engine returns global setting {"include": ["Epic", "Feature"]}"""
        mock_read_table.return_value = pl.DataFrame(
            {
                "project_id": [None],
                "settings_json": ['{"include": ["Epic", "Feature"]}'],
            }
        )

        result = load_issue_type_filter(MagicMock(), "ttm_days")
        assert result == ["Epic", "Feature"]

    @patch("pipelines.calculations.time_to_market.read_table")
    def test_load_issue_type_filter_prefers_project_specific_over_global(
        self, mock_read_table
    ):
        """Priority: project-specific setting > global setting."""
        # read_table returns both when project_id is provided in query
        mock_read_table.return_value = pl.DataFrame(
            {
                "project_id": ["P1", None],
                "settings_json": ['{"include": ["Story"]}', '{"include": ["Epic"]}'],
            }
        )

        result = load_issue_type_filter(MagicMock(), "ttm_days", project_id="P1")
        assert result == ["Story"]

    def test_ttm_uses_same_logic_as_lead_time(self):
        """Scenario: Epic (included) and Story (excluded by type filter)."""
        issues = pl.DataFrame(
            {
                "id": ["E1", "S1"],
                "project_id": ["P1", "P1"],
                "key": ["K1", "K2"],
                "type_name": ["Epic", "Story"],
                "jira_created_at": [datetime(2024, 1, 1)] * 2,
                "jira_resolved_at": [datetime(2024, 1, 10)] * 2,
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["E1", "E1", "S1", "S1"],
                "from_status_id": [None, "IP", None, "IP"],
                "to_status_id": ["IP", "DONE", "IP", "DONE"],
                "changed_at": [
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 5),  # E1: 3 days
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 5),  # S1: 3 days
                ],
            }
        )

        type_filter = ["Epic"]

        # In the asset, we filter issues by type first
        filtered_issues = issues.filter(pl.col("type_name").is_in(type_filter))

        result = lead_time_logic.calculate_lead_time_per_issue(
            filtered_issues,
            status_changelog,
            middle_status_ids=["IP"],
            end_status_ids=["DONE"],
        )

        assert len(result) == 1
        assert result["issue_id"][0] == "E1"
        assert result["lead_time_days"][0] == 3.0

    def test_ttm_excludes_issues_without_commitment_zone_transition(self):
        """Epic that went To Do -> Done only (no In Progress) is excluded."""
        issues = pl.DataFrame(
            {
                "id": ["E1"],
                "project_id": ["P1"],
                "key": ["K1"],
                "type_name": ["Epic"],
                "jira_created_at": [datetime(2024, 1, 1)],
                "jira_resolved_at": [datetime(2024, 1, 10)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["E1"],
                "from_status_id": [None],
                "to_status_id": ["DONE"],
                "changed_at": [datetime(2024, 1, 5)],
            }
        )

        result = lead_time_logic.calculate_lead_time_per_issue(
            issues, status_changelog, middle_status_ids=["IP"], end_status_ids=["DONE"]
        )

        assert result.is_empty()

    def test_ttm_uses_ceil_rounding(self):
        """Epic with 5 hours elapsed -> lead_time_days == 1.0"""
        issues = pl.DataFrame(
            {
                "id": ["E1"],
                "project_id": ["P1"],
                "key": ["K1"],
                "type_name": ["Epic"],
                "jira_created_at": [datetime(2024, 1, 1)],
                "jira_resolved_at": [datetime(2024, 1, 1, 5, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["E1", "E1"],
                "from_status_id": [None, "IP"],
                "to_status_id": ["IP", "DONE"],
                "changed_at": [
                    datetime(2024, 1, 1, 0, 0),
                    datetime(2024, 1, 1, 5, 0),
                ],
            }
        )

        result = lead_time_logic.calculate_lead_time_per_issue(
            issues, status_changelog, middle_status_ids=["IP"], end_status_ids=["DONE"]
        )

        assert result["lead_time_days"][0] == 1.0
