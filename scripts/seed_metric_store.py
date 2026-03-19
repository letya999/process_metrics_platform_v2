"""
Seeding script for Generic Long Metric Store (GLMS) foundation.
Populates metrics schema with grains, definitions, calculations, units, and dimension data.
"""

import os
from datetime import date

import polars as pl
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Infrastructure: Load environment and connect
load_dotenv()


def get_engine():
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")

    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(DATABASE_URL)


def seed_grains(conn):
    print("Seeding grains...")
    conn.execute(
        text(
            """
        INSERT INTO metrics.grains (grain_code, description) VALUES
        ('issue', 'One row per Jira issue'),
        ('sprint', 'One row per sprint'),
        ('week', 'One row per ISO week'),
        ('day', 'One row per calendar day'),
        ('release', 'One row per Jira release')
        ON CONFLICT (grain_code) DO NOTHING;
        """
        )
    )


def seed_definitions(conn):
    print("Seeding definitions...")
    conn.execute(
        text(
            """
        INSERT INTO metrics.definitions (metric_code) VALUES
        ('velocity'), ('lead_time'), ('throughput'), ('cfd'),
        ('backlog_growth'), ('ttm'), ('aging'), ('flow_efficiency')
        ON CONFLICT (metric_code) DO NOTHING;
        """
        )
    )


def seed_calculations(conn):
    print("Seeding calculations...")
    conn.execute(
        text(
            """
        WITH defs AS (SELECT id, metric_code FROM metrics.definitions),
             grns AS (SELECT id, grain_code FROM metrics.grains)
        INSERT INTO metrics.calculations (definition_id, calc_code, grain_id, unit_code, uses_commitment_points)
        VALUES
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_planned_sp', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'story_points', false),
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_completed_sp', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'story_points', false),
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_planned_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_completed_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'lead_time'), 'lead_time_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),

        ((SELECT id FROM defs WHERE metric_code = 'throughput'), 'throughput_count', (SELECT id FROM grns WHERE grain_code = 'week'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'cfd'), 'cfd_count', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_size', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_created', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_resolved', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_net_growth', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_avg_age_days', (SELECT id FROM grns WHERE grain_code = 'day'), 'days', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_stale_count', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_oldest_days', (SELECT id FROM grns WHERE grain_code = 'day'), 'days', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_stale_pct', (SELECT id FROM grns WHERE grain_code = 'day'), 'percent', false),

        ((SELECT id FROM defs WHERE metric_code = 'ttm'), 'ttm_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),

        ((SELECT id FROM defs WHERE metric_code = 'aging'), 'aging_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),

        ((SELECT id FROM defs WHERE metric_code = 'flow_efficiency'), 'flow_active_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),
        ((SELECT id FROM defs WHERE metric_code = 'flow_efficiency'), 'flow_wait_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),
        ((SELECT id FROM defs WHERE metric_code = 'flow_efficiency'), 'flow_efficiency_pct', (SELECT id FROM grns WHERE grain_code = 'issue'), 'percent', true)
        ON CONFLICT (calc_code) DO NOTHING;
        """
        )
    )


def seed_units(conn):
    print("Seeding units...")
    conn.execute(
        text(
            """
        INSERT INTO metrics.units (project_id, unit_code, display_symbol) VALUES
        (NULL, 'story_points', 'SP'),
        (NULL, 'issues', 'items'),
        (NULL, 'days', 'd'),
        (NULL, 'hours', 'h'),
        (NULL, 'percent', '%')
        ON CONFLICT DO NOTHING;
        """
        )
    )


