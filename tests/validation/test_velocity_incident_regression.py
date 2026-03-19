"""Regression checks for ADS 24-28 velocity incident."""

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-db-tests', default=False)",
    reason="Database tests require --run-db-tests flag",
)


def get_db_engine():
    import os

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/process_metrics",
    )
    return create_engine(db_url)


class TestVelocityIncidentRegression:
    """Ensure previously missing ADS 24-28 issues are present in clean layer."""

    @pytest.fixture
    def engine(self):
        return get_db_engine()

    def test_problem_keys_exist_in_clean_issues(self, engine):
        keys = [
            "TWAD-436",
            "TWAD-438",
            "TWAD-449",
            "TWAD-460",
            "TWAD-474",
            "TWAD-482",
            "TWAD-484",
            "TWAD-487",
        ]
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT external_key
                    FROM clean_jira.issues
                    WHERE external_key = ANY(:keys)
                    """
                ),
                {"keys": keys},
            ).fetchall()
        found = {r[0] for r in rows}
        missing = sorted(set(keys) - found)
        assert not missing, f"Missing keys in clean_jira.issues: {missing}"

    def test_problem_keys_have_sprint_relationships(self, engine):
        keys = [
            "TWAD-436",
            "TWAD-438",
            "TWAD-449",
            "TWAD-460",
            "TWAD-474",
            "TWAD-482",
            "TWAD-484",
            "TWAD-487",
        ]
        with engine.connect() as conn:
            rows_sprint_issues = conn.execute(
                text(
                    """
                    SELECT DISTINCT i.external_key
                    FROM clean_jira.sprint_issues si
                    JOIN clean_jira.issues i ON i.id = si.issue_id
                    WHERE i.external_key = ANY(:keys)
                    """
                ),
                {"keys": keys},
            ).fetchall()
            rows_changelog = conn.execute(
                text(
                    """
                    SELECT DISTINCT i.external_key
                    FROM clean_jira.sprint_issues_changelog sic
                    JOIN clean_jira.issues i ON i.id = sic.issue_id
                    WHERE i.external_key = ANY(:keys)
                    """
                ),
                {"keys": keys},
            ).fetchall()

        in_sprint_issues = {r[0] for r in rows_sprint_issues}
        in_changelog = {r[0] for r in rows_changelog}

        missing_in_sprint_issues = sorted(set(keys) - in_sprint_issues)
        missing_in_changelog = sorted(set(keys) - in_changelog)

        assert (
            not missing_in_sprint_issues
        ), f"Missing keys in clean_jira.sprint_issues: {missing_in_sprint_issues}"
        assert not missing_in_changelog, (
            "Missing keys in clean_jira.sprint_issues_changelog: "
            f"{missing_in_changelog}"
        )
