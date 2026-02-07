"""
Debug script to analyze TWMOB velocity discrepancies between Jira and our DB.

Jira Data:
Sprint	Commitment	Completed
Sprint 34	83	46
Sprint 35	80	46
Sprint 36	45	75
Sprint 37	92	49
Sprint 38	78	79

Our DB Data:
iteration_name	Plan	Fact
Sprint 34	65	29
Sprint 35	69	32
Sprint 36	38	24
Sprint 37	83	37
Sprint 38	73	58
Sprint 39	69	14

Discrepancies to investigate:
- Sprint 34: Jira 83/46 vs Our 65/29
- Sprint 35: Jira 80/46 vs Our 69/32
- Sprint 36: Jira 45/75 vs Our 38/24 (MAJOR issue with Completed)
- Sprint 37: Jira 92/49 vs Our 83/37
- Sprint 38: Jira 78/79 vs Our 73/58
"""

import os
import sys

import polars as pl
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Add project root to path
sys.path.append(os.getcwd())

from pipelines.utils.polars_db import read_table

load_dotenv()

db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)


# Jira reference data
JIRA_DATA = {
    "Sprint 34": {"commitment": 83, "completed": 46},
    "Sprint 35": {"commitment": 80, "completed": 46},
    "Sprint 36": {"commitment": 45, "completed": 75},
    "Sprint 37": {"commitment": 92, "completed": 49},
    "Sprint 38": {"commitment": 78, "completed": 79},
}


def analyze_sprint_scope():
    """Analyze what's in sprint_issues vs sprint_changelog."""
    print("\n" + "=" * 80)
    print("ANALYZING SPRINT SCOPE FOR TWMOB")
    print("=" * 80)

    query = """
    SELECT
        s.name as sprint_name,
        s.id as sprint_id,
        s.start_date,
        s.end_date,
        s.complete_date,
        COUNT(DISTINCT si.issue_id) as issues_in_sprint_issues,
        SUM(COALESCE((fv.json_value::text)::numeric, 0)) as sp_current
    FROM clean_jira.sprints s
    JOIN clean_jira.projects p ON p.id = s.project_id
    LEFT JOIN clean_jira.sprint_issues si ON si.sprint_id = s.id
    LEFT JOIN clean_jira.issues i ON i.id = si.issue_id
    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
    WHERE p.external_key = 'TWMOB'
      AND s.name IN ('Sprint 34', 'Sprint 35', 'Sprint 36', 'Sprint 37', 'Sprint 38')
      AND (fk.external_key = 'customfield_10036' OR fk.external_key IS NULL)
    GROUP BY s.name, s.id, s.start_date, s.end_date, s.complete_date
    ORDER BY s.start_date
    """

    df = read_table(engine, query)
    print("\nSprints with Current Sprint Issues:")
    print(df)

    return df


def analyze_sprint_changelog():
    """Analyze sprint changelog to understand add/remove history."""
    print("\n" + "=" * 80)
    print("ANALYZING SPRINT CHANGELOG FOR TWMOB")
    print("=" * 80)

    query = """
    SELECT
        s.name as sprint_name,
        s.id as sprint_id,
        sc.action,
        COUNT(*) as event_count
    FROM clean_jira.sprint_changelog sc
    JOIN clean_jira.sprints s ON s.id = sc.sprint_id
    JOIN clean_jira.projects p ON p.id = s.project_id
    WHERE p.external_key = 'TWMOB'
      AND s.name IN ('Sprint 34', 'Sprint 35', 'Sprint 36', 'Sprint 37', 'Sprint 38')
    GROUP BY s.name, s.id, sc.action
    ORDER BY s.name, sc.action
    """

    df = read_table(engine, query)
    print("\nSprint Changelog Summary:")
    print(df)

    return df


