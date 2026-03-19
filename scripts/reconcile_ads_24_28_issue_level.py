import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

FALLBACK_EXPECTED = {
    24: {"completed": {"TWAD-391", "TWAD-414", "TWAD-430"}, "removed": set()},
    25: {"completed": {"TWAD-411", "TWAD-416"}, "removed": {"TWAD-403", "TWAD-406"}},
    26: {
        "completed": {"TWAD-345", "TWAD-436", "TWAD-453"},
        "removed": {"TWAD-438", "TWAD-451"},
    },
    27: {
        "completed": {
            "TWAD-3",
            "TWAD-403",
            "TWAD-406",
            "TWAD-443",
            "TWAD-449",
            "TWAD-455",
            "TWAD-460",
            "TWAD-480",
        },
        "removed": set(),
    },
    28: {
        "completed": {"TWAD-445", "TWAD-451", "TWAD-458", "TWAD-484"},
        "removed": {"TWAD-482", "TWAD-487"},
    },
}


def _load_expected() -> dict[int, dict[str, set[str]]]:
    """Load expected issue sets from sprintreport artifact if available."""
    candidates = [
        Path("scripts/jira_ads_24_28_sprintreport_current.json"),
        Path("scripts/jira_ads_24_28_sprintreport.json"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        parsed: dict[int, dict[str, set[str]]] = {}
        for sprint_num_str, payload in raw.items():
            sprint_num = int(sprint_num_str)
            parsed[sprint_num] = {
                "completed": set(payload.get("completed", [])),
                "removed": set(payload.get("punted", [])),
            }
        if parsed:
            return parsed
    return FALLBACK_EXPECTED


def main() -> None:
    expected = _load_expected()

    load_dotenv(dotenv_path=Path(".env"))
    engine = create_engine(
        "postgresql://{user}:{pwd}@{host}:{port}/{db}".format(
            user=os.getenv("POSTGRES_USER", "postgres"),
            pwd=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            db=os.getenv("POSTGRES_DB", "process_metrics_v2"),
        )
    )

    sprint_query = text(
        """
        SELECT
            (regexp_match(s.name, '([0-9]+)$'))[1]::int AS sprint_num,
            s.id AS sprint_id,
            s.name AS sprint_name,
            s.start_date,
            COALESCE(s.complete_date, s.end_date) AS effective_end
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWAD'
          AND s.name LIKE 'ADS %'
          AND (regexp_match(s.name, '([0-9]+)$'))[1]::int BETWEEN 24 AND 28
        ORDER BY sprint_num
        """
    )

    with engine.connect() as conn:
        sprints = conn.execute(sprint_query).mappings().all()

        print("sprint,kind,expected_count,actual_count,missing_in_db,extra_in_db")

        for sprint in sprints:
            sprint_num = int(sprint["sprint_num"])
            sprint_id = sprint["sprint_id"]
            start_date = sprint["start_date"]
            effective_end = sprint["effective_end"]

            completed_actual = _load_completed_keys(conn, sprint_id, effective_end)
            removed_actual = _load_removed_keys(conn, sprint_id)

            _print_diff(
                sprint_num,
                "completed",
                expected[sprint_num]["completed"],
                completed_actual,
            )
            _print_diff(
                sprint_num, "removed", expected[sprint_num]["removed"], removed_actual
            )

            added_after_start = _load_added_after_start_keys(
                conn, sprint_id, start_date
            )
            print(
                f"{sprint_num},added_after_start,,{len(added_after_start)},,"
                f"{' '.join(sorted(added_after_start))}"
            )


def _load_removed_keys(conn, sprint_id) -> set[str]:
    q = text(
        """
        WITH last_actions AS (
            SELECT
                sic.issue_id,
                (ARRAY_AGG(sic.action ORDER BY sic.changed_at DESC))[1] AS last_action
            FROM clean_jira.sprint_issues_changelog sic
            WHERE sic.sprint_id = :sprint_id
            GROUP BY sic.issue_id
        )
        SELECT i.external_key
        FROM last_actions la
        JOIN clean_jira.issues i ON i.id = la.issue_id
        WHERE la.last_action = 'removed'
        ORDER BY i.external_key
        """
    )
    rows = conn.execute(q, {"sprint_id": sprint_id}).fetchall()
    return {r[0] for r in rows}


def _load_added_after_start_keys(conn, sprint_id, start_date) -> set[str]:
    q = text(
        """
        WITH first_added AS (
            SELECT
                sic.issue_id,
                MIN(sic.changed_at) FILTER (WHERE sic.action = 'added') AS first_added_at
            FROM clean_jira.sprint_issues_changelog sic
            WHERE sic.sprint_id = :sprint_id
            GROUP BY sic.issue_id
        )
        SELECT i.external_key
        FROM first_added fa
        JOIN clean_jira.issues i ON i.id = fa.issue_id
        WHERE fa.first_added_at > :start_date
        ORDER BY i.external_key
        """
    )
    rows = conn.execute(
        q, {"sprint_id": sprint_id, "start_date": start_date}
    ).fetchall()
    return {r[0] for r in rows}


def _load_completed_keys(conn, sprint_id, effective_end) -> set[str]:
    q = text(
        """
        WITH final_scope AS (
            WITH last_actions AS (
                SELECT
                    sic.issue_id,
                    (ARRAY_AGG(sic.action ORDER BY sic.changed_at DESC))[1] AS last_action
                FROM clean_jira.sprint_issues_changelog sic
                WHERE sic.sprint_id = :sprint_id
                GROUP BY sic.issue_id
            ),
            cl_scope AS (
                SELECT issue_id FROM last_actions WHERE last_action = 'added'
            ),
            fallback_scope AS (
                SELECT si.issue_id
                FROM clean_jira.sprint_issues si
                LEFT JOIN last_actions la ON la.issue_id = si.issue_id
                WHERE si.sprint_id = :sprint_id
                  AND si.is_active = true
                  AND la.issue_id IS NULL
            )
            SELECT issue_id FROM cl_scope
            UNION
            SELECT issue_id FROM fallback_scope
        ),
        status_before_end AS (
            SELECT
                fs.issue_id,
                (ARRAY_AGG(isc.to_status_id ORDER BY isc.changed_at DESC))[1] AS status_id
            FROM final_scope fs
            LEFT JOIN clean_jira.issue_status_changelog isc
              ON isc.issue_id = fs.issue_id
             AND isc.changed_at <= :effective_end
            GROUP BY fs.issue_id
        ),
        no_before_end AS (
            SELECT fs.issue_id
            FROM final_scope fs
            LEFT JOIN status_before_end sbe ON sbe.issue_id = fs.issue_id
            WHERE sbe.status_id IS NULL
        ),
        first_after_end AS (
            SELECT
                nbe.issue_id,
                (ARRAY_AGG(isc.from_status_id ORDER BY isc.changed_at ASC))[1] AS status_id
            FROM no_before_end nbe
            LEFT JOIN clean_jira.issue_status_changelog isc
              ON isc.issue_id = nbe.issue_id
             AND isc.changed_at > :effective_end
            GROUP BY nbe.issue_id
        ),
        effective_status AS (
            SELECT issue_id, status_id FROM status_before_end WHERE status_id IS NOT NULL
            UNION ALL
            SELECT issue_id, status_id FROM first_after_end WHERE status_id IS NOT NULL
        )
        SELECT i.external_key
        FROM effective_status es
        JOIN clean_jira.issue_statuses st ON st.id = es.status_id
        JOIN clean_jira.issues i ON i.id = es.issue_id
        WHERE st.category = 'done'
        ORDER BY i.external_key
        """
    )
    rows = conn.execute(
        q, {"sprint_id": sprint_id, "effective_end": effective_end}
    ).fetchall()
    return {r[0] for r in rows}


def _print_diff(
    sprint_num: int, kind: str, expected: set[str], actual: set[str]
) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    print(
        f"{sprint_num},{kind},{len(expected)},{len(actual)},"
        f"{' '.join(missing)},{' '.join(extra)}"
    )


if __name__ == "__main__":
    main()
