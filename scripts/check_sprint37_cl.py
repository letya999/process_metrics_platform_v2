"""Check all issues in Sprint 37 changelog."""

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
    sprint_id = conn.execute(
        text("SELECT id FROM clean_jira.sprints WHERE name = 'Sprint 37'")
    ).scalar()

    res = conn.execute(
        text(
            f"""
        SELECT COUNT(DISTINCT issue_id) FROM clean_jira.sprint_issues_changelog
        WHERE sprint_id = '{sprint_id}'
    """
        )
    ).scalar()
    print(f"Total distinct issues in changelog for Sprint 37: {res}")

    res_no_sub = conn.execute(
        text(
            f"""
        SELECT COUNT(DISTINCT sic.issue_id)
        FROM clean_jira.sprint_issues_changelog sic
        JOIN clean_jira.issues i ON i.id = sic.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE sic.sprint_id = '{sprint_id}' AND it.name NOT ILIKE '%sub%'
    """
        )
    ).scalar()
    print(f"Total distinct non-sub issues in changelog: {res_no_sub}")
