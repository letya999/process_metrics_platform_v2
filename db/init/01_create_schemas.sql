-- Ensure pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

BEGIN;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS platform;
CREATE SCHEMA IF NOT EXISTS raw_jira;
CREATE SCHEMA IF NOT EXISTS clean_jira;
CREATE SCHEMA IF NOT EXISTS metrics;
CREATE SCHEMA IF NOT EXISTS bi_analytics;
CREATE SCHEMA IF NOT EXISTS metabase;

-- Create service roles
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

-- Grant permissions
GRANT USAGE ON SCHEMA platform TO auth_user;
GRANT CREATE ON SCHEMA platform TO auth_user;

GRANT USAGE ON SCHEMA raw_jira TO etl_user;
GRANT USAGE ON SCHEMA clean_jira TO etl_user;
GRANT CREATE ON SCHEMA clean_jira TO etl_user;
GRANT USAGE ON SCHEMA bi_analytics TO etl_user;
GRANT CREATE ON SCHEMA bi_analytics TO etl_user;

GRANT USAGE ON SCHEMA platform TO orchestrator_user;

COMMIT;

-- Load schema definitions with absolute paths
\echo 'Loading platform schema...'
\ir /db/schemas/platform_schema.sql

\echo 'Loading clean_jira schema...'
\ir /db/schemas/clean_jira_schema.sql

\echo 'Loading bi_analytics schema...'
\ir /db/schemas/bi_analytics_schema.sql

\echo 'Loading metrics views...'
\ir /db/views/metrics.sql

\echo 'Database initialization complete.'
