"""Analyze why Plan (Commitment) is less than Jira reports."""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.append(os.getcwd())
load_dotenv()

db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)

OUTPUT_FILE = "debug_plan_discrepancy.txt"


def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("PLAN (COMMITMENT) DISCREPANCY ANALYSIS\n")
        f.write("=" * 80 + "\n\n")

        with engine.connect() as conn:
            sprints = [
                ("Sprint 34", 83),
                ("Sprint 35", 80),
                ("Sprint 36", 45),
                ("Sprint 37", 92),
                ("Sprint 38", 78),
            ]

            for sprint_name, jira_plan in sprints:
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
                    continue

                sprint_id, start_date, end_date = sprint_info

                f.write(f"\n{'=' * 60}\n")
                f.write(
                    f"{sprint_name}: Start={start_date}, Jira Plan={jira_plan} SP\n"
                )
                f.write(f"{'=' * 60}\n\n")

                # Our algorithm:
                # 1. Issues added at or before start (from changelog)
                # 2. Minus issues that were later removed

                # Count issues in sprint_issues (final scope, excluding sub-tasks)
                in_sprint = conn.execute(
                    text(
                        f"""
                    SELECT COUNT(*) as cnt, COALESCE(SUM(
                        CASE
                            WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                            THEN (fv.json_value::text)::numeric
                            ELSE 0
                        END
                    ), 0) as sp
                    FROM clean_jira.sprint_issues si
                    JOIN clean_jira.issues i ON i.id = si.issue_id
                    JOIN clean_jira.issue_types it ON it.id = i.type_id
                    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
                    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                        AND fk.external_key = 'customfield_10036'
                    WHERE si.sprint_id = '{sprint_id}'
                      AND it.name NOT ILIKE '%sub%'
                """
                    )
                ).fetchone()
                f.write(
                    f"In sprint_issues (final scope): {in_sprint[0]} issues, {in_sprint[1]:.0f} SP\n"
                )

                # Issues with changelog
                with_changelog = conn.execute(
                    text(
                        f"""
                    SELECT COUNT(DISTINCT sic.issue_id) as cnt
                    FROM clean_jira.sprint_issues_changelog sic
                    JOIN clean_jira.issues i ON i.id = sic.issue_id
                    JOIN clean_jira.issue_types it ON it.id = i.type_id
                    JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
                    WHERE sic.sprint_id = '{sprint_id}'
                      AND it.name NOT ILIKE '%sub%'
                """
                    )
                ).fetchone()
                f.write(f"Issues with changelog: {with_changelog[0]}\n")

                # Issues without changelog
                without_changelog = conn.execute(
                    text(
                        f"""
                    SELECT COUNT(*) as cnt, COALESCE(SUM(
                        CASE
                            WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                            THEN (fv.json_value::text)::numeric
                            ELSE 0
                        END
                    ), 0) as sp
                    FROM clean_jira.sprint_issues si
                    JOIN clean_jira.issues i ON i.id = si.issue_id
                    JOIN clean_jira.issue_types it ON it.id = i.type_id
                    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
                    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                        AND fk.external_key = 'customfield_10036'
                    WHERE si.sprint_id = '{sprint_id}'
                      AND it.name NOT ILIKE '%sub%'
                      AND NOT EXISTS (
                          SELECT 1 FROM clean_jira.sprint_issues_changelog sic
                          WHERE sic.issue_id = si.issue_id AND sic.sprint_id = '{sprint_id}'
                      )
                """
                    )
                ).fetchone()
                f.write(
                    f"Issues WITHOUT changelog (assumed in scope): {without_changelog[0]} issues, {without_changelog[1]:.0f} SP\n"
                )

                # Issues added at or before start (still in sprint)
                commitment = conn.execute(
                    text(
                        f"""
                    WITH added_before_start AS (
                        SELECT DISTINCT sic.issue_id
                        FROM clean_jira.sprint_issues_changelog sic
                        JOIN clean_jira.issues i ON i.id = sic.issue_id
                        JOIN clean_jira.issue_types it ON it.id = i.type_id
                        JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
                        WHERE sic.sprint_id = '{sprint_id}'
                          AND it.name NOT ILIKE '%sub%'
                          AND sic.action = 'added'
                          AND sic.changed_at <= '{start_date}'
                    ),
                    last_action AS (
                        SELECT DISTINCT ON (sic.issue_id) sic.issue_id, sic.action
                        FROM clean_jira.sprint_issues_changelog sic
                        JOIN clean_jira.issues i ON i.id = sic.issue_id
                        JOIN clean_jira.issue_types it ON it.id = i.type_id
                        JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
                        WHERE sic.sprint_id = '{sprint_id}'
                          AND it.name NOT ILIKE '%sub%'
                        ORDER BY sic.issue_id, sic.changed_at DESC
                    )
                    SELECT COUNT(DISTINCT abs.issue_id) as cnt, COALESCE(SUM(
                        CASE
                            WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                            THEN (fv.json_value::text)::numeric
                            ELSE 0
                        END
                    ), 0) as sp
                    FROM added_before_start abs
                    JOIN last_action la ON la.issue_id = abs.issue_id
                    JOIN clean_jira.issues i ON i.id = abs.issue_id
                    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
                    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                        AND fk.external_key = 'customfield_10036'
                    WHERE la.action = 'added'
                """
                    )
                ).fetchone()
                f.write(
                    f"\nOur Commitment (added before start, not removed): {commitment[0]} issues, {commitment[1]:.0f} SP\n"
                )
                f.write(f"Gap from Jira Plan: {jira_plan - commitment[1]:.0f} SP\n")

                # Where is the gap coming from?
                # Check issues added AFTER start but in final scope (scope creep)
                scope_creep = conn.execute(
                    text(
                        f"""
                    WITH first_add AS (
                        SELECT DISTINCT ON (sic.issue_id) sic.issue_id, sic.changed_at as first_added
                        FROM clean_jira.sprint_issues_changelog sic
                        JOIN clean_jira.issues i ON i.id = sic.issue_id
                        JOIN clean_jira.issue_types it ON it.id = i.type_id
                        JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
                        WHERE sic.sprint_id = '{sprint_id}'
                          AND it.name NOT ILIKE '%sub%'
                          AND sic.action = 'added'
                        ORDER BY sic.issue_id, sic.changed_at
                    ),
                    last_action AS (
                        SELECT DISTINCT ON (sic.issue_id) sic.issue_id, sic.action
                        FROM clean_jira.sprint_issues_changelog sic
                        JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
                        WHERE sic.sprint_id = '{sprint_id}'
                        ORDER BY sic.issue_id, sic.changed_at DESC
                    )
                    SELECT COUNT(*) as cnt, COALESCE(SUM(
                        CASE
                            WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                            THEN (fv.json_value::text)::numeric
                            ELSE 0
                        END
                    ), 0) as sp
                    FROM first_add fa
                    JOIN last_action la ON la.issue_id = fa.issue_id
                    JOIN clean_jira.issues i ON i.id = fa.issue_id
                    LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
                    LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                        AND fk.external_key = 'customfield_10036'
                    WHERE fa.first_added > '{start_date}'
                      AND la.action = 'added'
                """
                    )
                ).fetchone()
                f.write(
                    f"Scope Creep (added after start): {scope_creep[0]} issues, {scope_creep[1]:.0f} SP\n"
                )

                # Adding it up
                total_scope = commitment[1] + scope_creep[1] + without_changelog[1]
                f.write(
                    "\nTotal Final Scope = Commitment + Scope Creep + No Changelog\n"
                )
                f.write(
                    f"                  = {commitment[1]:.0f} + {scope_creep[1]:.0f} + {without_changelog[1]:.0f} = {total_scope:.0f} SP\n"
                )

    print(f"Analysis written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
