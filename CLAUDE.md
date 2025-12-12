# CLAUDE.md - Process Metrics Platform v2

## Project Overview

**Process Metrics Platform** is an open-source, self-hosted ETL + BI platform for calculating and visualizing software development team metrics (Lead Time, Velocity, Throughput, DORA metrics).

**Target users:** Project managers, delivery managers, agile coaches, team leads.

## Quick Start (MVP)

### 1. Start all services
```bash
docker compose up -d
```

### 2. Initialize database from scratch
```bash
# Option A: Let Docker Compose initialize via init script + migrations (recommended)
docker compose exec app alembic upgrade head

# Option B: Clean reset if DB is corrupted
docker compose down -v
docker compose up -d
docker compose exec app alembic upgrade head
```

### 3. Open services
- **Admin Panel:** http://localhost:8000
- **Dagster UI:** http://localhost:3000
- **Metabase:** http://localhost:3001

### 4. Verify everything works
```bash
# Check database migrations
docker compose exec app alembic current

# View Dagster assets
# Go to Dagster UI → Assets → should see jira_raw_data, clean_jira_issues, etc.

# Test a manual sync
docker compose exec app dagster job execute -j jira_sync_job
```

## MVP Optimizations (v2)

This version is optimized for MVP - single-user, Jira-only ETL platform:

### Removed for MVP (can be added later)
- ❌ `external_tool_users` — Multi-tool BI sync (Metabase, Grafana)
- ❌ `project_access` — Multi-user role-based access control
- ❌ `pipelines`, `pipeline_runs`, `pipeline_tasks` — Prefect orchestration (using Dagster instead)

### Simplified for MVP
- ✅ `platform.projects.owner_user_id` → Optional (NULL for system projects)
- ✅ `platform.projects.tool_integration_id` → Optional (NULL for system projects)
- ✅ Removed UNIQUE constraints dependent on removed fields
- ✅ Default "Jira System Project" auto-created for clean_jira data grouping

### Result
- **565 lines of code removed** (database + API + ORM)
- **Faster to market** for MVP phase
- **Extensible design** — easy to add multi-user/multi-tool later

### Schema Diagram (MVP)
```
platform.users (auth)
    ↓
platform.tool_integrations (Jira credentials)
    ↓
platform.projects (optional link)
    ↓
clean_jira.projects ← grouped by UUID
    ↓
clean_jira.issues/sprints/etc.
    ↓
metrics.* (materialized views)
```

## Architecture

### Monolith approach (not microservices)

```
┌─────────────────────────────────────────────────┐
│              Docker Compose                      │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │  Dagster   │  │  FastAPI   │  │ Metabase │  │
│  │  :3000     │  │  :8000     │  │  :3001   │  │
│  └────────────┘  └────────────┘  └──────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │              PostgreSQL                     │ │
│  │  raw_* → clean_* → metrics (views)         │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Data layers (Medallion architecture)

| Layer | Schema | Purpose |
|-------|--------|---------|
| **Raw (Bronze)** | `raw_jira`, `raw_gitlab` | Append-only, dlt loads data as-is |
| **Clean (Silver)** | `clean_jira`, `clean_gitlab` | Normalized, untangled structure |
| **Metrics (Gold)** | `metrics` | Materialized views for BI |
| **Platform** | `platform` | Users, integrations, configs |

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Orchestration** | Dagster | Pipeline scheduling, UI, asset lineage |
| **Data Ingestion** | dlt | Extract from Jira, GitLab, Slack |
| **API** | FastAPI | Admin panel backend |
| **Database** | PostgreSQL 15 | All data storage |
| **BI** | Metabase | Dashboards and visualizations |
| **Language** | Python 3.11 | Runtime |

## Project Structure

```
process_metrics/
├── app/                          # FastAPI admin API
│   ├── main.py                   # App entrypoint
│   ├── api/                      # API routes
│   │   ├── integrations.py       # CRUD for data sources
│   │   ├── projects.py           # Project selection
│   │   └── metric_config.py      # Metric configuration
│   ├── models/
│   │   └── orm.py                # SQLAlchemy models (platform schema)
│   └── services/
│       └── dagster_client.py     # Trigger Dagster jobs
│
├── pipelines/                    # Dagster pipelines
│   ├── definitions.py            # Dagster Definitions entry
│   ├── assets/
│   │   ├── jira/
│   │   │   ├── raw.py            # dlt → raw_jira
│   │   │   └── clean.py          # raw → clean_jira
│   │   ├── gitlab/
│   │   │   ├── raw.py
│   │   │   └── clean.py
│   │   └── metrics/
│   │       └── views.py          # Refresh materialized views
│   ├── resources/
│   │   └── database.py           # DB resource
│   └── jobs/
│       └── schedules.py          # Cron schedules
│
├── db/
│   ├── migrations/               # Alembic migrations
│   ├── schemas/
│   │   ├── platform.sql          # Users, integrations, configs
│   │   └── clean_jira.sql        # Clean Jira schema
│   └── views/
│       └── metrics.sql           # Materialized views
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── Makefile
├── ROADMAP.md                    # MVP plan and tasks
└── CLAUDE.md                     # This file
```

## Common Commands

### Development Workflow (use make!)

```bash
# BEFORE COMMIT - run all checks at once
make check                  # Runs: lint + test + validate

