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
        print("--- FACT VALUES SUMMARY ---")
        total = conn.execute(text("SELECT COUNT(*) FROM metrics.fact_values")).scalar()
        sliced = conn.execute(
            text(
                "SELECT COUNT(*) FROM metrics.fact_values WHERE slice_rule_id IS NOT NULL"
            )
        ).scalar()
        print(f"Total rows: {total}")
        print(f"Sliced rows: {sliced}")

        if sliced > 0:
            print("\n--- SAMPLE SLICED DATA ---")
            res = conn.execute(
                text(
                    """
                SELECT fv.slice_value, sr.rule_name, COUNT(*)
                FROM metrics.fact_values fv
                JOIN metrics.slice_rules sr ON fv.slice_rule_id = sr.id
                GROUP BY 1, 2
                LIMIT 10
            """
                )
            ).fetchall()
            for row in res:
                print(row)
        else:
            print("\nChecking why sliced is 0...")
            # Check if velocity definitions/calculations are there
            res = conn.execute(
                text(
                    "SELECT COUNT(*) FROM metrics.calculations WHERE calc_code LIKE 'velocity%%'"
                )
            ).scalar()
            print(f"Velocity calculations count: {res}")


if __name__ == "__main__":
    main()
