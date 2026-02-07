"""
Deep analysis of TWMOB velocity discrepancies - Fixed version.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)


def get_story_points_safe():
    """Get story points extraction SQL that handles various JSON formats."""
    return """
        CASE
            WHEN fv.json_value IS NULL THEN 0
            WHEN fv.json_value::text = '{}' THEN 0
            WHEN fv.json_value::text = 'null' THEN 0
            WHEN fv.json_value::text ~ '^[0-9.]+$' THEN (fv.json_value::text)::numeric
            ELSE 0
        END
    """


def analyze_sprint36_detail():
    """Detailed analysis of Sprint 36."""
    print("=" * 80)
    print("SPRINT 36 DETAILED ANALYSIS")
    print("Jira: Commitment=45, Completed=75")
    print("Our:  Plan=38, Fact=24")
    print("=" * 80)

    sp_sql = get_story_points_safe()

    with engine.connect() as conn:
        # Get sprint info
        sprint_info = conn.execute(
            text(
                """
            SELECT s.id, s.name, s.start_date, s.end_date, s.complete_date
            FROM clean_jira.sprints s
            JOIN clean_jira.projects p ON p.id = s.project_id
            WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
        """
            )
        ).fetchone()

        if not sprint_info:
            print("Sprint 36 not found!")
            return

        sprint_id = sprint_info[0]
        start_date = sprint_info[2]
        end_date = sprint_info[4] or sprint_info[3]

        print(f"\nSprint ID: {sprint_id}")
        print(f"Start: {start_date}")
        print(f"End: {end_date}")

        # 1. All issues currently in sprint
        print("\n" + "-" * 60)
        print("1. ALL ISSUES CURRENTLY IN SPRINT (sprint_issues table):")
        result = conn.execute(
            text(
                f"""
            SELECT
                i.external_key,
                ist.name as status,
                ist.category,
                {sp_sql} as sp,
                i.jira_resolved_at
            FROM clean_jira.sprint_issues si
            JOIN clean_jira.issues i ON i.id = si.issue_id
            LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
            LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
            LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
            WHERE si.sprint_id = '{sprint_id}'
            ORDER BY i.external_key
        """
            )
        )

        total_sp = 0
        done_sp = 0
        issues = []
        for row in result:
            total_sp += float(row[3] or 0)
            if row[2] == "done":
                done_sp += float(row[3] or 0)
            issues.append(row)

        print(f"Total issues: {len(issues)}")
        print(f"Total SP: {total_sp}")
        print(f"Done SP (current status): {done_sp}")
        print("\nIssue List:")
        for row in issues:
            print(f"  {row[0]}: {row[1]} ({row[2]}) - {row[3]} SP")

        # 2. Check issue_sprint_changelog
        print("\n" + "-" * 60)
        print("2. ISSUE SPRINT CHANGELOG (add/remove history):")
        result = conn.execute(
            text(
                f"""
            SELECT
                i.external_key,
                isc.action,
                isc.changed_at,
                {sp_sql} as sp
            FROM clean_jira.issue_sprint_changelog isc
            JOIN clean_jira.issues i ON i.id = isc.issue_id
            LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
            LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
            WHERE isc.sprint_id = '{sprint_id}'
            ORDER BY isc.changed_at
        """
            )
        )

        changelog = list(result)
        added_events = [r for r in changelog if r[1] == "added"]
        removed_events = [r for r in changelog if r[1] == "removed"]
        print(f"Total changelog entries: {len(changelog)}")
        print(f"Added events: {len(added_events)}")
        print(f"Removed events: {len(removed_events)}")

        # Show changelog
        print("\nChangelog entries:")
        for row in changelog[:20]:  # First 20
            print(f"  {row[2]}: {row[0]} - {row[1]} ({row[3]} SP)")
        if len(changelog) > 20:
            print(f"  ... and {len(changelog) - 20} more")

        # 3. Issues added BEFORE/AT start (commitment)
        print("\n" + "-" * 60)
        print(f"3. COMMITMENT: Issues added at/before start ({start_date}):")
        result = conn.execute(
            text(
                f"""
            WITH first_add AS (
                SELECT DISTINCT ON (issue_id)
                    issue_id,
                    changed_at as first_added
                FROM clean_jira.issue_sprint_changelog
                WHERE sprint_id = '{sprint_id}' AND action = 'added'
                ORDER BY issue_id, changed_at
            ),
            last_action AS (
                SELECT DISTINCT ON (issue_id)
                    issue_id,
                    action as final_action
                FROM clean_jira.issue_sprint_changelog
                WHERE sprint_id = '{sprint_id}'
                ORDER BY issue_id, changed_at DESC
            )
            SELECT
                i.external_key,
                fa.first_added,
                la.final_action,
                ist.name as status,
                ist.category,
                {sp_sql} as sp
            FROM first_add fa
            JOIN last_action la ON la.issue_id = fa.issue_id
            JOIN clean_jira.issues i ON i.id = fa.issue_id
            LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
            LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
            LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
            WHERE fa.first_added <= '{start_date}'
            ORDER BY i.external_key
        """
            )
        )

        commitment_issues = list(result)
        commitment_sp = sum(float(r[5] or 0) for r in commitment_issues)
        still_in = [r for r in commitment_issues if r[2] == "added"]
        removed = [r for r in commitment_issues if r[2] == "removed"]

        print(f"Issues with add event at/before start: {len(commitment_issues)}")
        print(f"  Still in sprint: {len(still_in)}")
        print(f"  Later removed: {len(removed)}")
        print(f"Total SP: {commitment_sp}")

        still_in_sp = sum(float(r[5] or 0) for r in still_in)
        print(f"SP (still in sprint): {still_in_sp}")

        # 4. Scope creep
        print("\n" + "-" * 60)
        print(f"4. SCOPE CREEP: Issues added after start ({start_date}):")
        result = conn.execute(
            text(
                f"""
            WITH first_add AS (
                SELECT DISTINCT ON (issue_id)
                    issue_id,
                    changed_at as first_added
                FROM clean_jira.issue_sprint_changelog
                WHERE sprint_id = '{sprint_id}' AND action = 'added'
                ORDER BY issue_id, changed_at
            ),
            last_action AS (
                SELECT DISTINCT ON (issue_id)
                    issue_id,
                    action as final_action
                FROM clean_jira.issue_sprint_changelog
                WHERE sprint_id = '{sprint_id}'
                ORDER BY issue_id, changed_at DESC
            )
            SELECT
                i.external_key,
                fa.first_added,
                la.final_action,
                ist.name as status,
                ist.category,
                {sp_sql} as sp
            FROM first_add fa
            JOIN last_action la ON la.issue_id = fa.issue_id
            JOIN clean_jira.issues i ON i.id = fa.issue_id
            LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
            LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
            LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
            WHERE fa.first_added > '{start_date}'
              AND la.final_action = 'added'
            ORDER BY i.external_key
        """
            )
        )

        scope_creep = list(result)
        scope_creep_sp = sum(float(r[5] or 0) for r in scope_creep)
        done_creep = [r for r in scope_creep if r[4] == "done"]
        done_creep_sp = sum(float(r[5] or 0) for r in done_creep)

        print(f"Scope creep issues: {len(scope_creep)}")
        print(f"Scope creep SP: {scope_creep_sp}")
        print(f"Done scope creep: {len(done_creep)} issues, {done_creep_sp} SP")

        print("\nScope creep issues:")
        for row in scope_creep:
            status = "DONE" if row[4] == "done" else row[3]
            print(f"  {row[0]}: {status} ({row[5]} SP) - added {row[1]}")

        # 5. Check completed status
        print("\n" + "-" * 60)
        print("5. COMPLETED: Issues with Done status at end:")

        # First get all unique issue IDs in sprint at close
        result = conn.execute(
            text(
                f"""
            WITH final_scope AS (
                SELECT DISTINCT ON (issue_id) issue_id
                FROM clean_jira.issue_sprint_changelog
                WHERE sprint_id = '{sprint_id}'
                ORDER BY issue_id, changed_at DESC
            )
            SELECT
                i.external_key,
                ist.name as status,
                ist.category,
                {sp_sql} as sp,
                i.jira_resolved_at
            FROM final_scope fs
            JOIN clean_jira.issue_sprint_changelog isc ON isc.issue_id = fs.issue_id
                AND isc.sprint_id = '{sprint_id}'
            JOIN clean_jira.issues i ON i.id = fs.issue_id
            LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
            LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
            LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
            WHERE isc.action = 'added'
              AND isc.changed_at = (
                  SELECT MAX(changed_at) FROM clean_jira.issue_sprint_changelog
                  WHERE issue_id = fs.issue_id AND sprint_id = '{sprint_id}'
              )
              AND ist.category = 'done'
            ORDER BY i.external_key
        """
            )
        )

        completed = list(result)
        completed_sp = sum(float(r[3] or 0) for r in completed)
        print(f"Completed issues (current status = done): {len(completed)}")
        print(f"Completed SP: {completed_sp}")

        print("\nCompleted issues:")
        for row in completed:
            print(f"  {row[0]}: {row[1]} ({row[3]} SP)")

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY FOR SPRINT 36:")
        print("=" * 80)
        print("Jira Commitment: 45 SP")
        print(f"Our Commitment (still in sprint from start): {still_in_sp} SP")
        print(f"Gap: {45 - still_in_sp} SP")
        print()
        print("Jira Completed: 75 SP")
        print(f"Our Completed (done status): {completed_sp} SP")
        print(f"Gap: {75 - completed_sp} SP")
        print()
        print("ANALYSIS:")
        print(f"Total in sprint_issues: {len(issues)} issues, {total_sp} SP")
        print(
            f"From changelog - commitment at start: {len(still_in)} issues, {still_in_sp} SP"
        )
        print(
            f"From changelog - scope creep: {len(scope_creep)} issues, {scope_creep_sp} SP"
        )
        print(f"Done scope creep: {len(done_creep)} issues, {done_creep_sp} SP")


def check_changelog_completeness():
    """Check if all sprint_issues have changelog entries."""
    print("\n" + "=" * 80)
    print("CHECKING CHANGELOG COMPLETENESS FOR SPRINT 36")
    print("=" * 80)

    sp_sql = get_story_points_safe()

    with engine.connect() as conn:
        sprint_info = conn.execute(
            text(
                """
            SELECT s.id
            FROM clean_jira.sprints s
            JOIN clean_jira.projects p ON p.id = s.project_id
            WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
        """
            )
        ).fetchone()

        sprint_id = sprint_info[0]

        # Find issues in sprint_issues but NOT in changelog
        result = conn.execute(
            text(
                f"""
            SELECT
                i.external_key,
                ist.name as status,
                ist.category,
                {sp_sql} as sp
            FROM clean_jira.sprint_issues si
            JOIN clean_jira.issues i ON i.id = si.issue_id
            LEFT JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
            LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
            LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                AND (fk.external_key = 'customfield_10036' OR fk.name ILIKE '%story point%')
            WHERE si.sprint_id = '{sprint_id}'
              AND NOT EXISTS (
                  SELECT 1 FROM clean_jira.issue_sprint_changelog isc
                  WHERE isc.issue_id = si.issue_id AND isc.sprint_id = '{sprint_id}'
              )
            ORDER BY i.external_key
        """
            )
        )

        missing = list(result)
        missing_sp = sum(float(r[3] or 0) for r in missing)

        print(f"Issues in sprint_issues but NOT in changelog: {len(missing)}")
        print(f"Missing SP: {missing_sp}")

        if missing:
            print("\nMissing issues:")
            for row in missing:
                print(f"  {row[0]}: {row[1]} ({row[3]} SP)")


def compare_all_sprints():
    """Compare our velocity with Jira for multiple sprints."""
    print("\n" + "=" * 80)
    print("COMPARISON: JIRA vs OUR VELOCITY")
    print("=" * 80)

    jira_data = {
        "Sprint 27": {"commitment": 94, "completed": 49},
        "Sprint 28": {"commitment": 94, "completed": 70},
        "Sprint 29": {"commitment": 88, "completed": 44},
        "Sprint 30": {"commitment": 93, "completed": 75},
        "Sprint 31": {"commitment": 85, "completed": 45},
        "Sprint 32": {"commitment": 104, "completed": 51},
        "Sprint 33": {"commitment": 81, "completed": 40},
        "Sprint 34": {"commitment": 83, "completed": 46},
        "Sprint 35": {"commitment": 80, "completed": 46},
        "Sprint 36": {"commitment": 45, "completed": 75},
        "Sprint 37": {"commitment": 92, "completed": 49},
        "Sprint 38": {"commitment": 78, "completed": 79},
    }

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT
                v.iteration_name,
                v.planned_story_points as our_plan,
                v.completed_story_points as our_fact
            FROM metrics.fact_velocity v
            JOIN clean_jira.projects p ON p.id = v.project_id
            WHERE p.external_key = 'TWMOB'
            ORDER BY v.start_date
        """
            )
        )

        our_data = {
            row[0]: {"plan": float(row[1]), "fact": float(row[2])} for row in result
        }

    print(
        f"{'Sprint':<12} {'Jira Plan':>10} {'Our Plan':>10} {'Diff':>6} | {'Jira Fact':>10} {'Our Fact':>10} {'Diff':>6}"
    )
    print("-" * 70)

    for sprint_name, jira in jira_data.items():
        our = our_data.get(sprint_name, {"plan": 0, "fact": 0})
        plan_diff = jira["commitment"] - our["plan"]
        fact_diff = jira["completed"] - our["fact"]

        print(
            f"{sprint_name:<12} {jira['commitment']:>10} {our['plan']:>10.0f} {plan_diff:>+6.0f} | {jira['completed']:>10} {our['fact']:>10.0f} {fact_diff:>+6.0f}"
        )


if __name__ == "__main__":
    compare_all_sprints()
    analyze_sprint36_detail()
    check_changelog_completeness()
