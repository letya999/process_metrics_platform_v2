"""convert_mvs_to_tables

Revision ID: 0011_convert_mvs_to_tables
Revises: 0010_fix_velocity_logic
Create Date: 2026-01-15 10:30:00.000000

Convert Materialized Views to regular Tables for Python-based metrics calculation.

This migration:
1. Drops all metrics Materialized Views
2. Creates regular tables with the same schema
3. Prepares the schema for Python/Polars-based calculation logic
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_convert_mvs_to_tables"
down_revision = "0010_fix_velocity_logic"
branch_labels = None
depends_on = None


def upgrade():
    """Convert Materialized Views to regular Tables."""

    # ==========================================
    # Step 1: Drop all Materialized Views
    # ==========================================

    # Drop presentation views first (they depend on fact tables)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.mv_lead_time CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.mv_throughput CASCADE;")

    # Drop fact table MVs (bins depend on base tables)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins CASCADE;")
    op.execute(
        "DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins_slice CASCADE;"
    )

    # Drop slice MVs
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity_slice CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_slice CASCADE;")

    # Drop base fact MVs
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time CASCADE;")

    # ==========================================
    # Step 2: Create fact_velocity as TABLE
    # ==========================================
    op.execute(
        """
        CREATE TABLE metrics.fact_velocity (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            iteration_id UUID NOT NULL,
            iteration_name TEXT,
            start_date DATE,
            end_date DATE,
            planned_story_points NUMERIC DEFAULT 0,
            completed_story_points NUMERIC DEFAULT 0,
            planned_issues INTEGER DEFAULT 0,
            completed_issues INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),

            -- Foreign keys
            CONSTRAINT fk_velocity_project FOREIGN KEY (project_id)
                REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            CONSTRAINT fk_velocity_iteration FOREIGN KEY (iteration_id)
                REFERENCES clean_jira.sprints(id) ON DELETE CASCADE
        );

        -- Indexes for query performance
        CREATE INDEX idx_fact_velocity_project ON metrics.fact_velocity(project_id);
        CREATE INDEX idx_fact_velocity_iteration ON metrics.fact_velocity(iteration_id);
        CREATE INDEX idx_fact_velocity_dates ON metrics.fact_velocity(start_date, end_date);
    """
    )

    # ==========================================
    # Step 3: Create fact_velocity_slice as TABLE
    # ==========================================
    op.execute(
        """
        CREATE TABLE metrics.fact_velocity_slice (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            iteration_id UUID NOT NULL,
            iteration_name TEXT,
            start_date DATE,
            end_date DATE,
            issue_type TEXT NOT NULL,
            planned_story_points NUMERIC DEFAULT 0,
            completed_story_points NUMERIC DEFAULT 0,
            planned_issues INTEGER DEFAULT 0,
            completed_issues INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),

            -- Foreign keys
            CONSTRAINT fk_velocity_slice_project FOREIGN KEY (project_id)
                REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            CONSTRAINT fk_velocity_slice_iteration FOREIGN KEY (iteration_id)
                REFERENCES clean_jira.sprints(id) ON DELETE CASCADE
        );

        -- Indexes
        CREATE INDEX idx_fact_velocity_slice_project ON metrics.fact_velocity_slice(project_id);
        CREATE INDEX idx_fact_velocity_slice_iteration ON metrics.fact_velocity_slice(iteration_id);
        CREATE INDEX idx_fact_velocity_slice_type ON metrics.fact_velocity_slice(issue_type);
    """
    )

    # ==========================================
    # Step 4: Create fact_lead_time as TABLE
    # ==========================================
    op.execute(
        """
        CREATE TABLE metrics.fact_lead_time (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id UUID NOT NULL,
            project_id UUID NOT NULL,
            issue_key TEXT,
            issue_type TEXT,
            commitment_start_at TIMESTAMPTZ,
            commitment_end_at TIMESTAMPTZ,
            lead_time_days NUMERIC,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),

            -- Foreign keys
            CONSTRAINT fk_lead_time_issue FOREIGN KEY (issue_id)
                REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            CONSTRAINT fk_lead_time_project FOREIGN KEY (project_id)
                REFERENCES clean_jira.projects(id) ON DELETE CASCADE
        );

        -- Indexes
        CREATE INDEX idx_fact_lead_time_issue ON metrics.fact_lead_time(issue_id);
        CREATE INDEX idx_fact_lead_time_project ON metrics.fact_lead_time(project_id);
        CREATE INDEX idx_fact_lead_time_dates ON metrics.fact_lead_time(commitment_start_at, commitment_end_at);
        CREATE INDEX idx_fact_lead_time_days ON metrics.fact_lead_time(lead_time_days);
    """
    )

    # ==========================================
    # Step 5: Create fact_lead_time_slice as TABLE
    # ==========================================
    op.execute(
        """
        CREATE TABLE metrics.fact_lead_time_slice (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            issue_type TEXT NOT NULL,
            avg_lead_time_days NUMERIC,
            median_lead_time_days NUMERIC,
            p90_lead_time_days NUMERIC,
            total_issues INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),

            -- Foreign keys
            CONSTRAINT fk_lead_time_slice_project FOREIGN KEY (project_id)
                REFERENCES clean_jira.projects(id) ON DELETE CASCADE
        );

        -- Indexes
        CREATE INDEX idx_fact_lead_time_slice_project ON metrics.fact_lead_time_slice(project_id);
        CREATE INDEX idx_fact_lead_time_slice_type ON metrics.fact_lead_time_slice(issue_type);
    """
    )

    # ==========================================
    # Step 6: Create fact_lead_time_bins as TABLE
    # ==========================================
    op.execute(
        """
        CREATE TABLE metrics.fact_lead_time_bins (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            bin_number INTEGER NOT NULL,
            tickets_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),

            -- Foreign keys
            CONSTRAINT fk_lead_time_bins_project FOREIGN KEY (project_id)
                REFERENCES clean_jira.projects(id) ON DELETE CASCADE,

            -- Unique constraint (one row per project per bin)
            CONSTRAINT uq_lead_time_bins_project_bin UNIQUE (project_id, bin_number)
        );

        -- Indexes
        CREATE INDEX idx_fact_lead_time_bins_project ON metrics.fact_lead_time_bins(project_id);
        CREATE INDEX idx_fact_lead_time_bins_bin ON metrics.fact_lead_time_bins(bin_number);
    """
    )

    # ==========================================
    # Step 7: Create fact_lead_time_bins_slice as TABLE
    # ==========================================
    op.execute(
        """
        CREATE TABLE metrics.fact_lead_time_bins_slice (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            issue_type TEXT NOT NULL,
            bin_number INTEGER NOT NULL,
            tickets_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),

            -- Foreign keys
            CONSTRAINT fk_lead_time_bins_slice_project FOREIGN KEY (project_id)
                REFERENCES clean_jira.projects(id) ON DELETE CASCADE,

            -- Unique constraint
            CONSTRAINT uq_lead_time_bins_slice UNIQUE (project_id, issue_type, bin_number)
        );

        -- Indexes
        CREATE INDEX idx_fact_lead_time_bins_slice_project ON metrics.fact_lead_time_bins_slice(project_id);
        CREATE INDEX idx_fact_lead_time_bins_slice_type ON metrics.fact_lead_time_bins_slice(issue_type);
    """
    )

    # ==========================================
    # Step 8: Recreate presentation views (as simple VIEWs, not MVs)
    # ==========================================

    # mv_velocity - just adds completion rate
    op.execute(
        """
        CREATE OR REPLACE VIEW metrics.mv_velocity AS
        SELECT
            project_id,
            iteration_id,
            iteration_name,
            start_date,
            end_date,
            planned_story_points,
            completed_story_points,
            planned_issues,
            completed_issues,
            CASE
                WHEN planned_story_points > 0
                THEN ROUND(completed_story_points / planned_story_points * 100, 2)
                ELSE 0
            END AS completion_rate_sp,
            CASE
                WHEN planned_issues > 0
                THEN ROUND(completed_issues::NUMERIC / planned_issues * 100, 2)
                ELSE 0
            END AS completion_rate_issues,
            created_at,
            updated_at
        FROM metrics.fact_velocity
        ORDER BY start_date DESC;
    """
    )

    # mv_lead_time - aggregates by project
    op.execute(
        """
        CREATE OR REPLACE VIEW metrics.mv_lead_time AS
        SELECT
            project_id,
            COUNT(*) AS total_issues,
            ROUND(AVG(lead_time_days)::NUMERIC, 2) AS avg_lead_time_days,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lead_time_days)::NUMERIC, 2) AS median_lead_time_days,
            ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY lead_time_days)::NUMERIC, 2) AS p90_lead_time_days,
            MIN(commitment_start_at) AS earliest_start,
            MAX(commitment_end_at) AS latest_end
        FROM metrics.fact_lead_time
        GROUP BY project_id;
    """
    )

    # mv_throughput - counts issues completed per day
    op.execute(
        """
        CREATE OR REPLACE VIEW metrics.mv_throughput AS
        SELECT
            project_id,
            DATE(commitment_end_at) AS completed_date,
            COUNT(*) AS issues_completed,
            ROUND(AVG(lead_time_days)::NUMERIC, 2) AS avg_lead_time_days
        FROM metrics.fact_lead_time
        WHERE commitment_end_at IS NOT NULL
        GROUP BY project_id, DATE(commitment_end_at)
        ORDER BY completed_date DESC;
    """
    )


def downgrade():
    """Rollback: Convert tables back to Materialized Views."""

    # Drop tables
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time_bins_slice CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time_bins CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time_slice CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics.fact_velocity_slice CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics.fact_velocity CASCADE;")

    # Drop presentation views
    op.execute("DROP VIEW IF EXISTS metrics.mv_velocity CASCADE;")
    op.execute("DROP VIEW IF EXISTS metrics.mv_lead_time CASCADE;")
    op.execute("DROP VIEW IF EXISTS metrics.mv_throughput CASCADE;")

    # Note: Re-creating original MVs would require re-implementing the complex SQL logic
    # This is intentionally left incomplete as we don't want to roll back to MVs
    # If rollback is needed, restore from migration 0010
    print("WARNING: Downgrade does not recreate Materialized Views.")
    print("To restore old schema, apply migrations up to 0010_fix_velocity_logic.")
