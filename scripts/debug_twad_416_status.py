import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def main():
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(DATABASE_URL)

    sprint_name = "ADS Спринт 23"

    with engine.connect() as conn:
        sprints = (
            conn.execute(
                text(
                    f"SELECT id, end_date, complete_date FROM clean_jira.sprints WHERE name = '{sprint_name}'"
                )
            )
            .mappings()
            .first()
        )

    str(sprints["id"])
    end_date = sprints["end_date"]
    complete_date = sprints["complete_date"]
    effective_end = complete_date if complete_date else end_date

    print(f"Sprint: {sprint_name}")
    print(f"End Date: {end_date}")
    print(f"Complete Date: {complete_date}")
    print(f"Effective End: {effective_end}\n")

    # Get TWAD-416 status history
    print("--- TWAD-416 Status History ---")
    with engine.connect() as conn:
        history = conn.execute(
            text(
                """
            SELECT isc.changed_at,
                   s_from.name as from_status,
                   s_to.name as to_status,
                   s_to.category as to_category
            FROM clean_jira.issue_status_changelog isc
            JOIN clean_jira.issues i ON i.id = isc.issue_id
            LEFT JOIN clean_jira.issue_statuses s_from ON s_from.id = isc.from_status_id
            LEFT JOIN clean_jira.issue_statuses s_to ON s_to.id = isc.to_status_id
            WHERE i.external_key = 'TWAD-416'
            ORDER BY isc.changed_at
        """
            )
        ).fetchall()

        for row in history:
            marker = " ← SPRINT END" if row[0] and row[0] <= effective_end else ""
            print(f"{row[0]}: {row[1]} → {row[2]} (category: {row[3]}){marker}")

    # Check current status
    print("\n--- TWAD-416 Current Status ---")
    with engine.connect() as conn:
        current = conn.execute(
            text(
                """
            SELECT s.name, s.category
            FROM clean_jira.issues i
            JOIN clean_jira.issue_statuses s ON s.id = i.status_id
            WHERE i.external_key = 'TWAD-416'
        """
            )
        ).fetchone()
        print(f"Current: {current[0]} (category: {current[1]})")


if __name__ == "__main__":
    main()
