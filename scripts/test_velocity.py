"""
Test the new velocity.py logic against TWMOB Jira data.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine

sys.path.append(os.getcwd())

load_dotenv()

db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)

from pipelines.calculations import velocity as velocity_logic
from pipelines.utils.polars_db import read_table


def test_twmob_velocity():
    """Test velocity calculation for TWMOB project."""

    print("Loading data from database...")

    # Load data (same as in the Dagster asset)
    sprints_df = read_table(
        engine,
        """
        SELECT DISTINCT s.id, s.project_id, s.name, s.start_date, s.end_date, s.complete_date
        FROM clean_jira.sprints s
        INNER JOIN clean_jira.sprint_issues si ON si.sprint_id = s.id
        INNER JOIN clean_jira.issues i ON i.id = si.issue_id
        INNER JOIN clean_jira.issue_types it ON it.id = i.type_id
        INNER JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE s.start_date IS NOT NULL
          AND it.name NOT ILIKE '%%sub%%'
          AND p.external_key = 'TWMOB'
        """,
    )

    sprint_issues_df = read_table(
        engine,
        """
        SELECT DISTINCT si.issue_id, si.sprint_id
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        JOIN clean_jira.sprints s ON s.id = si.sprint_id
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE it.name NOT ILIKE '%%sub%%'
          AND p.external_key = 'TWMOB'
        """,
    )

    sprint_changelog_df = read_table(
        engine,
        """
        SELECT sic.issue_id, sic.sprint_id, sic.action, sic.changed_at
        FROM clean_jira.sprint_issues_changelog sic
        JOIN clean_jira.sprints s ON s.id = sic.sprint_id
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB'
        """,
    )

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name, i.status_id,
               i.jira_created_at, i.jira_resolved_at
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        JOIN clean_jira.projects p ON p.id = i.project_id
        WHERE p.external_key = 'TWMOB'
        """,
    )

    field_values_df = read_table(
        engine,
        """
        SELECT fv.issue_id, fv.field_key_id, fv.json_value::text AS json_value
        FROM clean_jira.field_values fv
        JOIN clean_jira.issues i ON i.id = fv.issue_id
        JOIN clean_jira.projects p ON p.id = i.project_id
        WHERE p.external_key = 'TWMOB'
        """,
    )

    field_keys_df = read_table(
        engine,
        "SELECT id, external_key, name FROM clean_jira.field_keys",
    )

    status_changelog_df = read_table(
        engine,
        """
        SELECT isc.issue_id, isc.to_status_id, isc.changed_at
        FROM clean_jira.issue_status_changelog isc
        JOIN clean_jira.issues i ON i.id = isc.issue_id
        JOIN clean_jira.projects p ON p.id = i.project_id
        WHERE p.external_key = 'TWMOB'
        """,
    )

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id,
               old_value::text as old_value,
               new_value::text as new_value,
               changed_at
        FROM clean_jira.field_value_changelog
        """,
    )

    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )

    print(f"Loaded: {len(sprints_df)} sprints, {len(issues_df)} issues")
    print(f"Sprint changelog: {len(sprint_changelog_df)} entries")
    print(f"Status changelog: {len(status_changelog_df)} entries")

    # Calculate velocity
    print("\nCalculating velocity...")
    velocity_df = velocity_logic.calculate_velocity_facts(
        sprints_df=sprints_df,
        sprint_issues_df=sprint_issues_df,
        sprint_changelog_df=sprint_changelog_df,
        issues_df=issues_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        field_value_changelog_df=field_value_changelog_df,
        issue_statuses_df=issue_statuses_df,
    )

    print(f"\nCalculated velocity for {len(velocity_df)} sprints")

    # Compare with Jira data
    jira_data = {
        "Sprint 34": (83, 46),
        "Sprint 35": (80, 46),
        "Sprint 36": (45, 75),
        "Sprint 37": (92, 49),
        "Sprint 38": (78, 79),
    }

    # Write to file
    with open("velocity_test_results.txt", "w") as f:
        f.write("=" * 80 + "\n")
        f.write("COMPARISON: Jira vs New Algorithm\n")
        f.write("=" * 80 + "\n")
        f.write(
            f"{'Sprint':<12} {'Jira Plan':>10} {'Our Plan':>10} {'Gap':>8} | {'Jira Fact':>10} {'Our Fact':>10} {'Gap':>8}\n"
        )
        f.write("-" * 80 + "\n")

        for sprint_name, (jira_plan, jira_fact) in jira_data.items():
            our_row = velocity_df.filter(velocity_df["iteration_name"] == sprint_name)
            if our_row.is_empty():
                f.write(f"{sprint_name:<12} NOT FOUND\n")
                continue

            our_plan = float(our_row["planned_story_points"][0])
            our_fact = float(our_row["completed_story_points"][0])
            plan_gap = jira_plan - our_plan
            fact_gap = jira_fact - our_fact

            f.write(
                f"{sprint_name:<12} {jira_plan:>10} {our_plan:>10.0f} {plan_gap:>+8.0f} | {jira_fact:>10} {our_fact:>10.0f} {fact_gap:>+8.0f}\n"
            )

        f.write("-" * 80 + "\n")
        f.write("\nSUCCESS: If gaps are small, the algorithm is working correctly!\n")
        f.write("Small gaps can be due to:\n")
        f.write("- Timing differences in changelog capture\n")
        f.write("- Sub-task handling differences\n")
        f.write("- Story Point history not tracked (we use current values)\n")

    print("Results written to velocity_test_results.txt")


if __name__ == "__main__":
    test_twmob_velocity()
