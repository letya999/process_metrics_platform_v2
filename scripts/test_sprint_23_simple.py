import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipelines.calculations import velocity as velocity_logic
from pipelines.utils.polars_db import read_table


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
                text(f"SELECT id FROM clean_jira.sprints WHERE name = '{sprint_name}'")
            )
            .mappings()
            .first()
        )
    sprint_id = str(sprints["id"])

    print(f"Testing Sprint: {sprint_name} ({sprint_id})")

    # Load Tables
    sprints_df = read_table(
        engine, f"SELECT * FROM clean_jira.sprints WHERE id = '{sprint_id}'"
    )

    sprint_issues_df = read_table(
        engine,
        f"SELECT issue_id, sprint_id FROM clean_jira.sprint_issues WHERE sprint_id = '{sprint_id}'",
    )

    sprint_changelog_df = read_table(
        engine,
        f"SELECT issue_id, sprint_id, action, changed_at FROM clean_jira.sprint_issues_changelog WHERE sprint_id = '{sprint_id}'",
    )

    ids_set = set()
    if not sprint_issues_df.is_empty():
        ids_set.update(sprint_issues_df["issue_id"].to_list())
    if not sprint_changelog_df.is_empty():
        ids_set.update(sprint_changelog_df["issue_id"].to_list())

    ids_tuple = "', '".join([str(i) for i in ids_set])

    issues_df = read_table(
        engine,
        f"""
        SELECT i.id, i.project_id, i.external_key, i.jira_created_at, it.name as type_name
        FROM clean_jira.issues i
        JOIN clean_jira.issue_types it ON i.type_id = it.id
        WHERE i.id IN ('{ids_tuple}')
        """,
    )

    print(f"\nTotal issues in scope: {len(issues_df)}")
    print(f"Issues columns: {issues_df.columns}")

    # Test commitment
    try:
        commitment_df = velocity_logic.identify_sprint_commitment(
            sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
        )

        plan_count = len(commitment_df)
        print(f"\n✓ Plan calculation succeeded: {plan_count} issues")

        # Show which issues
        plan_keys = (
            commitment_df.join(
                issues_df.select(["id", "external_key"]),
                left_on="issue_id",
                right_on="id",
            )
            .select("external_key")
            .sort("external_key")
        )

        print("Plan issues:")
        for key in plan_keys["external_key"].to_list():
            print(f"  - {key}")

    except Exception as e:
        print(f"\n✗ Plan calculation failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
