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

    print(f"=== Testing Sprint: {sprint_name} ===\n")

    # Load all necessary tables
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
        SELECT i.id, i.project_id, i.external_key, i.jira_created_at, i.status_id, it.name as type_name
        FROM clean_jira.issues i
        JOIN clean_jira.issue_types it ON i.type_id = it.id
        WHERE i.id IN ('{ids_tuple}')
        """,
    )

    field_values_df = read_table(
        engine,
        f"SELECT issue_id, field_key_id, json_value FROM clean_jira.field_values WHERE issue_id IN ('{ids_tuple}')",
    )
    field_keys_df = read_table(
        engine, "SELECT id, external_key, name FROM clean_jira.field_keys"
    )
    field_value_changelog_df = read_table(
        engine,
        f"SELECT issue_id, field_key_id, old_value, new_value, changed_at FROM clean_jira.field_value_changelog WHERE issue_id IN ('{ids_tuple}')",
    )
    status_changelog_df = read_table(
        engine,
        f"SELECT issue_id, to_status_id, from_status_id, changed_at FROM clean_jira.issue_status_changelog WHERE issue_id IN ('{ids_tuple}')",
    )

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")
    board_columns_df = read_table(
        engine,
        "SELECT bc.id, bc.board_id, bc.name, bcs.status_id FROM clean_jira.board_columns bc LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id",
    )
    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )

    # Calculate velocity
    try:
        velocity_df = velocity_logic.calculate_velocity_facts(
            sprints_df,
            sprint_issues_df,
            sprint_changelog_df,
            issues_df,
            field_values_df,
            field_keys_df,
            status_changelog_df,
            boards_df,
            board_columns_df,
            field_value_changelog_df,
            issue_statuses_df,
        )

        print("✓ Velocity calculation succeeded!\n")
        print("Results:")
        print(f"  Planned Issues: {velocity_df['planned_issues'][0]}")
        print(f"  Planned Story Points: {velocity_df['planned_story_points'][0]}")
        print(f"  Completed Issues: {velocity_df['completed_issues'][0]}")
        print(f"  Completed Story Points: {velocity_df['completed_story_points'][0]}")

        print("\n--- Expected (from Jira) ---")
        print("  Planned Story Points: 11")
        print("  Completed Story Points: 4")

        plan_match = abs(velocity_df["planned_story_points"][0] - 11) < 0.1
        fact_match = abs(velocity_df["completed_story_points"][0] - 4) < 0.1

        print("\n--- Validation ---")
        print(f"  Plan matches Jira: {'✓ YES' if plan_match else '✗ NO'}")
        print(f"  Fact matches Jira: {'✓ YES' if fact_match else '✗ NO'}")

    except Exception as e:
        print(f"✗ Velocity calculation failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
