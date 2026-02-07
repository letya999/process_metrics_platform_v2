"""Simple query to check DB schema."""

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
    # 1. List all tables in clean_jira
    print("=" * 60)
    print("Tables in clean_jira schema:")
    result = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'clean_jira'"
        )
    )
    for row in result:
        print(f"  - {row[0]}")

    # 2. Check issue_sprint_changelog columns
    print("\n" + "=" * 60)
    print("Columns in clean_jira.issue_sprint_changelog:")
    result = conn.execute(
        text(
            """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'clean_jira' AND table_name = 'issue_sprint_changelog'
    """
        )
    )
    for row in result:
        print(f"  - {row[0]}: {row[1]}")

    # 3. Check sprint_issues columns
    print("\n" + "=" * 60)
    print("Columns in clean_jira.sprint_issues:")
    result = conn.execute(
        text(
            """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'clean_jira' AND table_name = 'sprint_issues'
    """
        )
    )
    for row in result:
        print(f"  - {row[0]}: {row[1]}")

    # 4. Sample data from TWMOB sprints
    print("\n" + "=" * 60)
    print("TWMOB Sprints:")
    result = conn.execute(
        text(
            """
        SELECT s.name, s.id, s.start_date, s.end_date, s.complete_date
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB'
        ORDER BY s.start_date DESC
        LIMIT 10
    """
        )
    )
    for row in result:
        print(f"  {row[0]}: {row[1]}, start={row[2]}, end={row[3]}, complete={row[4]}")

    # 5. Check fact_velocity for TWMOB
    print("\n" + "=" * 60)
    print("Current Velocity for TWMOB:")
    result = conn.execute(
        text(
            """
        SELECT v.iteration_name, v.planned_story_points, v.completed_story_points
        FROM metrics.fact_velocity v
        JOIN clean_jira.projects p ON p.id = v.project_id
        WHERE p.external_key = 'TWMOB'
        ORDER BY v.start_date
    """
        )
    )
    for row in result:
        print(f"  {row[0]}: Plan={row[1]}, Fact={row[2]}")