def analyze_sprint_issues_detail(sprint_name: str):
    """Get detailed breakdown of a specific sprint."""
    print("\n" + "=" * 80)
    print(f"DETAILED ANALYSIS: {sprint_name}")
    print("=" * 80)

    # Get sprint info
    sprint_query = f"""
    SELECT
        s.id, s.name, s.start_date, s.end_date, s.complete_date
    FROM clean_jira.sprints s
    JOIN clean_jira.projects p ON p.id = s.project_id
    WHERE p.external_key = 'TWMOB' AND s.name = '{sprint_name}'
    """
    sprint_df = read_table(engine, sprint_query)
    print("\nSprint Info:")
    print(sprint_df)

    if sprint_df.is_empty():
        print(f"Sprint {sprint_name} not found!")
        return

    sprint_id = sprint_df["id"][0]
    start_date = sprint_df["start_date"][0]
    end_date = sprint_df["complete_date"][0] or sprint_df["end_date"][0]

    # 1. Current sprint membership
    membership_query = f"""
    SELECT
        i.external_key,
        i.summary,
        ist.name as status,
        ist.category as status_category,
        COALESCE((fv.json_value::text)::numeric, 0) as story_points,
        i.jira_resolved_at,
        CASE WHEN ist.category = 'done' THEN 'Yes' ELSE 'No' END as is_done
    FROM clean_jira.sprint_issues si
    JOIN clean_jira.issues i ON i.id = si.issue_id
    LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
        AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
    WHERE si.sprint_id = '{sprint_id}'
    ORDER BY i.external_key
    """
    members = read_table(engine, membership_query)

    print(f"\nCurrent Sprint Members: {len(members)} issues")
    total_sp = members["story_points"].sum() if not members.is_empty() else 0
    done_sp = (
        members.filter(pl.col("is_done") == "Yes")["story_points"].sum()
        if not members.is_empty()
        else 0
    )
    print(f"Total SP (current): {total_sp}")
    print(f"Done SP (current status): {done_sp}")

    # 2. Changelog history
    changelog_query = f"""
    SELECT
        i.external_key,
        sc.action,
        sc.changed_at,
        COALESCE((fv.json_value::text)::numeric, 0) as story_points
    FROM clean_jira.sprint_changelog sc
    JOIN clean_jira.issues i ON i.id = sc.issue_id
    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
        AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
    WHERE sc.sprint_id = '{sprint_id}'
    ORDER BY sc.changed_at
    """
    changelog = read_table(engine, changelog_query)

    if not changelog.is_empty():
        added = changelog.filter(pl.col("action") == "added")
        removed = changelog.filter(pl.col("action") == "removed")
        print(f"\nChangelog: {len(added)} adds, {len(removed)} removes")

        # Issues added at or before start
        added_before_start = (
            added.filter(pl.col("changed_at") <= start_date) if start_date else added
        )
        print(f"Added at/before sprint start: {len(added_before_start)}")

    # 3. Check removed issues
    removed_query = f"""
    SELECT DISTINCT
        i.external_key,
        i.summary,
        ist.name as status,
        ist.category as status_category,
        COALESCE((fv.json_value::text)::numeric, 0) as story_points,
        sc.changed_at as removed_at
    FROM clean_jira.sprint_changelog sc
    JOIN clean_jira.issues i ON i.id = sc.issue_id
    LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
        AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
    WHERE sc.sprint_id = '{sprint_id}' AND sc.action = 'removed'
    ORDER BY i.external_key
    """
    removed = read_table(engine, removed_query)
    print(f"\nIssues REMOVED from sprint: {len(removed)}")
    if not removed.is_empty():
        removed_sp = removed["story_points"].sum()
        print(f"Removed SP: {removed_sp}")
        print(removed.select(["external_key", "status", "story_points", "removed_at"]))

    # 4. Check completed status at sprint end
    status_at_end_query = f"""
    WITH last_status AS (
        SELECT DISTINCT ON (isc.issue_id)
            isc.issue_id,
            isc.to_status_id,
            isc.changed_at
        FROM clean_jira.issue_status_changelog isc
        JOIN clean_jira.sprint_issues si ON si.issue_id = isc.issue_id
        WHERE si.sprint_id = '{sprint_id}'
          AND isc.changed_at <= '{end_date}'
        ORDER BY isc.issue_id, isc.changed_at DESC
    )
    SELECT
        i.external_key,
        ist_now.name as current_status,
        ist_now.category as current_category,
        ist_end.name as status_at_end,
        ist_end.category as category_at_end,
        ls.changed_at as last_status_change,
        COALESCE((fv.json_value::text)::numeric, 0) as story_points
    FROM clean_jira.sprint_issues si
    JOIN clean_jira.issues i ON i.id = si.issue_id
    LEFT JOIN clean_jira.issue_statuses ist_now ON ist_now.id = i.status_id
    LEFT JOIN last_status ls ON ls.issue_id = i.id
    LEFT JOIN clean_jira.issue_statuses ist_end ON ist_end.id = ls.to_status_id
    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
        AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
    WHERE si.sprint_id = '{sprint_id}'
    ORDER BY i.external_key
    """
    status_at_end = read_table(engine, status_at_end_query)

    if not status_at_end.is_empty():
        done_at_end = status_at_end.filter(pl.col("category_at_end") == "done")
        done_sp_at_end = (
            done_at_end["story_points"].sum() if not done_at_end.is_empty() else 0
        )
        print(f"\nDone at sprint end: {len(done_at_end)} issues, {done_sp_at_end} SP")

    return members


