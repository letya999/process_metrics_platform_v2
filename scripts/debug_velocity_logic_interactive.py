import os
import sys

import polars as pl
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Add project root to path
sys.path.append(os.getcwd())

from pipelines.calculations import velocity as velocity_logic
from pipelines.utils.polars_db import read_table

load_dotenv()

db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)


def debug_logic():
    print("Loading data for Sprint 36 (TWMOB only)...")

    # Load raw data filtered for speed/relevance
    sprints_df = read_table(
        engine, "SELECT * FROM clean_jira.sprints WHERE name = 'Sprint 36'"
    )

    # We need to find the Sprint ID for TWMOB
    # Let's get sprint issues first to identify relevant sprint ID
    sprint_issues_df = read_table(
        engine,
        """
        SELECT si.*
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON si.issue_id = i.id
        JOIN clean_jira.sprints s ON si.sprint_id = s.id
        WHERE s.name = 'Sprint 36' AND i.external_key LIKE 'TWMOB%%'
    """,
    )

    if sprint_issues_df.is_empty():
        print("No TWMOB issues found for Sprint 36")
        return

    sprint_id = sprint_issues_df["sprint_id"][0]
    print(f"Target Sprint ID: {sprint_id}")

    # Filter Sprints DF
    sprints_df = sprints_df.filter(pl.col("id") == sprint_id)

    # Get Issues
    issue_ids_list = sprint_issues_df["issue_id"].unique().to_list()
    issues_ids_str = "', '".join([str(x) for x in issue_ids_list])

    issues_df = read_table(
        engine, f"SELECT * FROM clean_jira.issues WHERE id IN ('{issues_ids_str}')"
    )

    # Get Status Changelog
    status_changelog_df = read_table(
        engine,
        f"""
        SELECT * FROM clean_jira.issue_status_changelog
        WHERE issue_id IN ('{issues_ids_str}')
    """,
    )

    # Get Issue Statuses (Categories)
    issue_statuses_df = read_table(engine, "SELECT * FROM clean_jira.issue_statuses")

    # Get Board Columns (Just in case)
    boards_df = read_table(engine, "SELECT * FROM clean_jira.boards")
    board_columns_df = read_table(
        engine, "SELECT * FROM clean_jira.board_columns"
    )  # Load all for safety

    print(f"Loaded {len(issues_df)} issues.")

    # --- STEP 1: Get Done Status IDs ---
    print("\n--- Testing get_done_status_ids ---")
    done_ids = velocity_logic.get_done_status_ids(
        boards_df, board_columns_df, issue_statuses_df
    )
    print(f"Found {len(done_ids)} Done IDs.")

    # Verify TWMOB-1906 Status ID
    target_key = "TWMOB-1906"
    target_issue = issues_df.filter(pl.col("external_key") == target_key)
    if not target_issue.is_empty():
        tid = target_issue["status_id"][0]
        print(f"TWMOB-1906 Status ID: {tid}")

        # Check if in done_ids (case insensitive)
        is_in = str(tid).lower() in [str(x).lower() for x in done_ids]
        print(f"Is TWMOB-1906 Status in Done IDs? {is_in}")

        if not is_in:
            # Find category
            stat_row = issue_statuses_df.filter(pl.col("id") == tid)
            if not stat_row.is_empty():
                print(f"Status Details: {stat_row.to_dicts()}")
            else:
                print("Status ID not found in issue_statuses table!")

    # --- STEP 2: Test identify_completed_subset ---
    print("\n--- Testing identify_completed_subset ---")

    # Prepare inputs logic expects
    # It takes sprint_issues_df (scope_df)
    # It needs status_changelog_df
    # It needs done_status_ids

    # We call the function
    # Note: calculate_velocity_facts calls identify_completed_subset internally.
    # But we can call identify_completed_subset directly if we can access it.
    # It's defined in the module.

    # But identify_completed_subset requires 'sprints_df' (for end dates) and 'scope_df'.
    # scope_df represents "Plan". But wait, logic uses 'sprint_issues_df' passed as 'scope_df' usually?
    # In calculate_velocity_facts:
    #   total_scope = identify_sprint_scope_at_close(...)
    #   completed_subset = identify_completed_subset(total_scope, sprint_changelog_df, sprints_df, ...done_ids...)

    # Wait, identify_completed_subset uses 'scope_df'.
    # If we want to check EVERYTHING associated with sprint, pass sprint_issues_df as scope.

    completed_df = velocity_logic.identify_completed_subset(
        scope_df=sprint_issues_df,
        status_changelog_df=status_changelog_df,
        sprints_df=sprints_df,
        done_status_ids=done_ids,
        issues_df=issues_df,  # Fallback
    )

    print(f"Algorithm identified {len(completed_df)} completed issues.")

    # Check TWMOB-1906
    target_id = target_issue["id"][0]
    is_completed = not completed_df.filter(pl.col("issue_id") == target_id).is_empty()
    print(f"Is TWMOB-1906 identified as Completed? {is_completed}")

    if not is_completed:
        print("DEBUGGING WHY NOT COMPLETED:")
        # Replicate logic manually
        # 1. Effective End Date
        sprint_row = sprints_df.filter(pl.col("id") == sprint_id)
        end_date = sprint_row["complete_date"][0] or sprint_row["end_date"][0]
        print(f"Sprint End Date: {end_date}")

        # 2. Changelog
        cl_rows = status_changelog_df.filter(pl.col("issue_id") == target_id).sort(
            "changed_at", descending=True
        )
        print("Changelog Rows:")
        print(cl_rows)

        # 3. Last status before end
        valid_cl = cl_rows.filter(pl.col("changed_at") <= end_date)
        if not valid_cl.is_empty():
            last_stat = valid_cl["to_status_id"][0]
            print(f"Last Status ID before end: {last_stat}")
            print(
                f"Is in Done IDs? {str(last_stat).lower() in [str(x).lower() for x in done_ids]}"
            )
        else:
            print("No changelog entries before end date!")
            # Check Fallback
            resolved_at = target_issue["jira_resolved_at"][0]
            print(f"Resolved At: {resolved_at}")
            curr_stat = target_issue["status_id"][0]
            print(f"Current Status: {curr_stat}")
            print(
                f"Is Resolved <= End? {resolved_at <= end_date if resolved_at else 'No Resolved Date'}"
            )


if __name__ == "__main__":
    debug_logic()
