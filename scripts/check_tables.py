"""Check sprint_issues_changelog structure and content."""

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
    # Check sprint_issues_changelog columns
    result = conn.execute(
        text(
            """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'clean_jira' AND table_name = 'sprint_issues_changelog'
        ORDER BY ordinal_position
    """
        )
    )
    print("sprint_issues_changelog columns:")
    for row in result:
        print(f"  {row[0]}: {row[1]}")

    # Check issue_status_changelog columns
    result = conn.execute(
        text(
            """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'clean_jira' AND table_name = 'issue_status_changelog'
        ORDER BY ordinal_position
    """
        )
    )
    print("\nissue_status_changelog columns:")
    for row in result:
        print(f"  {row[0]}: {row[1]}")

    # Sample sprint_issues_changelog data
    result = conn.execute(
        text(
            """
        SELECT sic.*, i.external_key
        FROM clean_jira.sprint_issues_changelog sic
        JOIN clean_jira.issues i ON i.id = sic.issue_id
        LIMIT 5
    """
        )
    )
    print("\nSample sprint_issues_changelog:")
    for row in result:
        print(f"  {row}")

    # Count entries per sprint for TWMOB
    result = conn.execute(
        text(
            """
        SELECT s.name, COUNT(*) as entries
        FROM clean_jira.sprint_issues_changelog sic
        JOIN clean_jira.sprints s ON s.id = sic.sprint_id
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB'
        GROUP BY s.name
        ORDER BY s.name
    """
        )
    )
    print("\nChangelog entries per TWMOB sprint:")
    for row in result:
        print(f"  {row[0]}: {row[1]}")
