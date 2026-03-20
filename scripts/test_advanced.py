import os

from dotenv import load_dotenv

load_dotenv()
os.environ["POSTGRES_HOST"] = "localhost"

from dagster import build_asset_context

from pipelines.assets.metrics.advanced import calculate_advanced_metrics
from pipelines.resources.database import DatabaseResource


class LocalDatabaseResource(DatabaseResource):
    def get_engine(self):
        from sqlalchemy import create_engine

        db_user = os.getenv("POSTGRES_USER", "postgres")
        db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
        db_host = os.getenv("POSTGRES_HOST", "localhost")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")
        DATABASE_URL = (
            f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        )
        return create_engine(DATABASE_URL)


if __name__ == "__main__":
    context = build_asset_context()
    database = LocalDatabaseResource()
    result = calculate_advanced_metrics(context, database)
    print("Result:", result)
