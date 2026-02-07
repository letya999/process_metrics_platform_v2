"""Check missing issues for Sprint 37."""

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
    sprint_id = conn.execute(
        text("SELECT id FROM clean_jira.sprints WHERE name = 'Sprint 37'")
    ).scalar()

    issues = conn.execute(
        text(
            f"""
        SELECT i.external_key,
               (SELECT action FROM clean_jira.sprint_issues_changelog WHERE issue_id = i.id AND sprint_id = '{sprint_id}' ORDER BY changed_at DESC LIMIT 1) as last_action,
               COALESCE((SELECT MAX(CASE WHEN fv.json_value::text ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN (fv.json_value::text)::numeric ELSE 0 END)
                FROM clean_jira.field_values fv JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
                WHERE fv.issue_id = i.id AND fk.external_key = 'customfield_10036'), 0) as sp
        FROM clean_jira.issues i
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE i.id IN (
            SELECT issue_id FROM clean_jira.sprint_issues_changelog WHERE sprint_id = '{sprint_id}'
        )
        AND it.name NOT ILIKE '%sub%'
        AND i.id NOT IN (
            SELECT issue_id FROM clean_jira.sprint_issues WHERE sprint_id = '{sprint_id}'
        )
    """
        )
    ).fetchall()

    print(f"{'Key':<12} {'LastAct':<10} {'SP':>4}")
    for k, la, sp in issues:
        print(f"{k:<12} {la:<10} {sp:>4.0f}")
