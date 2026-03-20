import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def get_engine():
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")
    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(DATABASE_URL)


def main():
    engine = get_engine()
    with engine.begin() as conn:
        print("Cleaning up old rules...")
        conn.execute(text("DELETE FROM metrics.slice_rules"))

        print("Inserting correct rules...")
        # 1. By Issue Type (Path: issues.type_id -> issue_types.id)
        # Target is clean_jira.issue_types.name
        conn.execute(
            text(
                """
            INSERT INTO metrics.slice_rules (rule_name, source_table, group_by_source_column, enabled)
            VALUES ('By Issue Type', 'clean_jira.issue_types', 'name', true)
        """
            )
        )

        # 2. By Sprint (Path: issues.id -> sprint_issues.issue_id -> sprint_issues.sprint_id -> sprints.id)
        # Target is clean_jira.sprints.name
        conn.execute(
            text(
                """
            INSERT INTO metrics.slice_rules (rule_name, source_table, group_by_source_column, enabled)
            VALUES ('By Sprint', 'clean_jira.sprints', 'name', true)
        """
            )
        )

        print("Rules updated successfully.")


if __name__ == "__main__":
    main()
