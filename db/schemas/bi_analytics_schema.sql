-- ============================================================================
-- BI Analytics Schema - Enhanced Structure
-- ============================================================================
-- Principles:
-- 1. Separation of metric configuration and data
-- 2. Universal dimension tables
-- 3. Slicing through polymorphic FK
-- 4. Normalization of reference data
-- 5. Expandable ENUMs through separate tables
-- ============================================================================

-- Create schema
CREATE SCHEMA IF NOT EXISTS bi_analytics;

-- ============================================================================
-- SECTION 1: ENUM REFERENCE TABLES (Expandable Enums)
-- ============================================================================

-- Commitment point roles
CREATE TABLE IF NOT EXISTS bi_analytics.enum_commitment_point_roles (
    role text PRIMARY KEY,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bi_analytics.enum_commitment_point_roles (role, description) VALUES
    ('commitment_start_lead_time', 'Lead Time start (moment when task is taken into work)'),
    ('commitment_end_lead_time', 'Lead Time end (moment when task is completed)')
ON CONFLICT (role) DO NOTHING;

-- Metric types
CREATE TABLE IF NOT EXISTS bi_analytics.enum_metric_types (
    metric_name text PRIMARY KEY,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bi_analytics.enum_metric_types (metric_name, description) VALUES
    ('velocity', 'Velocity (team speed per sprint)'),
    ('lead_time', 'Lead Time (task execution time)'),
    ('cfd', 'Cumulative Flow Diagram'),
    ('throughput', 'Throughput (system capacity)'),
    ('time_to_market', 'Time to Market (from idea to production)'),
    ('all', 'All metrics')
ON CONFLICT (metric_name) DO NOTHING;

-- Slice dimension types
CREATE TABLE IF NOT EXISTS bi_analytics.enum_slice_dimension_types (
    dimension_type text PRIMARY KEY,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bi_analytics.enum_slice_dimension_types (dimension_type, description) VALUES
    ('issue_type', 'Issue type (Story, Bug, Task, etc.)'),
    ('issue_statuses', 'Issue status'),
    ('custom_field_stream', 'Custom field stream'),
    ('sprint', 'Sprint')
ON CONFLICT (dimension_type) DO NOTHING;

-- ============================================================================
-- SECTION 2: METRIC CONFIGURATION
-- ============================================================================

-- Commitment point configuration for Lead Time calculation
CREATE TABLE IF NOT EXISTS bi_analytics.metric_config_commitment_points (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    board_column_id uuid NOT NULL REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE,
    role text NOT NULL REFERENCES bi_analytics.enum_commitment_point_roles(role),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(board_column_id, role)
);

CREATE INDEX idx_mcc_project_active ON bi_analytics.metric_config_commitment_points(project_id, is_active);
CREATE INDEX idx_mcc_board_column ON bi_analytics.metric_config_commitment_points(board_column_id);

COMMENT ON TABLE bi_analytics.metric_config_commitment_points IS 'Commitment point configuration for Lead Time (replaces board_commitment_points)';

-- Estimation field configuration (Story Points, T-Shirt Size, etc.)
CREATE TABLE IF NOT EXISTS bi_analytics.metric_config_estimation_fields (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    field_key_id uuid NOT NULL REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, field_key_id)
);

CREATE INDEX idx_mce_project_active ON bi_analytics.metric_config_estimation_fields(project_id, is_active);
CREATE INDEX idx_mce_field_key ON bi_analytics.metric_config_estimation_fields(field_key_id);
CREATE UNIQUE INDEX idx_mce_project_single_active
    ON bi_analytics.metric_config_estimation_fields(project_id)
    WHERE is_active = true;

COMMENT ON TABLE bi_analytics.metric_config_estimation_fields IS 'Estimation field configuration (replaces project_estimation_fields)';

-- Metric slicing rules
CREATE TABLE IF NOT EXISTS bi_analytics.metric_config_slice_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES platform.projects(id) ON DELETE CASCADE,
    metric_name text NOT NULL REFERENCES bi_analytics.enum_metric_types(metric_name),
    slice_dimension text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    enabled boolean NOT NULL DEFAULT true,
    top_n int NOT NULL DEFAULT 10,
    group_other boolean NOT NULL DEFAULT true,
    max_distinct_values int NOT NULL DEFAULT 50,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_mcsr_project_metric_dim
    ON bi_analytics.metric_config_slice_rules(COALESCE(project_id::text, 'global'), metric_name, slice_dimension);

CREATE INDEX idx_mcsr_project_enabled ON bi_analytics.metric_config_slice_rules(project_id, enabled);
CREATE INDEX idx_mcsr_metric ON bi_analytics.metric_config_slice_rules(metric_name);

COMMENT ON TABLE bi_analytics.metric_config_slice_rules IS 'Metric slicing rules (global and project-level)';

-- ============================================================================
-- SECTION 3: DIMENSION TABLES
-- ============================================================================

-- Date dimension
CREATE TABLE IF NOT EXISTS bi_analytics.dim_date (
    date date PRIMARY KEY,
    year int NOT NULL,
    quarter int NOT NULL,
    month int NOT NULL,
    day int NOT NULL,
    week int NOT NULL,
    day_of_week int NOT NULL,
    day_name text NOT NULL,
    month_name text NOT NULL,
    is_weekend boolean NOT NULL,
    is_holiday boolean NOT NULL DEFAULT false,
    fiscal_year int,
    fiscal_quarter int
);

CREATE INDEX idx_dim_date_year_month ON bi_analytics.dim_date(year, month);
CREATE INDEX idx_dim_date_year_quarter ON bi_analytics.dim_date(year, quarter);
CREATE INDEX idx_dim_date_fiscal ON bi_analytics.dim_date(fiscal_year, fiscal_quarter);

COMMENT ON TABLE bi_analytics.dim_date IS 'Date dimension with fiscal year support';
COMMENT ON COLUMN bi_analytics.dim_date.day_of_week IS '1=Monday, 7=Sunday';

-- Issue type dimension
CREATE TABLE IF NOT EXISTS bi_analytics.dim_issue_types (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_type_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issue_type_id, project_id)
);

CREATE INDEX idx_dim_issue_types_project ON bi_analytics.dim_issue_types(project_id);
CREATE INDEX idx_dim_issue_types_name ON bi_analytics.dim_issue_types(project_id, name);

COMMENT ON TABLE bi_analytics.dim_issue_types IS 'Denormalized issue type dimension for BI';

-- Issue status dimension
CREATE TABLE IF NOT EXISTS bi_analytics.dim_issue_statuses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_status_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issue_status_id, project_id)
);

