import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
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

    # Load tables
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

    # Test Plan
    print("--- PLAN (Commitment) ---")
    commitment_df = velocity_logic.identify_sprint_commitment(
        sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
    )

    plan_issues = (
        commitment_df.join(
            issues_df.select(["id", "external_key"]), left_on="issue_id", right_on="id"
        )
        .select("external_key")
        .sort("external_key")
    )

    print(f"Count: {len(plan_issues)}")
    print("Issues:", ", ".join(plan_issues["external_key"].to_list()))

    has_411 = "TWAD-411" in plan_issues["external_key"].to_list()
    print(f"TWAD-411 included: {'✓ YES' if has_411 else '✗ NO'}")

    # Test Fact
    print("\n--- FACT (Completed) ---")
    done_ids = velocity_logic.get_done_status_ids(
        boards_df, board_columns_df, issue_statuses_df
    )
    final_scope = velocity_logic.identify_sprint_final_scope(
        sprint_issues_df, sprint_changelog_df, issues_df
    )
    completed_df = velocity_logic.identify_completed_issues(
        final_scope, issues_df, status_changelog_df, done_ids, sprints_df
    )

    fact_issues = (
        completed_df.join(
            issues_df.select(["id", "external_key"]), left_on="issue_id", right_on="id"
        )
        .select("external_key")
        .sort("external_key")
    )

    print(f"Count: {len(fact_issues)}")
    print("Issues:", ", ".join(fact_issues["external_key"].to_list()))

    has_416 = "TWAD-416" in fact_issues["external_key"].to_list()
    print(
        f"TWAD-416 included: {'✗ NO (expected)' if not has_416 else '✓ YES (unexpected)'}"
    )

    print("\n--- Summary ---")
    print(f"Plan: {len(plan_issues)} issues (expected ~10-11)")
    print(f"Fact: {len(fact_issues)} issues (expected ~3)")


if __name__ == "__main__":
    main()
