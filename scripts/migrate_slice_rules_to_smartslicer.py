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


def migrate():
    engine = get_engine()
    print("Migrating slice rules to SmartSlicer convention...")

    with engine.begin() as conn:
        # Clear old rules
        conn.execute(
            text(
                "DELETE FROM metrics.slice_rules WHERE rule_name IN ('By Issue Type', 'By Priority', 'By Sprint')"
            )
        )

        # Insert current rules
        conn.execute(text("""
            INSERT INTO metrics.slice_rules (rule_name, source_table, group_by_source_column, enabled) VALUES
            ('By Issue Type', 'clean_jira.issue_types', 'name', true);
            """))

        # Verification
        print("\nVerifying metrics.slice_rules table state:")
        res = conn.execute(
            text(
                "SELECT rule_name, source_table, group_by_source_column, enabled FROM metrics.slice_rules"
            )
        )
        for row in res.fetchall():
            print(
                f"Rule: {row[0]} | Source: {row[1]} | Col: {row[2]} | Enabled: {row[3]}"
            )

    print("\nMigration completed.")


if __name__ == "__main__":
    migrate()
