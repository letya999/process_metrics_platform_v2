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
    with engine.connect() as conn:
        print("--- DEFINITIONS ---")
        res = conn.execute(
            text("SELECT id, metric_code FROM metrics.definitions")
        ).fetchall()
        for row in res:
            print(row)

        print("\n--- SLICE RULES ---")
        res = conn.execute(
            text(
                "SELECT id, rule_name, target_definition_id, group_by_source_column, enabled FROM metrics.slice_rules"
            )
        ).fetchall()
        for row in res:
            print(row)

        print("\n--- FACT VALUES (Sample) ---")
        res = conn.execute(
            text(
                "SELECT metric_id, slice_rule_id, slice_value, value FROM metrics.fact_values WHERE slice_rule_id IS NOT NULL LIMIT 5"
            )
        ).fetchall()
        if not res:
            print("No sliced facts found.")
        for row in res:
            print(row)


if __name__ == "__main__":
    main()