CREATE INDEX idx_dim_statuses_project ON bi_analytics.dim_issue_statuses(project_id);
CREATE INDEX idx_dim_statuses_name ON bi_analytics.dim_issue_statuses(project_id, name);

COMMENT ON TABLE bi_analytics.dim_issue_statuses IS 'Denormalized issue status dimension';

-- Custom field values dimension for slicing
CREATE TABLE IF NOT EXISTS bi_analytics.dim_custom_field_stream_values (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_key_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    field_name text NOT NULL,
    value_text text,
    value_numeric numeric,
    value_hash text NOT NULL,
    is_grouped_as_other boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(field_key_id, project_id, value_hash)
);

CREATE INDEX idx_dim_custom_values_project_field ON bi_analytics.dim_custom_field_stream_values(project_id, field_key_id);
CREATE INDEX idx_dim_custom_values_hash ON bi_analytics.dim_custom_field_stream_values(value_hash);
CREATE INDEX idx_dim_custom_values_grouped ON bi_analytics.dim_custom_field_stream_values(is_grouped_as_other);

COMMENT ON TABLE bi_analytics.dim_custom_field_stream_values IS 'Custom field values dimension for stream slicing';
COMMENT ON COLUMN bi_analytics.dim_custom_field_stream_values.value_hash IS 'Hash for fast lookup';

-- Sprint dimension for BI
CREATE TABLE IF NOT EXISTS bi_analytics.dim_sprints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    name text NOT NULL,
    start_date date,
    end_date date,
    complete_date timestamptz,
    status_name text,
    goal text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(sprint_id, project_id)
);