def compare_with_jira():
    """Compare our velocity calculation with Jira's numbers."""
    print("\n" + "=" * 80)
    print("COMPARISON: Jira vs Our Velocity Calculation")
    print("=" * 80)

    # Get our current fact_velocity data
    query = """
    SELECT
        v.iteration_name,
        v.planned_story_points as our_plan,
        v.completed_story_points as our_fact
    FROM metrics.fact_velocity v
    JOIN clean_jira.projects p ON p.id = v.project_id
    WHERE p.external_key = 'TWMOB'
      AND v.iteration_name IN ('Sprint 34', 'Sprint 35', 'Sprint 36', 'Sprint 37', 'Sprint 38')
    ORDER BY v.iteration_name
    """

    our_df = read_table(engine, query)
    print("\nOur Velocity Data:")
    print(our_df)

    # Create comparison
    print("\nComparison:")
    print("-" * 60)
    print(
        f"{'Sprint':<12} {'Jira Plan':>10} {'Our Plan':>10} {'Diff':>6} | {'Jira Fact':>10} {'Our Fact':>10} {'Diff':>6}"
    )
    print("-" * 60)

    for sprint_name, jira in JIRA_DATA.items():
        our_row = our_df.filter(pl.col("iteration_name") == sprint_name)
        if our_row.is_empty():
            our_plan, our_fact = 0, 0
        else:
            our_plan = our_row["our_plan"][0]
            our_fact = our_row["our_fact"][0]

        plan_diff = jira["commitment"] - our_plan
        fact_diff = jira["completed"] - our_fact

        print(
            f"{sprint_name:<12} {jira['commitment']:>10} {our_plan:>10} {plan_diff:>+6} | {jira['completed']:>10} {our_fact:>10} {fact_diff:>+6}"
        )


