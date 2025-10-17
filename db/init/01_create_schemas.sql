-- Initialize required schemas for Process Metrics Platform v2
BEGIN;

-- Schemas
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS admin;
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS monitoring;
CREATE SCHEMA IF NOT EXISTS orchestrator;

CREATE SCHEMA IF NOT EXISTS raw_jira_cloud_dlt;
CREATE SCHEMA IF NOT EXISTS raw_jira_cloud_rest;
CREATE SCHEMA IF NOT EXISTS raw_jira_server_rest;
CREATE SCHEMA IF NOT EXISTS raw_gitlab_cloud_api;
CREATE SCHEMA IF NOT EXISTS raw_gitlab_selfhosted_db;

CREATE SCHEMA IF NOT EXISTS clean_jira;
CREATE SCHEMA IF NOT EXISTS clean_gitlab;

CREATE SCHEMA IF NOT EXISTS bi_metrics;
CREATE SCHEMA IF NOT EXISTS bi_dashboards;
CREATE SCHEMA IF NOT EXISTS metabase;

-- Create service roles (no passwords here; set secure passwords externally)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'auth_user') THEN
        CREATE ROLE auth_user LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'etl_user') THEN
        CREATE ROLE etl_user LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'orchestrator_user') THEN
        CREATE ROLE orchestrator_user LOGIN;
    END IF;
END
$$;

-- Grants: least privilege per schema ownership
GRANT USAGE ON SCHEMA auth TO auth_user;
GRANT CREATE ON SCHEMA auth TO auth_user;

GRANT USAGE ON SCHEMA etl TO etl_user;
GRANT CREATE ON SCHEMA etl TO etl_user;

-- ETL needs read on raw_* and write on clean_* and bi_*
GRANT USAGE ON SCHEMA raw_jira_cloud_dlt TO etl_user;
GRANT USAGE ON SCHEMA raw_jira_cloud_rest TO etl_user;
GRANT USAGE ON SCHEMA raw_jira_server_rest TO etl_user;
GRANT USAGE ON SCHEMA raw_gitlab_cloud_api TO etl_user;
GRANT USAGE ON SCHEMA raw_gitlab_selfhosted_db TO etl_user;

GRANT USAGE ON SCHEMA clean_jira TO etl_user;
GRANT CREATE ON SCHEMA clean_jira TO etl_user;
GRANT USAGE ON SCHEMA clean_gitlab TO etl_user;
GRANT CREATE ON SCHEMA clean_gitlab TO etl_user;

GRANT USAGE ON SCHEMA bi_metrics TO etl_user;
GRANT CREATE ON SCHEMA bi_metrics TO etl_user;
GRANT USAGE ON SCHEMA bi_dashboards TO etl_user;
GRANT CREATE ON SCHEMA bi_dashboards TO etl_user;

-- Orchestrator minimal access to auth schema for service discovery
GRANT USAGE ON SCHEMA auth TO orchestrator_user;

COMMIT;
