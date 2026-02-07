"""Analyze commitment for Sprint 36."""

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

with engine.connect() as conn:
    # For Sprint 36
    sprint = conn.execute(
        text(
            """
        SELECT s.id, s.start_date FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
    """
        )
    ).fetchone()
    sprint_id, start_date = sprint

    print(f"Sprint 36: id={sprint_id}, start_date={start_date}")

    # Get all issues with their first 'added' timestamp
    issues = conn.execute(
        text(
            f"""
        WITH first_added AS (
            SELECT
                sic.issue_id,
                MIN(sic.changed_at) FILTER (WHERE sic.action = 'added') as first_added_at
            FROM clean_jira.sprint_issues_changelog sic
            JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
            JOIN clean_jira.issues i ON i.id = sic.issue_id
            JOIN clean_jira.issue_types it ON it.id = i.type_id
            WHERE sic.sprint_id = '{sprint_id}'
              AND it.name NOT ILIKE '%sub%'
            GROUP BY sic.issue_id
        ),
        last_action AS (
            SELECT DISTINCT ON (sic.issue_id) sic.issue_id, sic.action as last_action
            FROM clean_jira.sprint_issues_changelog sic
            WHERE sic.sprint_id = '{sprint_id}'
            ORDER BY sic.issue_id, sic.changed_at DESC
        ),
        sp AS (
            SELECT fv.issue_id, MAX(
                CASE
                    WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$'
                    THEN (fv.json_value::text)::numeric
                    ELSE 0
                END
            ) as story_points
            FROM clean_jira.field_values fv
            JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
            WHERE fk.external_key = 'customfield_10036'
            GROUP BY fv.issue_id
        )
        SELECT
            i.external_key,
            fa.first_added_at,
            la.last_action,
            COALESCE(sp.story_points, 0) as sp,
            CASE WHEN fa.first_added_at <= '{start_date}' THEN 'IN' ELSE 'AFTER' END as added_timing
        FROM first_added fa
        JOIN clean_jira.issues i ON i.id = fa.issue_id
        LEFT JOIN last_action la ON la.issue_id = fa.issue_id
        LEFT JOIN sp ON sp.issue_id = i.id
        ORDER BY fa.first_added_at
    """
        )
    ).fetchall()

    print(
        f"\n{'Issue':<15} {'First Added':<30} {'Last Action':<10} {'SP':>5} {'Timing':<8}"
    )
    print("-" * 75)

    before_start = []
    after_start = []

    for row in issues:
        key, first_added, last_action, sp, timing = row
        print(
            f"{key:<15} {str(first_added):<30} {last_action or 'N/A':<10} {sp:>5.0f} {timing:<8}"
        )
        if timing == "IN" and last_action == "added":
            before_start.append((key, sp))
        elif last_action == "added":
            after_start.append((key, sp))

    print("-" * 75)
    print(
        f"\nAdded BEFORE start (commitment): {len(before_start)} issues, {sum(sp for _, sp in before_start):.0f} SP"
    )
    print(
        f"Added AFTER start (scope creep): {len(after_start)} issues, {sum(sp for _, sp in after_start):.0f} SP"
    )
    print("\nJira reported Plan: 45 SP")