# Individual commands
make dev                    # Start dev environment (docker-compose up -d)
make test                   # Run pytest with coverage
make lint                   # Run ruff + black check
make format                 # Auto-format code (ruff --fix + black)
make validate               # Validate data integrity (raw → clean → metrics)
```

### Database

```bash
make migrate                # Run Alembic migrations
make migrate-create MSG="description"  # Create new migration
make migrate-down           # Rollback one migration
```

### Dagster

```bash
dagster dev                 # Start Dagster dev server
dagster job execute -j jira_sync_job  # Run job manually
```

### Docker

```bash
docker-compose up -d        # Start all services
docker-compose logs -f app  # View logs
docker-compose down         # Stop services
```

## Testing

### Test Structure

```
tests/
├── conftest.py             # Shared fixtures
├── unit/                   # Fast, no DB required
│   ├── test_jira_client.py
│   ├── test_transformations.py
│   └── test_metrics_calc.py
├── integration/            # Requires DB
│   ├── test_api.py
│   └── test_dagster_assets.py
└── validation/             # Data quality checks
    └── test_data_integrity.py
```

### Running Tests

```bash
# All tests with coverage
make test

# Or manually:
pytest tests/ -v --cov=app --cov=pipelines --cov-report=term-missing

# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Specific test
pytest tests/unit/test_jira_client.py::test_parse_issue -v
```

### Coverage Requirements

| Module | Minimum |
|--------|---------|
| `app/services/` | 80% |
| `pipelines/assets/` | 80% |
| `app/api/` | 70% |
| **Overall** | **75%** |

## Linting

### Tools

| Tool | Purpose |
|------|---------|
| **ruff** | Fast linter (replaces flake8, isort, pyupgrade) |
| **black** | Code formatter |

### Running Linters

```bash
# Check only (CI mode)
make lint

# Or manually:
ruff check app/ pipelines/ tests/
black --check app/ pipelines/ tests/

# Auto-fix
make format

# Or manually:
ruff check --fix app/ pipelines/ tests/
black app/ pipelines/ tests/
```

### Configuration (pyproject.toml)

```toml
[tool.ruff]
line-length = 88
select = ["E", "F", "W", "I", "B", "S"]
ignore = ["S101"]  # Allow assert in tests

[tool.black]
line-length = 88
target-version = ["py311"]
```

## Data Validation

### What is Validated

1. **Raw layer integrity** — dlt load completed, no missing required fields
2. **Clean layer consistency** — FK relationships valid, no orphan records
3. **Metrics correctness** — Views refresh successfully, no NULL in required columns

### Validation Commands

```bash
# Run all data validations
make validate

