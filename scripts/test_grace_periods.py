"""Test different grace periods for Commitment calculation."""

import os
from datetime import timedelta

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


def get_commitment_with_grace(conn, sprint_id, start_date, grace_delta):
    grace_time = start_date + grace_delta
    result = conn.execute(
        text(
            f"""
        WITH added_before_grace AS (
            SELECT DISTINCT sic.issue_id
            FROM clean_jira.sprint_issues_changelog sic
            JOIN clean_jira.sprint_issues si ON si.issue_id = sic.issue_id AND si.sprint_id = sic.sprint_id
            JOIN clean_jira.issues i ON i.id = sic.issue_id
            JOIN clean_jira.issue_types it ON it.id = i.type_id
            WHERE sic.sprint_id = '{sprint_id}'
              AND it.name NOT ILIKE '%sub%'
              AND sic.action = 'added'
              AND sic.changed_at <= '{grace_time}'
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
        SELECT COALESCE(SUM(sp.story_points), 0)
        FROM added_before_grace abg
        JOIN last_action la ON la.issue_id = abg.issue_id
        LEFT JOIN sp ON sp.issue_id = abg.issue_id
        WHERE la.last_action = 'added'
    """
        )
    ).fetchone()
    return float(result[0])


def main():
    sprints = [
        ("Sprint 34", 83),
        ("Sprint 35", 80),
        ("Sprint 36", 45),
        ("Sprint 37", 92),
        ("Sprint 38", 78),
    ]

    graces = [
        ("No Grace", timedelta(seconds=0)),
        ("1 Min", timedelta(minutes=1)),
        ("1 Hour", timedelta(hours=1)),
        ("12 Hours", timedelta(hours=12)),
        ("24 Hours", timedelta(hours=24)),
    ]

    print(
        f"{'Sprint':<12} {'Jira':>6} | {'No Grace':>8} {'1 Min':>8} {'1 Hour':>8} {'12h':>8} {'24h':>8}"
    )
    print("-" * 75)

    with engine.connect() as conn:
        for sprint_name, jira_plan in sprints:
            sprint_info = conn.execute(
                text(
                    f"""
                SELECT s.id, s.start_date
                FROM clean_jira.sprints s
                JOIN clean_jira.projects p ON p.id = s.project_id
                WHERE p.external_key = 'TWMOB' AND s.name = '{sprint_name}'
            """
                )
            ).fetchone()

            if not sprint_info:
                continue
            sprint_id, start_date = sprint_info

            row = [sprint_name, jira_plan]
            for _name, delta in graces:
                sp = get_commitment_with_grace(conn, sprint_id, start_date, delta)
                row.append(f"{sp:.0f}")

            print(
                f"{row[0]:<12} {row[1]:>6} | {row[2]:>8} {row[3]:>8} {row[4]:>8} {row[5]:>8} {row[6]:>8}"
            )


if __name__ == "__main__":
    main()
