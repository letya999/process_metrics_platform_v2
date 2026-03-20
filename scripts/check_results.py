import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def check_velocity_data():
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_host = "localhost"  # Testing from outside docker
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")
    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    engine = create_engine(DATABASE_URL)

    query = """
        SELECT
            calc_code,
            project_key,
            full_date,
            value,
            entity_id as sprint_id
        FROM metrics.v_facts
        WHERE metric_code = 'velocity'
        ORDER BY full_date DESC, sprint_id
        LIMIT 12
    """

    with engine.connect() as conn:
        result = conn.execute(text(query))
        print(
            f"{'Metric':<25} | {'Proj':<6} | {'Date':<10} | {'Value':<6} | {'Sprint ID'}"
        )
        print("-" * 100)
        for row in result:
            print(
                f"{row[0]:<25} | {row[1]:<6} | {str(row[2]):<10} | {float(row[3]):<6} | {row[4]}"
            )


if __name__ == "__main__":
    check_velocity_data()
