"""Debug the specific issue - why 85 SP instead of 75 SP for Sprint 36?"""

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

OUTPUT_FILE = "debug_sp_discrepancy.txt"


def main():
    """Debug 85 SP vs 75 SP discrepancy."""

    # Jira completed (from the sprint report)
    jira_completed = {
        "TWMOB-1906": 8,
        "TWMOB-1961": 5,
        "TWMOB-1963": 5,
        "TWMOB-2034": 2,
        "TWMOB-2073": 5,
        "TWMOB-2088": 5,
        "TWMOB-2194": 8,
        "TWMOB-2198": 2,
        "TWMOB-2202": 3,
        "TWMOB-2210": 0,
        "TWMOB-2211": 2,
        "TWMOB-2213": 1,
        "TWMOB-2215": 2,
        "TWMOB-2217": 0,
        "TWMOB-2219": 2,
        "TWMOB-2223": 2,
        "TWMOB-2231": 2,
        "TWMOB-2235": 1,
        "TWMOB-2240": 5,
        "TWMOB-2242": 5,
        "TWMOB-2262": 0,
        "TWMOB-2275": 1,
        "TWMOB-2277": 1,
        "TWMOB-2282": 1,
        "TWMOB-2284": 3,
        "TWMOB-2292": 2,
        "TWMOB-2323": 2,
    }

    # Our completed (from the debug output)
    our_completed = [
        ("TWMOB-2240", 5),
        ("TWMOB-2146", 1),
        ("TWMOB-2219", 2),
        ("TWMOB-2236", 0),
        ("TWMOB-2234", 0),
        ("TWMOB-2266", 0),
        ("TWMOB-2088", 5),
        ("TWMOB-2241", 0),
        ("TWMOB-2376", 0),
        ("TWMOB-2238", 1),
        ("TWMOB-2384", 0),
        ("TWMOB-2242", 5),
        ("TWMOB-2228", 1),
        ("TWMOB-2297", 2),
        ("TWMOB-2218", 0),
        ("TWMOB-2113", 0),
        ("TWMOB-2036", 0),
        ("TWMOB-2346", 0),
        ("TWMOB-2231", 2),
        ("TWMOB-2263", 0),
        ("TWMOB-2084", 0),
        ("TWMOB-2382", 0),
        ("TWMOB-2275", 1),
        ("TWMOB-2371", 0),
        ("TWMOB-2115", 0),
        ("TWMOB-2260", 0),
        ("TWMOB-2364", 0),
        ("TWMOB-2269", 0),
        ("TWMOB-2198", 2),
        ("TWMOB-2372", 0),
        ("TWMOB-2276", 0),
        ("TWMOB-2268", 0),
        ("TWMOB-2292", 2),
        ("TWMOB-2361", 0),
        ("TWMOB-2320", 1),
        ("TWMOB-2223", 2),
        ("TWMOB-2277", 1),
        ("TWMOB-2389", 0),
        ("TWMOB-1907", 0),
        ("TWMOB-2284", 3),
        ("TWMOB-2194", 8),
        ("TWMOB-1906", 8),
        ("TWMOB-2392", 0),
        ("TWMOB-2034", 2),
        ("TWMOB-2111", 0),
        ("TWMOB-2259", 0),
        ("TWMOB-2235", 1),
        ("TWMOB-2210", 0),
        ("TWMOB-2217", 0),
        ("TWMOB-2374", 0),
        ("TWMOB-2232", 0),
        ("TWMOB-1963", 5),
        ("TWMOB-2262", 0),
        ("TWMOB-2323", 2),
        ("TWMOB-2216", 0),
        ("TWMOB-2114", 0),
        ("TWMOB-2214", 0),
        ("TWMOB-1962", 0),
        ("TWMOB-2073", 5),
        ("TWMOB-2195", 0),
        ("TWMOB-2109", 1),
        ("TWMOB-1013", 0),
        ("TWMOB-2373", 0),
        ("TWMOB-2299", 0),
        ("TWMOB-2093", 0),
        ("TWMOB-2212", 0),
        ("TWMOB-2163", 0),
        ("TWMOB-2385", 0),
        ("TWMOB-2293", 0),
        ("TWMOB-2383", 0),
        ("TWMOB-2202", 3),
        ("TWMOB-1961", 5),
        ("TWMOB-2285", 0),
        ("TWMOB-2270", 1),
        ("TWMOB-2220", 0),
        ("TWMOB-2391", 0),
        ("TWMOB-2390", 0),
        ("TWMOB-2074", 0),
        ("TWMOB-2213", 1),
        ("TWMOB-2387", 0),
        ("TWMOB-2215", 2),
        ("TWMOB-2245", 0),
        ("TWMOB-2203", 0),
        ("TWMOB-2282", 1),
        ("TWMOB-2199", 0),
        ("TWMOB-2315", 1),
        ("TWMOB-2227", 1),
        ("TWMOB-2211", 2),
        ("TWMOB-2360", 0),
        ("TWMOB-1964", 0),
        ("TWMOB-2224", 0),
        ("TWMOB-2243", 0),
        ("TWMOB-2267", 0),
        ("TWMOB-2324", 0),
    ]

    our_keys = set(k for k, _ in our_completed)
    jira_keys = set(jira_completed.keys())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("SP DISCREPANCY ANALYSIS: 85 SP vs 75 SP\n")
        f.write("=" * 80 + "\n\n")

        f.write(
            f"Jira completed: {len(jira_keys)} issues, {sum(jira_completed.values())} SP\n"
        )
        f.write(
            f"Our completed:  {len(our_keys)} issues, {sum(sp for _, sp in our_completed)} SP\n\n"
        )

        # Issues in our list but NOT in Jira
        extra = our_keys - jira_keys
        f.write(f"EXTRA ISSUES (in our list but not in Jira): {len(extra)}\n")
        extra_sp = 0
        for key in sorted(extra):
            sp = next(s for k, s in our_completed if k == key)
            extra_sp += sp
            f.write(f"  {key}: {sp} SP\n")
        f.write(f"  Total extra SP: {extra_sp}\n\n")

        # Missing issues
        missing = jira_keys - our_keys
        f.write(f"MISSING ISSUES (in Jira but not in our list): {len(missing)}\n")
        missing_sp = 0
        for key in sorted(missing):
            sp = jira_completed[key]
            missing_sp += sp
            f.write(f"  {key}: {sp} SP\n")
        f.write(f"  Total missing SP: {missing_sp}\n\n")

        f.write(
            f"Net difference: Our {extra_sp} extra - {missing_sp} missing = {extra_sp - missing_sp} SP\n"
        )
        f.write("Actual difference: 85 - 75 = 10 SP\n")

        # Check issue types for extra issues
        f.write("\n" + "=" * 80 + "\n")
        f.write("CHECKING EXTRA ISSUES (reason for inclusion)\n")
        f.write("=" * 80 + "\n\n")

        with engine.connect() as conn:
            # Get sprint info
            sprint = conn.execute(
                text(
                    """
                SELECT s.id, COALESCE(s.complete_date, s.end_date) as end_date
                FROM clean_jira.sprints s
                JOIN clean_jira.projects p ON p.id = s.project_id
                WHERE p.external_key = 'TWMOB' AND s.name = 'Sprint 36'
            """
                )
            ).fetchone()
            sprint_id, end_date = sprint

            for key in sorted(list(extra)[:10]):  # First 10 extra issues
                result = conn.execute(
                    text(
                        f"""
                    SELECT
                        i.external_key,
                        it.name as issue_type,
                        ist.name as current_status,
                        ist.category as current_category
                    FROM clean_jira.issues i
                    JOIN clean_jira.issue_types it ON it.id = i.type_id
                    JOIN clean_jira.issue_statuses ist ON ist.id = i.status_id
                    WHERE i.external_key = '{key}'
                """
                    )
                ).fetchone()

                if result:
                    f.write(
                        f"{result[0]}: type={result[1]}, status={result[2]} ({result[3]})\n"
                    )

                    # Check if in Sprint 36 final scope
                    in_sprint = conn.execute(
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
                    f.write(
                        f"  In Sprint 36 changelog: {in_sprint[0] if in_sprint else 'NO'}\n"
                    )

                    # Check status at sprint end
                    status_at_end = conn.execute(
                        text(
                            f"""
                        SELECT DISTINCT ON (i.id) ist.name, ist.category, isc.changed_at
                        FROM clean_jira.issues i
                        JOIN clean_jira.issue_status_changelog isc ON isc.issue_id = i.id
                        JOIN clean_jira.issue_statuses ist ON ist.id = isc.to_status_id
                        WHERE i.external_key = '{key}' AND isc.changed_at <= '{end_date}'
                        ORDER BY i.id, isc.changed_at DESC
                    """
                        )
                    ).fetchone()
                    if status_at_end:
                        f.write(
                            f"  Status at sprint end: {status_at_end[0]} ({status_at_end[1]}) at {status_at_end[2]}\n"
                        )
                    else:
                        f.write("  NO status changelog before sprint end\n")
                    f.write("\n")

    print(f"Analysis written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
