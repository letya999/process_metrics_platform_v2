import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

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
    inspector = inspect(engine)

    print("--- TABLES IN clean_jira ---")
    tables = inspector.get_table_names(schema="clean_jira")
    for table in tables:
        print(f"\nTable: {table}")
        cols = inspector.get_columns(table, schema="clean_jira")
        for col in cols:
            print(f"  - {col['name']} ({col['type']})")

        fks = inspector.get_foreign_keys(table, schema="clean_jira")
        for fk in fks:
            print(
                f"  FK: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}"
            )


if __name__ == "__main__":
    main()