def analyze_jira_understanding():
    """
    Analyze what Jira counts as Commitment and Completed.

    Based on Jira Sprint Reports:
    - Commitment = Story points in sprint at start + adjustments shown with *
    - Completed = Story points of issues in "Completed Issues" section

    Key insight from Jira data provided:
    - Sprint 35: Commitment 80 → "Story Points (25 → 46)" suggests started with 25 SP of completed scope
    - Sprint 36: Commitment 45 → But completed 75! (more completed than committed)

    This means:
    1. Commitment = Initial sprint scope (issues at start)
    2. Completed = ALL done issues (including scope creep, i.e., added after start)
    """
    print("\n" + "=" * 80)
    print("UNDERSTANDING JIRA'S CALCULATION LOGIC")
    print("=" * 80)

    print(
        """
    Jira Sprint Report Logic (based on provided data):

    COMMITMENT (Plan):
    - Issues added to sprint at the BEGINNING
    - NOT including issues added later (marked with * in Jira)
    - Story Points value at sprint START

    COMPLETED (Fact):
    - ALL issues that reached "Done" by sprint end
    - INCLUDING issues added after sprint start (scope creep)
    - Story Points value at sprint END

    Sprint 36 Example from Jira:
    - Commitment: 45 SP (initial scope)
    - Completed: 75 SP (includes many * items added during sprint)

    Issues marked with * in Jira = added after sprint start
    These should NOT count towards Commitment but DO count towards Completed.
    """
    )


def check_issues_added_after_start():
    """Check for issues added after sprint start (scope creep)."""
    print("\n" + "=" * 80)
    print("SCOPE CREEP ANALYSIS: Issues added after sprint start")
    print("=" * 80)

    for sprint_name in ["Sprint 35", "Sprint 36", "Sprint 37", "Sprint 38"]:
        # Get sprint dates
        sprint_query = f"""
        SELECT s.id, s.name, s.start_date, COALESCE(s.complete_date, s.end_date) as end_date
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB' AND s.name = '{sprint_name}'
        """
        sprint_df = read_table(engine, sprint_query)

        if sprint_df.is_empty():
            continue

        sprint_id = sprint_df["id"][0]
        start_date = sprint_df["start_date"][0]
        sprint_df["end_date"][0]

        # Find issues added after start
        scope_creep_query = f"""
        WITH first_add AS (
            SELECT issue_id, MIN(changed_at) as first_added
            FROM clean_jira.sprint_changelog
            WHERE sprint_id = '{sprint_id}' AND action = 'added'
            GROUP BY issue_id
        ),
        final_state AS (
            SELECT DISTINCT ON (issue_id) issue_id, action
            FROM clean_jira.sprint_changelog
            WHERE sprint_id = '{sprint_id}'
            ORDER BY issue_id, changed_at DESC
        )
        SELECT
            i.external_key,
            ist.name as status,
            ist.category,
            COALESCE((fv.json_value::text)::numeric, 0) as story_points,
            fa.first_added,
            CASE WHEN ist.category = 'done' THEN 'Yes' ELSE 'No' END as is_done
        FROM first_add fa
        JOIN final_state fs ON fs.issue_id = fa.issue_id
        JOIN clean_jira.issues i ON i.id = fa.issue_id
        LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
        LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
        LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
            AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
        WHERE fa.first_added > '{start_date}'
          AND fs.action = 'added'  -- Still in sprint (not removed later)
        ORDER BY i.external_key
        """

        scope_creep = read_table(engine, scope_creep_query)

        if scope_creep.is_empty():
            print(f"\n{sprint_name}: No scope creep detected")
        else:
            total_creep_sp = scope_creep["story_points"].sum()
            done_creep = scope_creep.filter(pl.col("is_done") == "Yes")
            done_creep_sp = (
                done_creep["story_points"].sum() if not done_creep.is_empty() else 0
            )

            print(f"\n{sprint_name}:")
            print(f"  Scope Creep: {len(scope_creep)} issues, {total_creep_sp} SP")
            print(f"  Done (scope creep): {len(done_creep)} issues, {done_creep_sp} SP")


def main():
    print("\n" + "=" * 80)
    print("TWMOB VELOCITY DISCREPANCY ANALYSIS")
    print("=" * 80)

    analyze_jira_understanding()
    compare_with_jira()
    analyze_sprint_scope()
    analyze_sprint_changelog()
    check_issues_added_after_start()

    # Detailed analysis of most problematic sprint
    analyze_sprint_issues_detail("Sprint 36")


if __name__ == "__main__":
    main()
