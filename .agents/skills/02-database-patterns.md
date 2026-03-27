---
name: database-patterns
description: PostgreSQL patterns specific to this project (drivers, transactions, read/write utilities). Follow exactly — deviations have caused production bugs.
triggers:
  - "database"
  - "postgres"
  - "read_table"
  - "write_fact_values"
  - "transaction"
  - "engine.begin"
context:
  - agent.md
  - .agents/skills/12-tech-debt.md
---

# Skill: Database Patterns

PostgreSQL patterns specific to this project. Follow these exactly — deviations have caused production bugs.

---

## Schema Map (4 schemas, 1 database)

```
process_metrics (database)
├── raw_jira      — Bronze. dlt-managed. Never write here manually.
├── clean_jira    — Silver. Dagster clean assets. Normalized relational.
├── metrics       — Gold. Dagster metric assets. Generic Long Store.
└── platform      — Operational. FastAPI + Alembic. Users, integrations, projects.
```

Always use schema-qualified references: `clean_jira.issues`, not just `issues`.

---

## Two Connection Contexts — Never Cross Them

| Context | Driver | Pattern | Where used |
|---|---|---|---|
| Dagster assets | `psycopg2` (sync) | `DatabaseResource.get_engine()` → sync SQLAlchemy | `pipelines/` |
| FastAPI endpoints | `asyncpg` (async) | `get_db()` dependency → `AsyncSession` | `app/` |

**Never use `asyncpg` / `async` SQLAlchemy inside a Dagster asset.** Dagster assets run in sync context. The event loop is not available.

**Never use `psycopg2` / sync SQLAlchemy inside a FastAPI endpoint.** Blocks the event loop, degrades performance under load.

---

## Transaction Patterns

### Canonical pattern for clean layer assets (Dagster)

```python
# ONE engine.begin() block per asset. Never call conn.commit() manually.
with engine.begin() as conn:
    conn.execute(text("DELETE FROM clean_jira.my_table WHERE project_id = :pid"), {"pid": project_id})
    conn.execute(text("INSERT INTO clean_jira.my_table ..."), rows)
# Transaction commits automatically on context exit, rolls back on exception
```

Anti-pattern (causes partial writes):
```python
# WRONG — two separate transactions, second can fail leaving inconsistent state
with engine.connect() as conn:
    conn.execute(text("DELETE ..."))
    conn.commit()          # ← NEVER DO THIS
    conn.execute(text("INSERT ..."))
    conn.commit()
```

### Parameterized queries — always

```python
from sqlalchemy import text

# Always use :param notation, never f-strings or % formatting
conn.execute(
    text("SELECT * FROM clean_jira.issues WHERE project_id = :pid AND status = :status"),
    {"pid": project_id, "status": "Done"},
)
```

### Array parameters (PostgreSQL-specific)

```python
# Passing a list of UUIDs — must cast explicitly
conn.execute(
    text("""
        DELETE FROM metrics.fact_values
        WHERE metric_id = ANY(CAST(:ids AS uuid[]))
    """),
    {"ids": "{" + ",".join(str(i) for i in metric_ids) + "}"},
)
```

---

## Reading Data into Polars

Always use `read_table()` from `pipelines/utils/polars_db.py`. Never write raw `pl.read_database_uri()` calls in assets.

```python
from pipelines.utils.polars_db import read_table

# Signature: read_table(engine, query, params=None) -> pl.DataFrame
# Second argument is ALWAYS a SQL query string, never a bare table name.

# Full table
df = read_table(engine, "SELECT * FROM clean_jira.issues")

# With filter (parameterized) — pass params as third positional arg
df = read_table(
    engine,
    "SELECT * FROM clean_jira.issues WHERE project_id = :pid",
    {"pid": project_id},
)

# Bare table names are NOT supported — always use full SELECT queries:
# read_table(engine, "clean_jira.issues")  <- WRONG on Windows + psycopg2
df = read_table(engine, "SELECT * FROM clean_jira.issues")  # CORRECT
```

`read_table()` tries three paths internally:
1. `pl.read_database_uri(query, uri)` — fast path, fails on Windows with psycopg2
2. pandas bridge via SQLAlchemy — fallback when path 1 fails
3. pandas bridge with `params` dict — always used when params dict is provided

**Never call `pl.read_database_uri()` directly** — it skips fallback logic and fails on Windows.
**Always use full `SELECT` queries** — bare table names (e.g., `"clean_jira.issues"`) fail in path 1 and produce incorrect results in path 2.

---

## Writing Metrics

Never write to `metrics.fact_values` directly. Always use `write_fact_values()`:

```python
from pipelines.utils.polars_db import write_fact_values

# Signature:
# write_fact_values(df, engine, metric_ids, project_agg_ids, time_id_start, time_id_end) -> int

# Required columns in fact_df:
# metric_id, project_agg_id, time_id, value
# Optional columns: entity_type, entity_id, event_start_at, event_end_at,
#   slice_rule_id, slice_value, commitment_rule_id, settings_id, context_json

time_ids = fact_df["time_id"].to_list()
rows_written = write_fact_values(
    fact_df,                                        # df first
    engine,                                         # engine second
    metric_ids=[calc_id],                           # list of metric UUID strings
    project_agg_ids=fact_df["project_agg_id"].unique().to_list(),
    time_id_start=min(time_ids),
    time_id_end=max(time_ids),
)
```

