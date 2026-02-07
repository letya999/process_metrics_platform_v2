"""
Compare multiple approaches for calculating Sprint Commitment (Plan) to match Jira Reports.
Target Sprints: 34, 35, 36, 37, 38.
"""

import os
from datetime import timedelta

import pandas as pd
import polars as pl
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

# Database connection
db_user = os.getenv("POSTGRES_USER", "postgres")
db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
engine = create_engine(DATABASE_URL)

JIRA_PLANS = {
    "Sprint 34": 83,
    "Sprint 35": 80,
    "Sprint 36": 45,
    "Sprint 37": 92,
    "Sprint 38": 78,
}


def load_data():
    """Load necessary data into Polars DataFrames."""
    print("Loading data...")
    query_sprints = """
        SELECT s.id::text, s.name, s.start_date, s.end_date, s.complete_date
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON p.id = s.project_id
        WHERE p.external_key = 'TWMOB'
          AND s.name IN ('Sprint 34', 'Sprint 35', 'Sprint 36', 'Sprint 37', 'Sprint 38')
    """
    sprints_df = pl.read_database(query_sprints, engine)

    # Ensure datetime types and Utf8 IDs
    # start_date might be returned as datetime object, so we might need to ensure it
    # If read_database gets datetimes, it usually handles them, but let's check schema

    query_changelog = """
        SELECT issue_id::text, sprint_id::text, action, changed_at
        FROM clean_jira.sprint_issues_changelog
    """
    changelog_df = pl.read_database(query_changelog, engine)

    query_issues = """
        SELECT i.id::text as issue_id, it.name as type_name
        FROM clean_jira.issues i
        JOIN clean_jira.issue_types it ON it.id = i.type_id
    """
    issues_df = pl.read_database(query_issues, engine)

    # Story Points (Aggregated to avoid duplicates)
    query_sp = """
        SELECT fv.issue_id::text, MAX(
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
    """
    sp_df = pl.read_database(query_sp, engine)
    # sp_df is already text/numeric, so Polars should be happy

    # Filter out sub-tasks
    non_sub_issues = issues_df.filter(
        ~pl.col("type_name").cast(pl.Utf8).str.to_lowercase().str.contains("sub")
    ).select("issue_id")

    # Filter changelog to target sprints and non-sub issues
    target_sprint_ids = sprints_df["id"].to_list()
    changelog_df = changelog_df.filter(
        pl.col("sprint_id").is_in(target_sprint_ids)
    ).join(non_sub_issues, on="issue_id", how="inner")

    return sprints_df, changelog_df, sp_df


def calculate_sp_sum(issue_ids, sp_df):
    if not issue_ids:
        return 0.0
    df = pl.DataFrame({"issue_id": list(set(issue_ids))}, schema={"issue_id": pl.Utf8})
    res = df.join(sp_df, on="issue_id", how="left")
    return res["story_points"].sum()


def get_issues_at_cutoff(sprint_id, cutoff_date, changelog_df):
    """
    Issues present in sprint at cutoff_date.
    Logic: Added <= cutoff AND (Last action <= cutoff is 'added').
    """
    sprint_logs = changelog_df.filter(pl.col("sprint_id") == sprint_id)

    # Filter events before cutoff
    valid_logs = sprint_logs.filter(pl.col("changed_at") <= cutoff_date)

    if valid_logs.is_empty():
        return []

    # Get last action before cutoff
    last_actions = valid_logs.sort("changed_at", descending=True).unique(
        subset=["issue_id"], keep="first"
    )

    # Keep only those where last action was 'added'
    active_issues = last_actions.filter(pl.col("action") == "added")[
        "issue_id"
    ].to_list()
    return active_issues


def get_issues_ignore_removals(sprint_id, cutoff_date, changelog_df):
    """Issues added <= cutoff, regardless of removal."""
    sprint_logs = changelog_df.filter(
        (pl.col("sprint_id") == sprint_id)
        & (pl.col("changed_at") <= cutoff_date)
        & (pl.col("action") == "added")
    )
    return sprint_logs["issue_id"].unique().to_list()