CREATE INDEX idx_dim_sprints_project ON bi_analytics.dim_sprints(project_id);
CREATE INDEX idx_dim_sprints_dates ON bi_analytics.dim_sprints(project_id, start_date, end_date);

COMMENT ON TABLE bi_analytics.dim_sprints IS 'Denormalized sprint dimension';

-- ============================================================================
-- SECTION 4: FACT TABLES WITH UNIVERSAL SLICING
-- ============================================================================

-- Velocity per sprint with multi-dimensional slicing
CREATE TABLE IF NOT EXISTS bi_analytics.fact_velocity_sliced (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    sprint_id uuid NOT NULL,
    sprint_name text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,

    slice_dimension_type text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    slice_dimension_id uuid,
    slice_value_text text,

    planned_issues int NOT NULL DEFAULT 0,
    planned_story_points numeric DEFAULT 0,
    completed_issues int NOT NULL DEFAULT 0,
    completed_story_points numeric DEFAULT 0,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_fvs_project_sprint ON bi_analytics.fact_velocity_sliced(project_id, sprint_id);
CREATE INDEX idx_fvs_project_sprint_dim ON bi_analytics.fact_velocity_sliced(project_id, sprint_id, slice_dimension_type);
CREATE INDEX idx_fvs_slice_dim_id ON bi_analytics.fact_velocity_sliced(slice_dimension_id);
CREATE UNIQUE INDEX idx_fvs_unique
    ON bi_analytics.fact_velocity_sliced(project_id, sprint_id, slice_dimension_type, COALESCE(slice_dimension_id::text, 'null'));

COMMENT ON TABLE bi_analytics.fact_velocity_sliced IS 'Velocity with universal multi-dimensional slicing';
COMMENT ON COLUMN bi_analytics.fact_velocity_sliced.slice_dimension_type IS 'Dimension type (issue_type, issue_statuses, custom_field_stream, sprint)';
COMMENT ON COLUMN bi_analytics.fact_velocity_sliced.slice_dimension_id IS 'Polymorphic FK to corresponding dim table';
COMMENT ON COLUMN bi_analytics.fact_velocity_sliced.slice_value_text IS 'Denormalized value for performance';

-- Lead Time per issue with details
CREATE TABLE IF NOT EXISTS bi_analytics.fact_lead_time_sliced (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL,
    sprint_id uuid,

    lead_time_days numeric NOT NULL,
    commitment_start_at timestamptz,
    commitment_end_at timestamptz,
    start_commitment_point_id uuid,
    end_commitment_point_id uuid,

    lead_time_bin_number int,

    slice_dimension_type text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    slice_dimension_id uuid,
    slice_value_text text,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_flts_project_issue ON bi_analytics.fact_lead_time_sliced(project_id, issue_id);
CREATE INDEX idx_flts_project_sprint ON bi_analytics.fact_lead_time_sliced(project_id, sprint_id);
CREATE INDEX idx_flts_project_dim ON bi_analytics.fact_lead_time_sliced(project_id, slice_dimension_type);
CREATE INDEX idx_flts_bin ON bi_analytics.fact_lead_time_sliced(lead_time_bin_number);
CREATE UNIQUE INDEX idx_flts_unique
    ON bi_analytics.fact_lead_time_sliced(issue_id, slice_dimension_type, COALESCE(slice_dimension_id::text, 'null'));

COMMENT ON TABLE bi_analytics.fact_lead_time_sliced IS 'Lead Time per issue with polymorphic slicing';

-- Bins for Lead Time histograms
CREATE TABLE IF NOT EXISTS bi_analytics.fact_lead_time_bins_sliced (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    bin_number int NOT NULL,
    bin_min_days numeric NOT NULL,
    bin_max_days numeric NOT NULL,

    slice_dimension_type text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    slice_dimension_id uuid,
    slice_value_text text,

    tickets_count int NOT NULL DEFAULT 0,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_fltbs_project_bin ON bi_analytics.fact_lead_time_bins_sliced(project_id, bin_number);
CREATE INDEX idx_fltbs_project_dim ON bi_analytics.fact_lead_time_bins_sliced(project_id, slice_dimension_type);
CREATE UNIQUE INDEX idx_fltbs_unique
    ON bi_analytics.fact_lead_time_bins_sliced(project_id, bin_number, slice_dimension_type, COALESCE(slice_dimension_id::text, 'null'));

COMMENT ON TABLE bi_analytics.fact_lead_time_bins_sliced IS 'Bins for Lead Time histograms';

-- Cumulative Flow Diagram (CFD) with daily granularity
CREATE TABLE IF NOT EXISTS bi_analytics.fact_cfd_daily_sliced (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    date date NOT NULL,
    status_id uuid NOT NULL,
    status_name text NOT NULL,
    sprint_id uuid,

    slice_dimension_type text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    slice_dimension_id uuid,
    slice_value_text text,

    issue_count int NOT NULL DEFAULT 0,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_fcfds_project_date ON bi_analytics.fact_cfd_daily_sliced(project_id, date);
CREATE INDEX idx_fcfds_project_status ON bi_analytics.fact_cfd_daily_sliced(project_id, status_id, date);
CREATE INDEX idx_fcfds_project_sprint ON bi_analytics.fact_cfd_daily_sliced(project_id, sprint_id, date);
CREATE INDEX idx_fcfds_dim ON bi_analytics.fact_cfd_daily_sliced(slice_dimension_type, slice_dimension_id);
CREATE UNIQUE INDEX idx_fcfds_unique
    ON bi_analytics.fact_cfd_daily_sliced(project_id, date, status_id, slice_dimension_type, COALESCE(slice_dimension_id::text, 'null'));

COMMENT ON TABLE bi_analytics.fact_cfd_daily_sliced IS 'CFD with daily granularity and slicing';

-- Throughput (completed issues per day)
CREATE TABLE IF NOT EXISTS bi_analytics.fact_throughput_daily_sliced (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    date date NOT NULL,

    slice_dimension_type text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    slice_dimension_id uuid,
    slice_value_text text,

    completed_issues int NOT NULL DEFAULT 0,
    completed_story_points numeric DEFAULT 0,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_ftds_project_date ON bi_analytics.fact_throughput_daily_sliced(project_id, date);
CREATE INDEX idx_ftds_project_dim ON bi_analytics.fact_throughput_daily_sliced(project_id, slice_dimension_type);
CREATE UNIQUE INDEX idx_ftds_unique
    ON bi_analytics.fact_throughput_daily_sliced(project_id, date, slice_dimension_type, COALESCE(slice_dimension_id::text, 'null'));

COMMENT ON TABLE bi_analytics.fact_throughput_daily_sliced IS 'Throughput with daily granularity';

-- Time to Market (from creation to production)
CREATE TABLE IF NOT EXISTS bi_analytics.fact_time_to_market_sliced (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL,

    created_at timestamptz NOT NULL,
    first_commit_at timestamptz,
    first_pr_at timestamptz,
    merged_at timestamptz,
    deployed_to_staging_at timestamptz,
    deployed_to_production_at timestamptz,

    dev_time_days numeric,
    review_time_days numeric,
    deployment_time_days numeric,
    total_time_days numeric,

    slice_dimension_type text NOT NULL REFERENCES bi_analytics.enum_slice_dimension_types(dimension_type),
    slice_dimension_id uuid,
    slice_value_text text,

    created_at_record timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_fttms_project_issue ON bi_analytics.fact_time_to_market_sliced(project_id, issue_id);
CREATE INDEX idx_fttms_project_dim ON bi_analytics.fact_time_to_market_sliced(project_id, slice_dimension_type);
CREATE INDEX idx_fttms_production_date ON bi_analytics.fact_time_to_market_sliced(deployed_to_production_at);
CREATE UNIQUE INDEX idx_fttms_unique
    ON bi_analytics.fact_time_to_market_sliced(issue_id, slice_dimension_type, COALESCE(slice_dimension_id::text, 'null'));

COMMENT ON TABLE bi_analytics.fact_time_to_market_sliced IS 'Time to Market with development stages';

-- ============================================================================
-- FINAL COMMENTS
-- ============================================================================

COMMENT ON SCHEMA bi_analytics IS 'Analytics schema with enhanced structure: configuration separation, universal dimensions, polymorphic slicing, expandable ENUMs';
