import os
from unittest.mock import MagicMock

from dagster import build_asset_context
from dotenv import load_dotenv
from sqlalchemy import create_engine

from pipelines.assets.metrics.velocity import calculate_velocity
from pipelines.resources.database import DatabaseResource

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
    db_resource = DatabaseResource(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    # We need to mock the resource return to use our engine
    db_resource.get_engine = MagicMock(return_value=engine)

    context = build_asset_context(resources={"database": db_resource})

    print("Running calculate_velocity simulation...")
    result = calculate_velocity(context, db_resource)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
