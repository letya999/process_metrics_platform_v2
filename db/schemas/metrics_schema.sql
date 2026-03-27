--
-- PostgreSQL database dump
--


-- Dumped from database version 15.15
-- Dumped by pg_dump version 15.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: metrics; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA metrics;


--
-- Name: SCHEMA metrics; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA metrics IS 'Materialized views for team metrics (Lead Time, Velocity, Throughput)';


--
-- Name: refresh_all_views(); Type: FUNCTION; Schema: metrics; Owner: -
--

CREATE FUNCTION metrics.refresh_all_views() RETURNS void
    LANGUAGE plpgsql
    AS $$
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_throughput;

        -- Refresh sliced views (check existence just in case, though they are created above)
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity_slice;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time_slice;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time_bins_slice;
    END;
    $$;


--
-- Name: FUNCTION refresh_all_views(); Type: COMMENT; Schema: metrics; Owner: -
--

COMMENT ON FUNCTION metrics.refresh_all_views() IS 'Refresh all metrics materialized views including sliced views';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: calculation_settings; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.calculation_settings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid,
    target_calculation_id uuid NOT NULL,
    settings_type text NOT NULL,
    settings_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: calculations; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.calculations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    definition_id uuid NOT NULL,
    calc_code text NOT NULL,
    grain_id uuid NOT NULL,
    unit_code text NOT NULL,
    uses_commitment_points boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: commitment_rules; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.commitment_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid,
    board_id uuid,
    target_calculation_id uuid NOT NULL,
    target_calculation_name text NOT NULL,
    start_column_id uuid NOT NULL,
    end_column_id uuid NOT NULL,
    start_column_name_snapshot text NOT NULL,
    end_column_name_snapshot text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: definitions; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.definitions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    metric_code text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: dim_dates; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.dim_dates (
    time_id integer NOT NULL,
    full_date date NOT NULL,
    week_num integer NOT NULL,
    month_num integer NOT NULL,
    quarter integer NOT NULL,
    year integer NOT NULL
);


--
-- Name: dim_dates_time_id_seq; Type: SEQUENCE; Schema: metrics; Owner: -
--

CREATE SEQUENCE metrics.dim_dates_time_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dim_dates_time_id_seq; Type: SEQUENCE OWNED BY; Schema: metrics; Owner: -
--

ALTER SEQUENCE metrics.dim_dates_time_id_seq OWNED BY metrics.dim_dates.time_id;


--
-- Name: dim_projects; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.dim_projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    project_key text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: fact_values; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.fact_values (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    metric_id uuid NOT NULL,
    project_agg_id uuid NOT NULL,
    time_id integer NOT NULL,
    value double precision NOT NULL,
    entity_type text,
    entity_id text,
    event_start_at timestamp with time zone,
    event_end_at timestamp with time zone,
    slice_rule_id uuid,
    slice_value text,
    commitment_rule_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    settings_id uuid,
    context_json jsonb
);


