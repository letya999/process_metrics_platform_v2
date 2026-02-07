"""Debug velocity.py intermediate steps for Sprint 36 - simplified."""

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

import polars as pl

from pipelines.calculations import velocity as velocity_logic
from pipelines.utils.polars_db import read_table

OUTPUT_FILE = "debug_velocity_steps_output.txt"


def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # Load data for TWMOB Sprint 36
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
              AND s.name = 'Sprint 36'
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
              AND s.name = 'Sprint 36'
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
              AND s.name = 'Sprint 36'
            """,
        )

        issues_df = read_table(
            engine,
            """
            SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name, i.status_id
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
            engine, "SELECT id, external_key, name FROM clean_jira.field_keys"
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
        boards_df = read_table(
            engine, "SELECT id, project_id, name FROM clean_jira.boards"
        )
        board_columns_df = read_table(
            engine,
            "SELECT bc.id, bc.board_id, bc.name, bcs.status_id FROM clean_jira.board_columns bc LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id",
        )
        issue_statuses_df = read_table(
            engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
        )

        f.write(f"Sprints: {len(sprints_df)}\n")
        f.write(f"Sprint issues: {len(sprint_issues_df)}\n")
        f.write(f"Sprint changelog: {len(sprint_changelog_df)}\n")

        # Step 1: Done Status IDs
        done_ids = velocity_logic.get_done_status_ids(
            boards_df, board_columns_df, issue_statuses_df
        )
        f.write(f"\nDone status IDs: {len(done_ids)}\n")

        # Step 2: Story points
        sp_df = velocity_logic.extract_story_points(
            issues_df, field_values_df, field_keys_df
        )
        sp_with_values = sp_df.filter(pl.col("story_points") > 0)
        f.write(
            f"\nStory points: {len(sp_df)} issues, {len(sp_with_values)} with SP > 0\n"
        )
        f.write(f"Total SP: {sp_df['story_points'].sum()}\n")

        # Step 3: Final scope
        final_scope = velocity_logic.identify_sprint_final_scope(
            sprint_issues_df, sprint_changelog_df
        )
        f.write(f"\nFinal scope: {len(final_scope)} issues\n")

        # Step 4: Completed
        completed = velocity_logic.identify_completed_issues(
            final_scope, issues_df, status_changelog_df, done_ids, sprints_df
        )
        f.write(f"Completed: {len(completed)} issues\n")

        # Join with SP
        completed_with_sp = completed.join(
            sp_df, on="issue_id", how="left"
        ).with_columns(pl.col("story_points").fill_null(0.0))
        f.write(f"Completed SP: {completed_with_sp['story_points'].sum()}\n")

        # List completed issues
        completed_with_keys = completed_with_sp.join(
            issues_df.select(["id", "key"]).rename({"id": "issue_id"}),
            on="issue_id",
            how="left",
        )
        f.write("\nCompleted issues:\n")
        for row in completed_with_keys.iter_rows():
            issue_id, sprint_id, is_comp, sp, key = row
            f.write(f"  {key}: {sp:.0f} SP\n")

        f.write("\n" + "=" * 50 + "\n")
        f.write("Jira: 27 issues, 75 SP\n")
        f.write(
            f"Us:   {len(completed)} issues, {completed_with_sp['story_points'].sum():.0f} SP\n"
        )

    print(f"Debug output written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
