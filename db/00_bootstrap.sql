-- Bootstrap init runner for Postgres entrypoint
-- This file is executed automatically on first DB init
\set ON_ERROR_STOP on

\echo '=== Running DB init scripts ==='
\ir init/01_create_schemas.sql
\echo '=== DB init scripts completed ==='