--
-- Name: grains; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.grains (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    grain_code text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: slice_rules; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.slice_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid,
    rule_name text NOT NULL,
    target_definition_id uuid,
    target_definition_name text,
    source_table text NOT NULL,
    group_by_source_column text NOT NULL,
    enabled boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: units; Type: TABLE; Schema: metrics; Owner: -
--

CREATE TABLE metrics.units (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid,
    unit_code text NOT NULL,
    display_symbol text NOT NULL,
    source_field_id uuid,
    source_entity text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: v_facts; Type: VIEW; Schema: metrics; Owner: -
--

CREATE VIEW metrics.v_facts AS
 SELECT fv.id,
    fv.metric_id,
    fv.project_agg_id,
    fv.time_id,
    fv.value,
    fv.entity_type,
    fv.entity_id,
    fv.event_start_at,
    fv.event_end_at,
    fv.slice_rule_id,
    fv.slice_value,
    fv.commitment_rule_id,
    fv.settings_id,
    fv.context_json,
    fv.created_at,
    fv.updated_at,
    c.calc_code,
    c.unit_code,
    c.uses_commitment_points,
    d.metric_code,
    g.grain_code,
    dp.project_key,
    dt.full_date,
    dt.week_num,
    dt.month_num,
    dt.quarter,
    dt.year,
    sr.rule_name AS slice_rule_name,
    cs.settings_type AS calc_settings_type,
    cs.settings_json AS calc_settings_json
   FROM (((((((metrics.fact_values fv
     JOIN metrics.calculations c ON ((fv.metric_id = c.id)))
     JOIN metrics.definitions d ON ((c.definition_id = d.id)))
     JOIN metrics.grains g ON ((c.grain_id = g.id)))
     JOIN metrics.dim_projects dp ON ((fv.project_agg_id = dp.id)))
     JOIN metrics.dim_dates dt ON ((fv.time_id = dt.time_id)))
     LEFT JOIN metrics.slice_rules sr ON ((fv.slice_rule_id = sr.id)))
     LEFT JOIN metrics.calculation_settings cs ON ((fv.settings_id = cs.id)));


--
-- Name: dim_dates time_id; Type: DEFAULT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.dim_dates ALTER COLUMN time_id SET DEFAULT nextval('metrics.dim_dates_time_id_seq'::regclass);


--
-- Name: calculation_settings calculation_settings_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculation_settings
    ADD CONSTRAINT calculation_settings_pkey PRIMARY KEY (id);


--
-- Name: calculations calculations_calc_code_key; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculations
    ADD CONSTRAINT calculations_calc_code_key UNIQUE (calc_code);


--
-- Name: calculations calculations_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculations
    ADD CONSTRAINT calculations_pkey PRIMARY KEY (id);


--
-- Name: commitment_rules commitment_rules_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT commitment_rules_pkey PRIMARY KEY (id);


--
-- Name: definitions definitions_metric_code_key; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.definitions
    ADD CONSTRAINT definitions_metric_code_key UNIQUE (metric_code);


--
-- Name: definitions definitions_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.definitions
    ADD CONSTRAINT definitions_pkey PRIMARY KEY (id);


--
-- Name: dim_dates dim_dates_full_date_key; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.dim_dates
    ADD CONSTRAINT dim_dates_full_date_key UNIQUE (full_date);


--
-- Name: dim_dates dim_dates_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.dim_dates
    ADD CONSTRAINT dim_dates_pkey PRIMARY KEY (time_id);


--
-- Name: dim_projects dim_projects_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.dim_projects
    ADD CONSTRAINT dim_projects_pkey PRIMARY KEY (id);


--
-- Name: dim_projects dim_projects_project_id_key; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.dim_projects
    ADD CONSTRAINT dim_projects_project_id_key UNIQUE (project_id);


--
-- Name: fact_values fact_values_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fact_values_pkey PRIMARY KEY (id);


--
-- Name: grains grains_grain_code_key; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.grains
    ADD CONSTRAINT grains_grain_code_key UNIQUE (grain_code);


--
-- Name: grains grains_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.grains
    ADD CONSTRAINT grains_pkey PRIMARY KEY (id);


--
-- Name: slice_rules slice_rules_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.slice_rules
    ADD CONSTRAINT slice_rules_pkey PRIMARY KEY (id);


--
-- Name: units units_pkey; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.units
    ADD CONSTRAINT units_pkey PRIMARY KEY (id);


--
-- Name: commitment_rules uq_commitment_rules_project_board_calc; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT uq_commitment_rules_project_board_calc UNIQUE (project_id, board_id, target_calculation_id);


--
-- Name: slice_rules uq_slice_rules_project_name; Type: CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.slice_rules
    ADD CONSTRAINT uq_slice_rules_project_name UNIQUE (project_id, rule_name);


--
-- Name: idx_calc_settings_calc; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_calc_settings_calc ON metrics.calculation_settings USING btree (target_calculation_id);


--
-- Name: idx_calc_settings_project; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_calc_settings_project ON metrics.calculation_settings USING btree (project_id);


--
-- Name: idx_calc_settings_project_type_unique; Type: INDEX; Schema: metrics; Owner: -
--

CREATE UNIQUE INDEX idx_calc_settings_project_type_unique ON metrics.calculation_settings USING btree (project_id, target_calculation_id, settings_type) WHERE (project_id IS NOT NULL);


--
-- Name: idx_calc_settings_type_unique; Type: INDEX; Schema: metrics; Owner: -
--

CREATE UNIQUE INDEX idx_calc_settings_type_unique ON metrics.calculation_settings USING btree (target_calculation_id, settings_type) WHERE (project_id IS NULL);


--
-- Name: idx_commitment_rules_global_unique; Type: INDEX; Schema: metrics; Owner: -
--

CREATE UNIQUE INDEX idx_commitment_rules_global_unique ON metrics.commitment_rules USING btree (board_id, target_calculation_id) WHERE (project_id IS NULL);


--
-- Name: idx_fact_values_base; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_fact_values_base ON metrics.fact_values USING btree (metric_id, project_agg_id, time_id) WHERE (slice_rule_id IS NULL);


--
-- Name: idx_fact_values_context_gin; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_fact_values_context_gin ON metrics.fact_values USING gin (context_json) WHERE (context_json IS NOT NULL);


--
-- Name: idx_fact_values_entity; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_fact_values_entity ON metrics.fact_values USING btree (entity_type, entity_id) WHERE (entity_id IS NOT NULL);


--
-- Name: idx_fact_values_main; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_fact_values_main ON metrics.fact_values USING btree (metric_id, project_agg_id, time_id) INCLUDE (value, slice_value, entity_id, entity_type);


--
-- Name: idx_fact_values_project_time; Type: INDEX; Schema: metrics; Owner: -
--

CREATE INDEX idx_fact_values_project_time ON metrics.fact_values USING btree (project_agg_id, time_id) INCLUDE (value, metric_id);


--
-- Name: idx_slice_rules_global_unique; Type: INDEX; Schema: metrics; Owner: -
--

CREATE UNIQUE INDEX idx_slice_rules_global_unique ON metrics.slice_rules USING btree (rule_name) WHERE (project_id IS NULL);


--
-- Name: idx_unique_unit_code_global; Type: INDEX; Schema: metrics; Owner: -
--

CREATE UNIQUE INDEX idx_unique_unit_code_global ON metrics.units USING btree (unit_code) WHERE (project_id IS NULL);


--
-- Name: idx_unique_unit_code_project; Type: INDEX; Schema: metrics; Owner: -
--

CREATE UNIQUE INDEX idx_unique_unit_code_project ON metrics.units USING btree (project_id, unit_code) WHERE (project_id IS NOT NULL);


--
-- Name: calculation_settings calculation_settings_project_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculation_settings
    ADD CONSTRAINT calculation_settings_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: calculation_settings calculation_settings_target_calculation_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculation_settings
    ADD CONSTRAINT calculation_settings_target_calculation_id_fkey FOREIGN KEY (target_calculation_id) REFERENCES metrics.calculations(id) ON DELETE CASCADE;


--
-- Name: calculations calculations_definition_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculations
    ADD CONSTRAINT calculations_definition_id_fkey FOREIGN KEY (definition_id) REFERENCES metrics.definitions(id) ON DELETE CASCADE;


--
-- Name: calculations calculations_grain_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.calculations
    ADD CONSTRAINT calculations_grain_id_fkey FOREIGN KEY (grain_id) REFERENCES metrics.grains(id);


--
-- Name: commitment_rules commitment_rules_board_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT commitment_rules_board_id_fkey FOREIGN KEY (board_id) REFERENCES clean_jira.boards(id) ON DELETE CASCADE;


--
-- Name: commitment_rules commitment_rules_end_column_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT commitment_rules_end_column_id_fkey FOREIGN KEY (end_column_id) REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE;


--
-- Name: commitment_rules commitment_rules_project_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT commitment_rules_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: commitment_rules commitment_rules_start_column_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT commitment_rules_start_column_id_fkey FOREIGN KEY (start_column_id) REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE;


--
-- Name: commitment_rules commitment_rules_target_calculation_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.commitment_rules
    ADD CONSTRAINT commitment_rules_target_calculation_id_fkey FOREIGN KEY (target_calculation_id) REFERENCES metrics.calculations(id) ON DELETE CASCADE;


--
-- Name: dim_projects dim_projects_project_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.dim_projects
    ADD CONSTRAINT dim_projects_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: fact_values fact_values_commitment_rule_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fact_values_commitment_rule_id_fkey FOREIGN KEY (commitment_rule_id) REFERENCES metrics.commitment_rules(id) ON DELETE SET NULL;


--
-- Name: fact_values fact_values_metric_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fact_values_metric_id_fkey FOREIGN KEY (metric_id) REFERENCES metrics.calculations(id) ON DELETE CASCADE;


--
-- Name: fact_values fact_values_project_agg_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fact_values_project_agg_id_fkey FOREIGN KEY (project_agg_id) REFERENCES metrics.dim_projects(id) ON DELETE CASCADE;


--
-- Name: fact_values fact_values_slice_rule_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fact_values_slice_rule_id_fkey FOREIGN KEY (slice_rule_id) REFERENCES metrics.slice_rules(id) ON DELETE SET NULL;


--
-- Name: fact_values fact_values_time_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fact_values_time_id_fkey FOREIGN KEY (time_id) REFERENCES metrics.dim_dates(time_id) ON DELETE CASCADE;


--
-- Name: fact_values fk_fact_values_settings; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.fact_values
    ADD CONSTRAINT fk_fact_values_settings FOREIGN KEY (settings_id) REFERENCES metrics.calculation_settings(id) ON DELETE SET NULL;


--
-- Name: slice_rules slice_rules_project_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.slice_rules
    ADD CONSTRAINT slice_rules_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: slice_rules slice_rules_target_definition_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.slice_rules
    ADD CONSTRAINT slice_rules_target_definition_id_fkey FOREIGN KEY (target_definition_id) REFERENCES metrics.definitions(id) ON DELETE SET NULL;


--
-- Name: units units_project_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.units
    ADD CONSTRAINT units_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: units units_source_field_id_fkey; Type: FK CONSTRAINT; Schema: metrics; Owner: -
--

ALTER TABLE ONLY metrics.units
    ADD CONSTRAINT units_source_field_id_fkey FOREIGN KEY (source_field_id) REFERENCES clean_jira.field_keys(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--


-- Auto-generated baseline comments for missing objects
COMMENT ON TABLE metrics.calculation_settings IS 'Per-calculation settings with optional project overrides.';
COMMENT ON COLUMN metrics.calculation_settings.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.calculation_settings.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN metrics.calculation_settings.target_calculation_id IS 'Reference identifier for target calculation.';
COMMENT ON COLUMN metrics.calculation_settings.settings_type IS 'Settings type.';
COMMENT ON COLUMN metrics.calculation_settings.settings_json IS 'JSON payload for settings.';
COMMENT ON COLUMN metrics.calculation_settings.enabled IS 'Enabled.';
COMMENT ON COLUMN metrics.calculation_settings.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.calculation_settings.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN metrics.calculations.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.calculations.definition_id IS 'Reference identifier for definition.';
COMMENT ON COLUMN metrics.calculations.uses_commitment_points IS 'Uses commitment points.';
COMMENT ON COLUMN metrics.calculations.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.calculations.updated_at IS 'Row last update timestamp.';
COMMENT ON TABLE metrics.commitment_rules IS 'Rules mapping board columns to commitment boundaries.';
COMMENT ON COLUMN metrics.commitment_rules.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.commitment_rules.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN metrics.commitment_rules.board_id IS 'Reference identifier for board.';
COMMENT ON COLUMN metrics.commitment_rules.target_calculation_id IS 'Reference identifier for target calculation.';
COMMENT ON COLUMN metrics.commitment_rules.target_calculation_name IS 'Target calculation name.';
COMMENT ON COLUMN metrics.commitment_rules.start_column_id IS 'Reference identifier for start column.';
COMMENT ON COLUMN metrics.commitment_rules.end_column_id IS 'Reference identifier for end column.';
COMMENT ON COLUMN metrics.commitment_rules.start_column_name_snapshot IS 'Start column name snapshot.';
COMMENT ON COLUMN metrics.commitment_rules.end_column_name_snapshot IS 'End column name snapshot.';
COMMENT ON COLUMN metrics.commitment_rules.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.commitment_rules.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN metrics.definitions.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.definitions.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.definitions.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN metrics.dim_dates.week_num IS 'Week num.';
COMMENT ON COLUMN metrics.dim_dates.month_num IS 'Month num.';
COMMENT ON COLUMN metrics.dim_dates.quarter IS 'Quarter.';
COMMENT ON COLUMN metrics.dim_dates.year IS 'Year.';
COMMENT ON COLUMN metrics.dim_projects.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.dim_projects.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN metrics.dim_projects.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.dim_projects.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN metrics.fact_values.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.fact_values.event_start_at IS 'Timestamp/date value for event start at.';
COMMENT ON COLUMN metrics.fact_values.event_end_at IS 'Timestamp/date value for event end at.';
COMMENT ON COLUMN metrics.fact_values.commitment_rule_id IS 'Reference identifier for commitment rule.';
COMMENT ON COLUMN metrics.fact_values.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.fact_values.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN metrics.fact_values.settings_id IS 'Reference identifier for settings.';
COMMENT ON TABLE metrics.grains IS 'Supported aggregation grains for metric calculations.';
COMMENT ON COLUMN metrics.grains.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.grains.grain_code IS 'Grain code.';
COMMENT ON COLUMN metrics.grains.description IS 'Description value from source or normalized entity.';
COMMENT ON COLUMN metrics.grains.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.slice_rules.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.slice_rules.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN metrics.slice_rules.rule_name IS 'Rule name.';
COMMENT ON COLUMN metrics.slice_rules.target_definition_id IS 'Reference identifier for target definition.';
COMMENT ON COLUMN metrics.slice_rules.target_definition_name IS 'Target definition name.';
COMMENT ON COLUMN metrics.slice_rules.source_table IS 'Source table.';
COMMENT ON COLUMN metrics.slice_rules.group_by_source_column IS 'Group by source column.';
COMMENT ON COLUMN metrics.slice_rules.enabled IS 'Enabled.';
COMMENT ON COLUMN metrics.slice_rules.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.slice_rules.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN metrics.units.id IS 'Primary key UUID.';
COMMENT ON COLUMN metrics.units.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN metrics.units.unit_code IS 'Unit code.';
COMMENT ON COLUMN metrics.units.display_symbol IS 'Display symbol.';
COMMENT ON COLUMN metrics.units.source_field_id IS 'Reference identifier for source field.';
COMMENT ON COLUMN metrics.units.source_entity IS 'Source entity.';
COMMENT ON COLUMN metrics.units.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN metrics.units.updated_at IS 'Row last update timestamp.';

-- Curated semantic comments (priority objects)





COMMENT ON TABLE metrics.slice_rules IS 'Segmentation rules for producing sliced metric series.';
COMMENT ON TABLE metrics.units IS 'Unit catalog and source-field binding configuration.';

-- Curated semantic comments v2 (top tables)
COMMENT ON TABLE metrics.definitions IS 'Business metric families registry.';
COMMENT ON COLUMN metrics.definitions.metric_code IS 'Stable business metric code.';

COMMENT ON TABLE metrics.calculations IS 'Metric calculation variants with grain and unit settings.';
COMMENT ON COLUMN metrics.calculations.calc_code IS 'Stable technical calculation code.';
COMMENT ON COLUMN metrics.calculations.grain_id IS 'Reference to metrics.grains.';
COMMENT ON COLUMN metrics.calculations.unit_code IS 'Unit code of produced values.';

COMMENT ON TABLE metrics.dim_projects IS 'Project dimension used by metric fact rows.';
COMMENT ON COLUMN metrics.dim_projects.project_key IS 'Project key.';

COMMENT ON TABLE metrics.dim_dates IS 'Date dimension keyed by integer time_id.';
COMMENT ON COLUMN metrics.dim_dates.time_id IS 'Reference identifier for time.';
COMMENT ON COLUMN metrics.dim_dates.full_date IS 'Timestamp/date value for full date.';

COMMENT ON TABLE metrics.fact_values IS 'Generic long-format fact table storing metric values.';
COMMENT ON COLUMN metrics.fact_values.metric_id IS 'Reference to the calculation variant that produced the value.';
COMMENT ON COLUMN metrics.fact_values.project_agg_id IS 'Reference to project dimension row.';
COMMENT ON COLUMN metrics.fact_values.time_id IS 'Reference to date dimension key (YYYYMMDD).';
COMMENT ON COLUMN metrics.fact_values.value IS 'Measured numeric value.';
COMMENT ON COLUMN metrics.fact_values.entity_type IS 'Entity grain type (issue, sprint, day, week, release).';
COMMENT ON COLUMN metrics.fact_values.entity_id IS 'Entity identifier within the selected grain.';
COMMENT ON COLUMN metrics.fact_values.slice_rule_id IS 'Applied slice rule when metric is segmented.';
COMMENT ON COLUMN metrics.fact_values.slice_value IS 'Segment value produced by slice rule.';
COMMENT ON COLUMN metrics.fact_values.context_json IS 'Optional JSON context for diagnostics and BI drill-down.';

COMMENT ON VIEW metrics.v_facts IS 'Denormalized analytics view joining metric facts and dimensions.';

-- Curated semantic comments v4 (manual high-detail)
COMMENT ON TABLE metrics.fact_values IS 'Central long-format metric store: each row is one metric observation for one project/date/entity/slice combination.';
COMMENT ON COLUMN metrics.fact_values.id IS 'Technical UUID primary key of the fact row.';
COMMENT ON COLUMN metrics.fact_values.metric_id IS 'FK to metrics.calculations: identifies calculation variant (calc_code) that produced the value.';
COMMENT ON COLUMN metrics.fact_values.project_agg_id IS 'FK to metrics.dim_projects: project context for aggregation and filtering.';
COMMENT ON COLUMN metrics.fact_values.time_id IS 'FK to metrics.dim_dates (YYYYMMDD integer key) used for time-series queries.';
COMMENT ON COLUMN metrics.fact_values.value IS 'Numeric metric value produced by calculation logic.';
COMMENT ON COLUMN metrics.fact_values.entity_type IS 'Grain label for entity_id (issue, sprint, day, week, release).';
COMMENT ON COLUMN metrics.fact_values.entity_id IS 'Entity identifier at selected grain (for example issue key, sprint ID, or date token).';
COMMENT ON COLUMN metrics.fact_values.event_start_at IS 'Optional process/event start timestamp used by duration metrics.';
COMMENT ON COLUMN metrics.fact_values.event_end_at IS 'Optional process/event end timestamp used by duration metrics.';
COMMENT ON COLUMN metrics.fact_values.slice_rule_id IS 'FK to metrics.slice_rules when this row is part of a segmented series; NULL for unsliced values.';
COMMENT ON COLUMN metrics.fact_values.slice_value IS 'Segment member value (for example issue type, priority, team) produced by slice rule.';
COMMENT ON COLUMN metrics.fact_values.commitment_rule_id IS 'FK to metrics.commitment_rules for flow metrics that depend on board column boundaries.';
COMMENT ON COLUMN metrics.fact_values.settings_id IS 'FK to metrics.calculation_settings snapshot used during calculation run.';
COMMENT ON COLUMN metrics.fact_values.context_json IS 'Optional JSON payload with extra diagnostic context not modeled as dedicated columns.';
COMMENT ON COLUMN metrics.fact_values.created_at IS 'Insert timestamp of fact row in warehouse.';
COMMENT ON COLUMN metrics.fact_values.updated_at IS 'Last update timestamp of fact row in warehouse.';
