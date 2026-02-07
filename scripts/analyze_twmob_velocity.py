"""Fixed analysis with proper aggregation to avoid duplicates."""

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

OUTPUT_FILE = "velocity_analysis_output.txt"


def main():
    """
    Fixed analysis.
    Key insight: The JOIN with field_values creates DUPLICATES because
    one issue can have multiple field_values. We need to pre-aggregate SP.
    """

    jira = {
        "Sprint 34": (83, 46),
        "Sprint 35": (80, 46),
        "Sprint 36": (45, 75),
        "Sprint 37": (92, 49),
        "Sprint 38": (78, 79),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("TWMOB VELOCITY DISCREPANCY ANALYSIS (FIXED)\n")
        f.write("=" * 80 + "\n\n")

        with engine.connect() as conn:
            # First, let's create a proper SP subquery that won't cause duplicates
            # Story Points are in field customfield_10036

            f.write("CHECKING STORY POINTS EXTRACTION:\n")
            f.write("-" * 80 + "\n")

            # Check how many SP field keys exist
            sp_keys = conn.execute(
                text(
                    """
                SELECT id, external_key, name
                FROM clean_jira.field_keys
                WHERE external_key = 'customfield_10036'
                   OR name ILIKE '%story point%'
            """
                )
            ).fetchall()
            f.write(f"Story Points field keys found: {len(sp_keys)}\n")
            for k in sp_keys:
                f.write(f"  - {k[0]}: {k[1]} ({k[2]})\n")

            # Get the primary SP field key ID
            sp_key_id = sp_keys[0][0] if sp_keys else None
            f.write(f"\nUsing field_key_id: {sp_key_id}\n\n")

            f.write("SUMMARY TABLE (with proper aggregation):\n")
            f.write("-" * 80 + "\n")
            f.write(
                f"{'Sprint':<12} {'Jira Plan':>10} {'Our Commit':>12} {'Gap':>8} | {'Jira Fact':>10} {'Our Done':>10} {'Gap':>8}\n"
            )
            f.write("-" * 80 + "\n")

            for sprint_name, (jira_plan, jira_fact) in jira.items():
                sprint_info = conn.execute(
                    text(
                        f"""
                    SELECT s.id, s.start_date, COALESCE(s.complete_date, s.end_date) as end_date
                    FROM clean_jira.sprints s
                    JOIN clean_jira.projects p ON p.id = s.project_id
                    WHERE p.external_key = 'TWMOB' AND s.name = '{sprint_name}'
                """
                    )
                ).fetchone()

                if not sprint_info:
                    f.write(f"{sprint_name:<12} NOT FOUND\n")
                    continue

                sprint_id, start_date, end_date = sprint_info

                # Commitment at start - FIXED with proper aggregation
                # Use a subquery to get SP per issue first
                commitment = conn.execute(
                    text(
                        f"""
                    WITH story_points AS (
                        SELECT
                            fv.issue_id,
                            MAX(
                                CASE
                                    WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                                    THEN (fv.json_value::text)::numeric
                                    ELSE 0
                                END
                            ) as sp
                        FROM clean_jira.field_values fv
                        JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                        WHERE fk.external_key = 'customfield_10036'
                        GROUP BY fv.issue_id
                    ),
                    at_start AS (
                        SELECT DISTINCT issue_id
                        FROM clean_jira.sprint_issues_changelog
                        WHERE sprint_id = '{sprint_id}'
                          AND action = 'added'
                          AND changed_at <= '{start_date}'
                    )
                    SELECT COUNT(DISTINCT ats.issue_id) as cnt, COALESCE(SUM(sp.sp), 0) as sp
                    FROM at_start ats
                    JOIN clean_jira.issues i ON i.id = ats.issue_id
                    JOIN clean_jira.issue_types it ON it.id = i.type_id
                    LEFT JOIN story_points sp ON sp.issue_id = ats.issue_id
                    WHERE it.name NOT ILIKE '%sub%'
                """
                    )
                ).fetchone()

                # Completed at end - FIXED with proper aggregation
                completed = conn.execute(
                    text(
                        f"""
                    WITH story_points AS (
                        SELECT
                            fv.issue_id,
                            MAX(
                                CASE
                                    WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                                    THEN (fv.json_value::text)::numeric
                                    ELSE 0
                                END
                            ) as sp
                        FROM clean_jira.field_values fv
                        JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                        WHERE fk.external_key = 'customfield_10036'
                        GROUP BY fv.issue_id
                    ),
                    last_action AS (
                        SELECT DISTINCT ON (issue_id) issue_id, action
                        FROM clean_jira.sprint_issues_changelog
                        WHERE sprint_id = '{sprint_id}'
                        ORDER BY issue_id, changed_at DESC
                    ),
                    status_at_end AS (
                        SELECT DISTINCT ON (issue_id) issue_id, to_status_id
                        FROM clean_jira.issue_status_changelog
                        WHERE changed_at <= '{end_date}'
                        ORDER BY issue_id, changed_at DESC
                    )
                    SELECT COUNT(DISTINCT la.issue_id) as cnt, COALESCE(SUM(sp.sp), 0) as sp
                    FROM last_action la
                    JOIN status_at_end sae ON sae.issue_id = la.issue_id
                    JOIN clean_jira.issue_statuses ist ON ist.id = sae.to_status_id
                    JOIN clean_jira.issues i ON i.id = la.issue_id
                    JOIN clean_jira.issue_types it ON it.id = i.type_id
                    LEFT JOIN story_points sp ON sp.issue_id = la.issue_id
                    WHERE la.action = 'added'
                      AND it.name NOT ILIKE '%sub%'
                      AND ist.category = 'done'
                """
                    )
                ).fetchone()

                commit_cnt = int(commitment[0] or 0)
                commit_sp = float(commitment[1] or 0)
                compl_cnt = int(completed[0] or 0)
                compl_sp = float(completed[1] or 0)
                plan_gap = jira_plan - commit_sp
                fact_gap = jira_fact - compl_sp

                f.write(
                    f"{sprint_name:<12} {jira_plan:>10} {commit_sp:>12.0f} {plan_gap:>+8.0f} | {jira_fact:>10} {compl_sp:>10.0f} {fact_gap:>+8.0f}\n"
                )
                f.write(
                    f"{'':>12} {'':>10} ({commit_cnt:>4} iss) {'':>8} | {'':>10} ({compl_cnt:>4} iss)\n"
                )

            f.write("-" * 80 + "\n\n")

            # Sprint 36 detail
            f.write("=" * 80 + "\n")
            f.write("SPRINT 36 ISSUES DETAIL:\n")
            f.write("=" * 80 + "\n\n")

            sprint_info = conn.execute(
                text(
                    """
                SELECT s.id, s.start_date, COALESCE(s.complete_date, s.end_date) as end_date
                FROM clean_jira.sprints s
                JOIN clean_jira.projects p ON p.id = s.project_id
                WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
            """
                )
            ).fetchone()

            sprint_id, start_date, end_date = sprint_info
            f.write(f"Period: {start_date} → {end_date}\n\n")

            # Get all issues in final scope with their SP
            f.write("Issues in final sprint scope:\n")
            issues = conn.execute(
                text(
                    f"""
                WITH story_points AS (
                    SELECT
                        fv.issue_id,
                        MAX(
                            CASE
                                WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                                THEN (fv.json_value::text)::numeric
                                ELSE 0
                            END
                        ) as sp
                    FROM clean_jira.field_values fv
                    JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                    WHERE fk.external_key = 'customfield_10036'
                    GROUP BY fv.issue_id
                ),
                first_add AS (
                    SELECT DISTINCT ON (issue_id) issue_id, changed_at as first_added
                    FROM clean_jira.sprint_issues_changelog
                    WHERE sprint_id = '{sprint_id}' AND action = 'added'
                    ORDER BY issue_id, changed_at
                ),
                last_action AS (
                    SELECT DISTINCT ON (issue_id) issue_id, action
                    FROM clean_jira.sprint_issues_changelog
                    WHERE sprint_id = '{sprint_id}'
                    ORDER BY issue_id, changed_at DESC
                ),
                status_at_end AS (
                    SELECT DISTINCT ON (issue_id) issue_id, to_status_id
                    FROM clean_jira.issue_status_changelog
                    WHERE changed_at <= '{end_date}'
                    ORDER BY issue_id, changed_at DESC
                )
                SELECT
                    i.external_key,
                    COALESCE(sp.sp, 0) as sp,
                    ist_end.category as status_at_end,
                    CASE WHEN fa.first_added <= '{start_date}' THEN 'commitment' ELSE 'scope_creep' END as type
                FROM last_action la
                JOIN clean_jira.issues i ON i.id = la.issue_id
                JOIN clean_jira.issue_types it ON it.id = i.type_id
                LEFT JOIN story_points sp ON sp.issue_id = la.issue_id
                LEFT JOIN first_add fa ON fa.issue_id = la.issue_id
                LEFT JOIN status_at_end sae ON sae.issue_id = la.issue_id
                LEFT JOIN clean_jira.issue_statuses ist_end ON ist_end.id = sae.to_status_id
                WHERE la.action = 'added'
                  AND it.name NOT ILIKE '%sub%'
                ORDER BY i.external_key
            """
                )
            ).fetchall()

            commitment_issues = [i for i in issues if i[3] == "commitment"]
            scope_creep_issues = [i for i in issues if i[3] == "scope_creep"]
            done_commitment = [i for i in commitment_issues if i[2] == "done"]
            done_scope_creep = [i for i in scope_creep_issues if i[2] == "done"]

            commitment_sp = sum(float(i[1] or 0) for i in commitment_issues)
            scope_creep_sp = sum(float(i[1] or 0) for i in scope_creep_issues)
            done_commitment_sp = sum(float(i[1] or 0) for i in done_commitment)
            done_scope_creep_sp = sum(float(i[1] or 0) for i in done_scope_creep)

            f.write(f"Total issues in scope: {len(issues)}\n")
            f.write("\nCOMMITMENT (at start):\n")
            f.write(f"  Issues: {len(commitment_issues)}, SP: {commitment_sp:.0f}\n")
            f.write(f"  Done: {len(done_commitment)}, SP: {done_commitment_sp:.0f}\n")

            f.write("\nSCOPE CREEP (added after start):\n")
            f.write(f"  Issues: {len(scope_creep_issues)}, SP: {scope_creep_sp:.0f}\n")
            f.write(f"  Done: {len(done_scope_creep)}, SP: {done_scope_creep_sp:.0f}\n")

            f.write("\nTOTAL DONE (commitment + scope creep):\n")
            f.write(
                f"  Issues: {len(done_commitment) + len(done_scope_creep)}, SP: {done_commitment_sp + done_scope_creep_sp:.0f}\n"
            )

            f.write("\nJira reports: Commitment=45, Completed=75\n")
            f.write(
                f"Our analysis: Commitment={commitment_sp:.0f}, Completed={done_commitment_sp + done_scope_creep_sp:.0f}\n"
            )

            # Check individual commitment issues
            f.write("\n\nCommitment issues detail:\n")
            for i in commitment_issues[:10]:  # First 10
                f.write(f"  {i[0]}: {i[1]:.0f} SP, status={i[2]}\n")
            if len(commitment_issues) > 10:
                f.write(f"  ... and {len(commitment_issues) - 10} more\n")

            f.write("\n\nDone scope creep issues detail:\n")
            for i in done_scope_creep:
                f.write(f"  {i[0]}: {i[1]:.0f} SP\n")

    print(f"Analysis written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