`write_fact_values()` is atomic and idempotent:
1. Stage into temp table
2. DELETE existing rows for same metric_id × project_agg_id × time_id range
3. INSERT from temp table
4. Optional advisory lock (env `FACT_VALUES_USE_ADVISORY_LOCK`)
5. Returns count of rows inserted

---

## Polars Struct Columns → DB (Critical)

Polars `Struct` dtype columns CANNOT be written via pandas bridge directly — psycopg2 does not know how to serialize them.

```python
# Before any to_sql() call, serialize Struct columns to JSON strings:
import json

struct_cols = [col for col, dtype in zip(df.columns, df.dtypes) if isinstance(dtype, pl.Struct)]
for col in struct_cols:
    df = df.with_columns(
        pl.col(col).map_elements(lambda v: json.dumps(v) if v is not None else None)
    )
```

This is already handled inside `write_fact_values()` for `context_json`. If you write custom data directly, handle it yourself.

---

## Alembic Migrations

### Naming convention
Always number sequentially: `0032_description.py`, `0033_description.py`.
Never use hash names (the `e17a9cb848b6_*` file is a historical anomaly — do not repeat).

### Creating a migration
```bash
make migrate-create MSG="add_my_new_column"
# Creates: db/migrations/versions/0032_add_my_new_column.py
```

### Migration must be idempotent
Use `ON CONFLICT DO NOTHING` for seed data. Use `IF NOT EXISTS` for tables and indexes.

```python
def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO metrics.grains (id, grain_code)
        VALUES (:id, 'my_grain')
        ON CONFLICT (grain_code) DO NOTHING
    """), {"id": str(uuid.uuid4())})
```

### Never modify existing migrations
Existing migrations in `versions/` are applied to production. Only add new ones. Editing an existing migration will cause Alembic head mismatch in environments where it's already applied.

### Schema sync is mandatory (`migrations` + `db/schemas`)
If you change database schema (tables, columns, constraints, indexes, views):
1. Add Alembic migration in `db/migrations/versions/`.
2. Update the corresponding canonical SQL file in `db/schemas/*.sql`.
3. Add/update `COMMENT ON TABLE` / `COMMENT ON COLUMN` in English for changed objects.

A migration without matching schema file update is considered incomplete.

Example workflow:
```text
Change DB schema -> create migration -> update db/schemas/*.sql -> verify comments exist
```

---

## Useful PostgreSQL Patterns

### Advisory locks (concurrent write protection)
```python
# Already used in write_fact_values, but useful to know:
conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": sorted_calc_codes_str})
```

### Check if table exists before querying
```python
from pipelines.assets.jira.clean._utils import table_exists

if not table_exists(engine, "raw_jira", "issues"):
    logger.warning("raw_jira.issues not found, skipping")
    return
```

### Upsert pattern (clean layer dimensions)
```python
conn.execute(text("""
    INSERT INTO clean_jira.issue_statuses (id, project_id, jira_status_id, name, category)
    VALUES (:id, :project_id, :jira_id, :name, :category)
    ON CONFLICT (project_id, jira_status_id)
    DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category
"""), rows)
```

### Bulk insert with executemany
```python
# For large datasets, use executemany (psycopg2 uses COPY-like batching)
conn.execute(text("INSERT INTO clean_jira.my_table (a, b, c) VALUES (:a, :b, :c)"), list_of_dicts)
```

### Querying metrics.v_facts view (for statistics and debugging)
```python
# v_facts is the denormalized view — use for Metabase queries and diagnostics
# Do NOT use for metric writes — always write to fact_values directly
df = read_table(
    engine,
    "SELECT * FROM metrics.v_facts WHERE calc_code = :cc AND project_key = :pk",
    {"cc": "velocity_planned_sp", "pk": "PROJ"},
)
```

### When to use `v_facts` vs `fact_values`
| Use case | Table |
|---|---|
| Metabase dashboard queries | `metrics.v_facts` |
| Dagster asset_check validation | `metrics.fact_values` (with metric_id UUID) |
| Writing metric results | `metrics.fact_values` (via `write_fact_values()`) |
| Debugging specific metric | `metrics.v_facts` (human-readable calc_code) |
| Aggregation stats in `metrics_all` | `metrics.v_facts` |

---

## Connection Pool (Dagster)

The `DatabaseResource` uses `lru_cache` keyed on connection string:
```python
@lru_cache(maxsize=8)
def _build_engine(url: str, pool_size: int, ...) -> Engine:
    ...
```

Do not create new engines in assets. Always use `database.get_engine()`. Creating ad-hoc engines leaks connections.

Pool defaults (from env vars):
- `DB_POOL_SIZE=5`
- `DB_MAX_OVERFLOW=10`
- `DB_POOL_RECYCLE=1800` (30 min — prevents stale connections after PostgreSQL timeout)

---

## Querying clean_jira from Dagster

Standard pattern for loading data per project:
```python
issues_df = read_table(engine, "SELECT * FROM clean_jira.issues")

# Filter per project in Polars (cheaper than N SQL queries)
for project_id in issues_df["project_id"].unique().to_list():
    project_df = issues_df.filter(pl.col("project_id") == project_id)
    ...
```

Exception: For very large tables (changelog, field_value_changelog), filter in SQL:
```python
changelog_df = read_table(
    engine,
    "SELECT * FROM clean_jira.issue_status_changelog WHERE project_id = :pid",
    {"pid": project_id},
)
```