def analyze_approaches():
    try:
        print("Starting analysis...")
        sprints_df, changelog_df, sp_df = load_data()
        print(
            f"Loaded {len(sprints_df)} sprints, {len(changelog_df)} changelog entries, {len(sp_df)} SP entries."
        )

        results = []

        # Ensure sp_df has correct types
        sp_df = sp_df.with_columns(
            pl.col("story_points").cast(pl.Float64).fill_null(0.0)
        )

        for row in sprints_df.iter_rows(named=True):
            sprint_name = row["name"]
            print(f"Processing {sprint_name}...")
            sprint_id = row["id"]
            start_date = row["start_date"]

            # 1. Strict Start (Snapshot at start)
            ids_strict = get_issues_at_cutoff(sprint_id, start_date, changelog_df)
            sp_strict = calculate_sp_sum(ids_strict, sp_df)

            # 2. Grace 15m (Snapshot at start + 15m)
            ids_15m = get_issues_at_cutoff(
                sprint_id, start_date + timedelta(minutes=15), changelog_df
            )
            sp_15m = calculate_sp_sum(ids_15m, sp_df)

            # 3. Grace 1h (Snapshot at start + 60m)
            ids_1h = get_issues_at_cutoff(
                sprint_id, start_date + timedelta(hours=1), changelog_df
            )
            sp_1h = calculate_sp_sum(ids_1h, sp_df)

            # 4. Grace 24h (Snapshot at start + 24h)
            ids_24h = get_issues_at_cutoff(
                sprint_id, start_date + timedelta(hours=24), changelog_df
            )
            sp_24h = calculate_sp_sum(ids_24h, sp_df)

            # 5. Ignore Removals (Added <= Start)
            ids_ir_strict = get_issues_ignore_removals(
                sprint_id, start_date, changelog_df
            )
            sp_ir_strict = calculate_sp_sum(ids_ir_strict, sp_df)

            # 6. Ignore Removals (Grace 1h) - "Ever added in first hour"
            ids_ir_1h = get_issues_ignore_removals(
                sprint_id, start_date + timedelta(hours=1), changelog_df
            )
            sp_ir_1h = calculate_sp_sum(ids_ir_1h, sp_df)

            # 7. All Ever Added (Total Footprint)
            ids_all = (
                changelog_df.filter(
                    (pl.col("sprint_id") == sprint_id) & (pl.col("action") == "added")
                )["issue_id"]
                .unique()
                .to_list()
            )
            sp_all = calculate_sp_sum(ids_all, sp_df)

            jira_val = JIRA_PLANS.get(sprint_name, 0)

            results.append(
                {
                    "Sprint": sprint_name,
                    "Jira": jira_val,
                    "1. Strict": sp_strict,
                    "2. Grace 15m": sp_15m,
                    "3. Grace 1h": sp_1h,
                    "4. Grace 24h": sp_24h,
                    "5. Ign Rem (Start)": sp_ir_strict,
                    "6. Ign Rem (1h)": sp_ir_1h,
                    "7. All Ever": sp_all,
                }
            )

        # Prepare DataFrame
        df_res = pd.DataFrame(results)

        # Write full analysis to file
        with open("commitment_approaches_comparison.txt", "w", encoding="utf-8") as f:
            f.write("=== PLAN CALCULATION COMPARISON ===\n\n")

            # Formatting table
            headers = [
                "Sprint",
                "Jira",
                "1. Strict",
                "2. Grace 15m",
                "3. Grace 1h",
                "4. Grace 24h",
                "5. Ign Rem (Start)",
                "6. Ign Rem (1h)",
                "7. All Ever",
            ]
            f.write(f"{'  '.join([f'{h:<15}' for h in headers])}\n")
            f.write("-" * 150 + "\n")

            approaches = headers[2:]
            error_sums = {app: 0 for app in approaches}

            for _index, row in df_res.iterrows():
                line = [f"{row['Sprint']:<15}", f"{row['Jira']:<15}"]
                for app in approaches:
                    val = row[app]
                    diff = abs(val - row["Jira"])
                    error_sums[app] += diff
                    line.append(f"{val:<15.0f}")
                f.write("  ".join(line) + "\n")

            f.write("\n\n=== TOTAL ABSOLUTE ERROR (Lower is Better) ===\n")
            sorted_errors = sorted(error_sums.items(), key=lambda x: x[1])
            for app, err in sorted_errors:
                f.write(f"{app:<20}: {err:.0f}\n")

            f.write(f"\n✅ BEST APPROACH: {sorted_errors[0][0]}\n")

        print("Analysis written to commitment_approaches_comparison.txt")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    analyze_approaches()
