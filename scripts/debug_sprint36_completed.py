"""
Debug specific sprint to find exact discrepancy source.
"""

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


def debug_sprint36():
    """Debug Sprint 36 to understand why Completed = 75 in Jira but 85 for us."""

    with engine.connect() as conn:
        # Get sprint info
        sprint = conn.execute(
            text(
                """
            SELECT s.id, s.start_date, COALESCE(s.complete_date, s.end_date) as end_date
            FROM clean_jira.sprints s
            JOIN clean_jira.projects p ON p.id = s.project_id
            WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
        """
            )
        ).fetchone()

        sprint_id, start_date, end_date = sprint

        print(f"Sprint 36: {start_date} -> {end_date}")

        # Our completed list
        print("\n=== OUR COMPLETED ISSUES ===")
        our_completed = conn.execute(
            text(
                f"""
            WITH story_points AS (
                SELECT
                    fv.issue_id,
                    MAX(CASE
                        WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                        THEN (fv.json_value::text)::numeric
                        ELSE 0
                    END) as sp
                FROM clean_jira.field_values fv
                JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                WHERE fk.external_key = 'customfield_10036'
                GROUP BY fv.issue_id
            ),
            final_scope AS (
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
                ist.category
            FROM final_scope fs
            JOIN status_at_end sae ON sae.issue_id = fs.issue_id
            JOIN clean_jira.issue_statuses ist ON ist.id = sae.to_status_id
            JOIN clean_jira.issues i ON i.id = fs.issue_id
            JOIN clean_jira.issue_types it ON it.id = i.type_id
            LEFT JOIN story_points sp ON sp.issue_id = i.id
            WHERE fs.action = 'added'
              AND it.name NOT ILIKE '%sub%'
              AND ist.category = 'done'
            ORDER BY i.external_key
        """
            )
        ).fetchall()

        our_sp = sum(r[1] for r in our_completed)
        print(f"Our completed: {len(our_completed)} issues, {our_sp:.0f} SP")

        # Jira completed list (from the report)
        jira_completed = [
            ("TWMOB-1906", 8),
            ("TWMOB-1961", 5),
            ("TWMOB-1963", 5),
            ("TWMOB-2034", 2),
            ("TWMOB-2073", 5),
            ("TWMOB-2088", 5),
            ("TWMOB-2194", 8),
            ("TWMOB-2198", 2),
            ("TWMOB-2202", 3),
            ("TWMOB-2210", 0),
            ("TWMOB-2211", 2),
            ("TWMOB-2213", 1),
            ("TWMOB-2215", 2),
            ("TWMOB-2217", 0),
            ("TWMOB-2219", 2),
            ("TWMOB-2223", 2),
            ("TWMOB-2231", 2),
            ("TWMOB-2235", 1),
            ("TWMOB-2240", 5),
            ("TWMOB-2242", 5),
            ("TWMOB-2262", 0),
            ("TWMOB-2275", 1),
            ("TWMOB-2277", 1),
            ("TWMOB-2282", 1),
            ("TWMOB-2284", 3),
            ("TWMOB-2292", 2),
            ("TWMOB-2323", 2),
        ]
        jira_sp = sum(sp for _, sp in jira_completed)
        print(f"\nJira completed: {len(jira_completed)} issues, {jira_sp} SP")

        # Find differences
        our_keys = set(r[0] for r in our_completed)
        jira_keys = set(k for k, _ in jira_completed)

        print("\n=== DIFFERENCES ===")
        print(f"In our list but NOT in Jira: {our_keys - jira_keys}")
        print(f"In Jira but NOT in our list: {jira_keys - our_keys}")

        # Check those extra ones
        extra = our_keys - jira_keys
        if extra:
            print("\nDetails of extra issues in our list:")
            for key in extra:
                row = [r for r in our_completed if r[0] == key][0]
                print(f"  {row[0]}: {row[1]:.0f} SP, category={row[2]}")

                # Check status changelog
                history = conn.execute(
                    text(
                        f"""
                    SELECT isc.changed_at, ist.name, ist.category
                    FROM clean_jira.issue_status_changelog isc
                    JOIN clean_jira.issue_statuses ist ON ist.id = isc.to_status_id
                    JOIN clean_jira.issues i ON i.id = isc.issue_id
                    WHERE i.external_key = '{key}'
                    ORDER BY isc.changed_at DESC
                    LIMIT 5
                """
                    )
                ).fetchall()
                for h in history:
                    print(f"    {h[0]}: {h[1]} ({h[2]})")

        # Check issues missing from our list
        missing = jira_keys - our_keys
        if missing:
            print("\nDetails of issues missing from our list:")
            for key in missing:
                # Check if in final scope
                in_scope = conn.execute(
                    text(
                        f"""
                    SELECT DISTINCT ON (issue_id) action
                    FROM clean_jira.sprint_issues_changelog sic
                    JOIN clean_jira.issues i ON i.id = sic.issue_id
                    WHERE i.external_key = '{key}' AND sic.sprint_id = '{sprint_id}'
                    ORDER BY issue_id, changed_at DESC
                """
                    )
                ).fetchone()

                print(
                    f"  {key}: last_action={in_scope[0] if in_scope else 'NO CHANGELOG'}"
                )


if __name__ == "__main__":
    debug_sprint36()
