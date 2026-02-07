"""Analyze Sprint 37 commitment."""

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
    sprint = conn.execute(
        text(
            """
        SELECT s.id, s.start_date FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 37'
    """
        )
    ).fetchone()
    sprint_id, start_date = sprint
    print(f"Sprint 37: start={start_date}")

    # Issues currently in sprint (final scope)
    issues = conn.execute(
        text(
            f"""
        SELECT i.external_key, it.name,
               (SELECT MIN(changed_at) FROM clean_jira.sprint_issues_changelog WHERE issue_id = i.id AND sprint_id = '{sprint_id}' AND action = 'added') as added_at,
               (SELECT MAX(changed_at) FROM clean_jira.sprint_issues_changelog WHERE issue_id = i.id AND sprint_id = '{sprint_id}') as last_cl_at,
               (SELECT action FROM clean_jira.sprint_issues_changelog WHERE issue_id = i.id AND sprint_id = '{sprint_id}' ORDER BY changed_at DESC LIMIT 1) as last_action,
               COALESCE((SELECT MAX(CASE WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN (fv.json_value::text)::numeric ELSE 0 END)
                FROM clean_jira.field_values fv JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                WHERE fv.issue_id = i.id AND fk.external_key = 'customfield_10036'), 0) as sp
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE si.sprint_id = '{sprint_id}' AND it.name NOT ILIKE '%sub%'
    """
        )
    ).fetchall()

    print(f"\n{'Key':<12} {'AddedAt':<25} {'LastAct':<8} {'SP':>4}")
    for k, _t, a, _l_t, l_a, sp in sorted(issues, key=lambda x: str(x[2])):
        print(f"{k:<12} {str(a):<25} {l_a or 'NONE':<8} {sp:>4.0f}")
