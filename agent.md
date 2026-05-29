# Agent Guide

This file is the single source of truth for all AI assistants in this repository.

## Project Overview
- Name: Process Metrics Platform v2
- Type: Self-hosted ETL + BI platform for engineering process metrics
- Main users: project managers, delivery managers, agile coaches, team leads
- Core principle: simple monolith over microservices

## Architecture Approach
- Monolithic application stack with clear responsibilities by module
- Service topology (production):
  - `app` (FastAPI admin/API)
  - `dagster-webserver` + `dagster-daemon` (orchestration, schedules, asset runs)
  - `postgres` (single database, multiple schemas)
  - `metabase` (dashboards, provisioned via `bi/` pack)
  - `caddy` (reverse proxy + HTTPS)
- Compose files: `docker-compose.yml` (local dev), `docker-compose.prod.yml` (production)

## Data Architecture
The platform follows Medallion-style layering.

### Layer 1: Raw (Bronze)
- Purpose: ingest source data as close to original as possible
- Writer: dlt-based ingestion
- Characteristics: append-oriented, source-oriented, minimal transformation
- Typical schemas: `raw_jira`, `raw_gitlab`

### Layer 2: Clean (Silver)
- Purpose: normalize and type data for consistent downstream logic
- Writer: Dagster assets and transformation logic
- Characteristics: cleaned fields, canonical naming, relational integrity
- Typical schemas: `clean_jira`, `clean_gitlab`

### Layer 3: Metrics (Gold)
- Purpose: business-ready facts for reporting and analytics
- Writer: metrics calculations + SQL/materialized constructs
- Characteristics: metric-centric tables and slices, dashboard-ready shape
- Typical schema: `metrics`

### Platform Layer
- Purpose: operational metadata and platform configuration
- Writer: FastAPI + migrations
- Typical schema: `platform`

## ETL / ELT Flow
1. Extract from source systems via dlt.
2. Load into raw schemas.
3. Transform raw -> clean using Dagster assets/calculations.
4. Compute metrics/slices in metrics schema.
5. Visualize in Metabase.

Short flow: `Sources -> dlt -> raw -> Dagster transforms -> clean -> metrics -> Metabase`.

## Data Sources
- Active/primary:
  - Jira (issues, statuses, changelog-based signals)
- Supported/target in platform direction:
  - GitLab
  - Slack
  - Other connectors via dlt extension pattern

## Core Runtime Components
- FastAPI: admin endpoints, platform operations, integration control
- Dagster: orchestration, scheduling, observability of data assets
- PostgreSQL 15: persistent storage for all layers
- Metabase: BI dashboards; cards/dashboards are code-defined in `bi/packs/` and provisioned via `metabase-init` container
- Caddy: HTTPS termination and reverse proxy in production

## Repository Map
- `app/` FastAPI app, API routes, models, services
- `pipelines/` Dagster definitions, assets, calculations, resources
- `bi/` Metabase BI pack: card/dashboard JSON definitions, provisioner (`bi/providers/metabase/`)
- `streamlit_admin/` admin UI for operational tasks
- `db/` SQL bootstrap, schemas, migrations, views
- `spec/` OpenSpec capabilities and active changes
- `tests/` unit, integration, validation tests
- `scripts/` operational and setup scripts

## Engineering Rules
- Keep solutions pragmatic; prefer simple implementation paths.
- Preserve monolith architecture unless explicitly re-scoped.
- Reuse existing conventions before introducing new patterns.
- Avoid hidden behavior and implicit magic.
- Never commit credentials or secrets.

## Quality and Verification
- Primary project check command: `make check`
- Common commands:
  - `make dev` - start local stack
  - `make lint` - style/lint checks
  - `make test` - test suite with coverage
  - `make migrate` - apply migrations
  - `make docker-up` / `make docker-down` - lifecycle

## Operational Notes for Agents
- Prefer reading existing implementations before changing behavior.
- For schema or metric logic changes, inspect both `pipelines/` and `db/migrations/`.
- When changing ETL logic, verify impact across all layers (raw/clean/metrics).
- Keep changes scoped and explicit; document assumptions in PR/task notes.

## Agent Entrypoints
- `codex.md`
- `gemini.md`
- `claude.md`
- `CLAUDE.md`

If any assistant-specific file conflicts with this document, `agent.md` wins.