# What it does:
# 1. Check raw tables have data after last load
# 2. Check clean tables FK integrity
# 3. Refresh materialized views and check for errors
# 4. Run data quality assertions
```

### Validation in Dagster Assets

```python
from dagster import asset, AssetCheckResult, asset_check

@asset
def clean_jira_issues(...):
    """Transform raw to clean."""
    pass

@asset_check(asset=clean_jira_issues)
def check_no_orphan_issues(context, db):
    """Ensure all issues have valid project_id."""
    orphans = db.execute("""
        SELECT count(*) FROM clean_jira.issues i
        WHERE NOT EXISTS (
            SELECT 1 FROM clean_jira.projects p
            WHERE p.id = i.project_id
        )
    """).scalar()

    return AssetCheckResult(
        passed=orphans == 0,
        metadata={"orphan_count": orphans}
    )
```

## Makefile Reference

```makefile
# Main commands
check:      lint test validate     # Run all checks before commit
dev:        docker-compose up -d   # Start development environment
test:       pytest with coverage   # Run all tests
lint:       ruff + black check     # Check code style
format:     ruff fix + black       # Auto-format code
validate:   data integrity checks  # Validate data pipeline

# Database
migrate:    alembic upgrade head
migrate-create: alembic revision --autogenerate
migrate-down: alembic downgrade -1

# Docker
docker-build: docker-compose build
docker-up:    docker-compose up -d
docker-down:  docker-compose down -v
docker-logs:  docker-compose logs -f
```

## Pre-commit Checklist

Before every commit, run:

```bash
make check
```

This ensures:
- [ ] Code is formatted (black)
- [ ] No linting errors (ruff)
- [ ] All tests pass (pytest)
- [ ] Coverage >= 75%
- [ ] Data validations pass

## Key Concepts

### Dagster Assets

Assets represent data artifacts. Dependencies are explicit:

```python
@asset(group_name="jira")
def raw_jira_issues():
    """Load from Jira API to raw layer."""
    pass

@asset(deps=[raw_jira_issues])
def clean_jira_issues():
    """Transform raw to clean layer."""
    pass

@asset(deps=[clean_jira_issues])
def metrics_lead_time():
    """Refresh lead time materialized view."""
    pass
```

### dlt Pipelines

dlt handles incremental loading and state:

```python
pipeline = dlt.pipeline(
    pipeline_name="jira",
    destination="postgres",
    dataset_name="raw_jira"
)

source = jira_source(projects=["PROJ1", "PROJ2"])
pipeline.run(source, write_disposition="append")
```

### Data Flow

```
Jira API → dlt → raw_jira (append-only)
                    ↓
              clean_jira (normalized)
                    ↓
              metrics.mv_* (materialized views)
                    ↓
              Metabase (dashboards)
```

## Configuration

Environment variables (`.env`):

```bash
# Database
DATABASE_URL=postgresql://postgres:pass@localhost:5432/metrics

# Jira
JIRA_BASE_URL=https://company.atlassian.net
JIRA_USER_EMAIL=user@company.com
JIRA_API_TOKEN=secret

# Dagster
DAGSTER_HOME=/app/.dagster
```

## Adding New Data Source

1. Create dlt source in `pipelines/assets/{source}/raw.py`
2. Create clean transformation in `pipelines/assets/{source}/clean.py`
3. Add SQL schema in `db/schemas/clean_{source}.sql`
4. Add data validation checks
5. Update metrics views if needed
6. Register assets in `pipelines/definitions.py`
7. Write tests (unit + integration)

## Troubleshooting

### Dagster job fails
1. Check Dagster UI logs at http://localhost:3000
2. Verify credentials in `.env`
3. Check database connectivity

### dlt incremental not working
1. Check `_dlt_loads` table for state
2. Verify `primary_key` is set on resource
3. Check `write_disposition` setting

### Materialized view stale
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;
```

### Tests failing
```bash
# Run with verbose output
pytest -v -s --tb=short

# Run specific failing test
pytest tests/unit/test_example.py::test_name -v
```
