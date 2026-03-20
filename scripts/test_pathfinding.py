import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

from pipelines.utils.smart_slicer import SmartSlicer

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
    slicer = SmartSlicer(engine)

    print("Testing path: issues -> issue_types.name")
    mapping = slicer.get_slice_mapping(
        "clean_jira.issues", "clean_jira.issue_types.name"
    )
    if mapping is not None:
        print(f"Path found! Mapping size: {len(mapping)}")
        print(mapping.head(3))
    else:
        print("Path NOT found for issue_types")

    print("\nTesting path: issues -> sprints.name")
    mapping = slicer.get_slice_mapping("clean_jira.issues", "clean_jira.sprints.name")
    if mapping is not None:
        print(f"Path found! Mapping size: {len(mapping)}")
        print(mapping.head(3))
    else:
        print("Path NOT found for sprints")


if __name__ == "__main__":
    main()
