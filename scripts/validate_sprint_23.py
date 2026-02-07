import os
import sys

import polars as pl
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

    # Load Tables
    sprints_df = read_table(
        engine, f"SELECT * FROM clean_jira.sprints WHERE id = '{sprint_id}'"
    )

    # Issues - Need all potentially relevant issues
    sprint_issues_df = read_table(
        engine,
        f"""
        SELECT si.issue_id, si.sprint_id
        FROM clean_jira.sprint_issues si
        WHERE si.sprint_id = '{sprint_id}'
        """,
    )
    sprint_changelog_df = read_table(
        engine,
        f"""
        SELECT issue_id, sprint_id, action, changed_at
        FROM clean_jira.sprint_issues_changelog
        WHERE sprint_id = '{sprint_id}'
        """,
    )

    ids_set = set()
    if not sprint_issues_df.is_empty():
        ids_set.update(sprint_issues_df["issue_id"].to_list())
    if not sprint_changelog_df.is_empty():
        ids_set.update(sprint_changelog_df["issue_id"].to_list())

    ids_tuple = "', '".join([str(i) for i in ids_set])

    issues_df = read_table(
        engine,
        f"SELECT id, project_id, external_key as key, type_id, jira_created_at FROM clean_jira.issues WHERE id IN ('{ids_tuple}')",
    )

    # Mock types (all non-sub)
    issue_types_df = read_table(
        engine, "SELECT id, name as type_name FROM clean_jira.issue_types"
    )
    issues_df = issues_df.join(
        issue_types_df, left_on="type_id", right_on="id", how="left"
    )

    # SP
    read_table(
        engine,
        f"SELECT issue_id, 1.0 as story_points FROM clean_jira.issues WHERE id IN ('{ids_tuple}')",
    ).select(
        ["issue_id", "story_points"]
    )  # Dummy SP

    # Plan
    print("--- PLAN ---")
    commitment_df = velocity_logic.identify_sprint_commitment(
        sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
    )

    plan_issues = (
        commitment_df.join(issues_df, left_on="issue_id", right_on="id")
        .select("key")
        .sort("key")
    )
    print(plan_issues)

    # Check if TWAD-411 is in plan
    is_411 = not plan_issues.filter(pl.col("key") == "TWAD-411").is_empty()
    print(f"TWAD-411 In Plan: {is_411}")

    # Fact
    print("\n--- FACT ---")
    status_changelog_df = read_table(
        engine,
        f"""
        SELECT issue_id, to_status_id, from_status_id, changed_at
        FROM clean_jira.issue_status_changelog
        WHERE issue_id IN ('{ids_tuple}')
        """,
    )
    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")
    board_columns_df = read_table(
        engine, "SELECT id, board_id, name FROM clean_jira.board_columns"
    )  # Dummy
    read_table(engine, "SELECT * FROM clean_jira.board_column_statuses")  # Dummy
    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )

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
        completed_df.join(issues_df, left_on="issue_id", right_on="id")
        .select("key")
        .sort("key")
    )
    print(fact_issues)

    # Check if TWAD-416 is in fact
    is_416 = not fact_issues.filter(pl.col("key") == "TWAD-416").is_empty()
    print(f"TWAD-416 In Fact: {is_416}")


if __name__ == "__main__":
    main()