def seed_dim_dates(conn):
    print("Seeding dim_dates (2024-2030)...")
    # Using Polars for efficient date generation
    start_date = date(2024, 1, 1)
    end_date = date(2030, 12, 31)

    dates = pl.date_range(start_date, end_date, interval="1d", eager=True).alias(
        "full_date"
    )

    df_dates = pl.DataFrame({"full_date": dates}).with_columns(
        [
            pl.col("full_date").dt.strftime("%Y%m%d").cast(pl.Int32).alias("time_id"),
            pl.col("full_date").dt.week().alias("week_num"),
            pl.col("full_date").dt.month().alias("month_num"),
            ((pl.col("full_date").dt.month() - 1) // 3 + 1).alias("quarter"),
            pl.col("full_date").dt.year().alias("year"),
        ]
    )

    # Write to DB using ADBC if possible, but for seeding 2.5k rows standard is fine
    # We'll use a simple insert to avoid extra dependencies if possible
    # but since we have polars, let's try write_database
    try:
        uri = os.getenv("DATABASE_URL")
        if not uri:
            db_user = os.getenv("POSTGRES_USER", "postgres")
            db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
            db_host = os.getenv("POSTGRES_HOST", "localhost")
            db_port = os.getenv("POSTGRES_PORT", "5432")
            db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")
            uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        df_dates.write_database(
            table_name="metrics.dim_dates",
            connection=uri,
            if_table_exists="append",  # dim_dates is unique by time_id, but write_database doesn't support ON CONFLICT easily
            engine="adbc",
        )
    except Exception as e:
        print(f"  Warning: ADBC write failed, falling back to manual insert: {e}")
        # Manual insert for idempotency
        for row in df_dates.to_dicts():
            conn.execute(
                text(
                    "INSERT INTO metrics.dim_dates (time_id, full_date, week_num, month_num, quarter, year) VALUES (:time_id, :full_date, :week_num, :month_num, :quarter, :year) ON CONFLICT (time_id) DO NOTHING"
                ),
                row,
            )


def sync_dim_projects(conn):
    print("Syncing dim_projects...")
    conn.execute(
        text(
            """
        INSERT INTO metrics.dim_projects (project_id, project_key)
        SELECT id, external_key FROM clean_jira.projects
        ON CONFLICT (project_id) DO UPDATE SET project_key = EXCLUDED.project_key;
        """
        )
    )


def seed_slice_rules(conn):
    print("Seeding default slice_rules...")
    conn.execute(
        text(
            """
        INSERT INTO metrics.slice_rules (rule_name, source_table, group_by_source_column, enabled) VALUES
        ('By Issue Type', 'clean_jira.issue_types', 'name', true),
        ('By Sprint', 'clean_jira.sprints', 'name', true)
        ON CONFLICT (rule_name) DO UPDATE SET
            source_table = EXCLUDED.source_table,
            group_by_source_column = EXCLUDED.group_by_source_column;
        """
        )
    )


def infer_commitment_rules(conn):
    print("Inferring commitment_rules from board columns...")
    # Find boards and their columns
    boards = conn.execute(
        text("SELECT id, project_id, name FROM clean_jira.boards")
    ).fetchall()

    # We also need calculation IDs for lead_time_days
    lt_calc_id = conn.execute(
        text("SELECT id FROM metrics.calculations WHERE calc_code = 'lead_time_days'")
    ).scalar()

    if not lt_calc_id:
        print(
            "  Error: lead_time_days calculation not found. Skipping commitment rules."
        )
        return

    for board_id, project_id, board_name in boards:
        # Heuristic: Find "In Progress" (start) and "Done" (end)
        columns = conn.execute(
            text(
                "SELECT id, name FROM clean_jira.board_columns WHERE board_id = :board_id ORDER BY position"
            ),
            {"board_id": board_id},
        ).fetchall()

        start_col = None
        end_col = None

        for col_id, col_name in columns:
            name_lower = col_name.lower()
            if not start_col and any(
                word in name_lower
                for word in ["in progress", "в работе", "progress", "active"]
            ):
                start_col = (col_id, col_name)
            if any(
                word in name_lower
                for word in ["done", "готово", "closed", "resolved", "completed"]
            ):
                end_col = (col_id, col_name)

        if start_col and end_col:
            print(f"  Board '{board_name}': inferred {start_col[1]} -> {end_col[1]}")
            conn.execute(
                text(
                    """
                INSERT INTO metrics.commitment_rules (
                    project_id, board_id, target_calculation_id, target_calculation_name,
                    start_column_id, end_column_id, start_column_name_snapshot, end_column_name_snapshot
                ) VALUES (
                    :project_id, :board_id, :calc_id, 'lead_time_days',
                    :start_id, :end_id, :start_name, :end_name
                ) ON CONFLICT DO NOTHING;
                """
                ),
                {
                    "project_id": project_id,
                    "board_id": board_id,
                    "calc_id": lt_calc_id,
                    "start_id": start_col[0],
                    "end_id": end_col[0],
                    "start_name": start_col[1],
                    "end_name": end_col[1],
                },
            )


def main():
    engine = get_engine()
    with engine.begin() as conn:
        seed_grains(conn)
        seed_definitions(conn)
        seed_calculations(conn)
        seed_units(conn)
        seed_dim_dates(conn)
        sync_dim_projects(conn)
        seed_slice_rules(conn)
        infer_commitment_rules(conn)
    print("\nSeeding completed successfully!")


if __name__ == "__main__":
    main()
