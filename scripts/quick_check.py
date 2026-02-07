"""Quick check of sprint_issues vs changelog coverage."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # For Sprint 36
    sprint = conn.execute(
        text(
            """
        SELECT s.id FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
    """
        )
    ).fetchone()
    sprint_id = sprint[0]

    # Count in sprint_issues (excluding sub-tasks)
    si_count = conn.execute(
        text(
            f"""
        SELECT COUNT(DISTINCT si.issue_id)
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE si.sprint_id = '{sprint_id}'
          AND it.name NOT ILIKE '%sub%'
    """
        )
    ).fetchone()
    print(f"Sprint 36 issues in sprint_issues (no sub-tasks): {si_count[0]}")

    # Count with changelog
    cl_count = conn.execute(
        text(
            f"""
        SELECT COUNT(DISTINCT sic.issue_id)
        FROM clean_jira.sprint_issues_changelog sic
        JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
        JOIN clean_jira.issues i ON i.id = sic.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE sic.sprint_id = '{sprint_id}'
          AND it.name NOT ILIKE '%sub%'
    """
        )
    ).fetchone()
    print(f"Sprint 36 issues with changelog: {cl_count[0]}")

    # Issues without changelog
    no_cl = conn.execute(
        text(
            f"""
        SELECT COUNT(DISTINCT si.issue_id)
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE si.sprint_id = '{sprint_id}'
          AND it.name NOT ILIKE '%sub%'
          AND NOT EXISTS (
              SELECT 1 FROM clean_jira.sprint_issues_changelog sic
              WHERE sic.issue_id = si.issue_id AND sic.sprint_id = '{sprint_id}'
          )
    """
        )
    ).fetchone()
    print(f"Sprint 36 issues WITHOUT changelog: {no_cl[0]}")
