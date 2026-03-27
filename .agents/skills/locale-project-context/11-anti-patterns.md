---
name: anti-patterns
description: Known anti-patterns that have broken or will break production. Read this before touching database, metrics, auth, or Polars code.
triggers:
  - "anti-pattern"
  - "wrong pattern"
  - "don't do"
  - "avoid"
context:
  - agent.md
  - .agents/skills/07-metrics-layer.md
  - .agents/skills/02-database-patterns.md
---

# Skill: Anti-Patterns

Things that have broken production, will break production, or mislead agents.
These rules exist because someone already made the mistake.

---

## Database Anti-Patterns

### ❌ Mixing async and sync drivers
```python
# WRONG: asyncpg in Dagster asset
@asset(...)
async def my_asset(database: DatabaseResource):  # Dagster doesn't support async assets
    ...

# WRONG: sync SQLAlchemy in FastAPI endpoint
@router.get("/data")
def my_endpoint(db: AsyncSession = Depends(get_db)):  # missing async, blocks event loop
    result = db.execute(...)  # sync execute on async session
```

### ❌ Manual commit in clean layer
```python
# WRONG — partial write if second op fails
with engine.connect() as conn:
    conn.execute(text("DELETE FROM ..."))
    conn.commit()  # ← NEVER
    conn.execute(text("INSERT INTO ..."))
    conn.commit()  # ← NEVER
```

### ❌ Writing to fact_values directly
```python
# WRONG — bypasses dedup, advisory lock, staging temp table
with engine.begin() as conn:
    conn.execute(text("INSERT INTO metrics.fact_values ..."), rows)

# CORRECT — df first, engine second, all params explicit
write_fact_values(
    df, engine,
    metric_ids=[calc_id],
    project_agg_ids=df["project_agg_id"].unique().to_list(),
    time_id_start=min(df["time_id"].to_list()),
    time_id_end=max(df["time_id"].to_list()),
)
```

### ❌ Hardcoding metric UUIDs
```python
# WRONG — UUIDs differ between environments
VELOCITY_CALC_ID = "3f4a8b2c-1234-..."

# CORRECT — use get_calculation_id(), NOT get_calc_id() (wrong name)
from pipelines.utils.metric_registry import get_calculation_id
calc_id = get_calculation_id(engine, "velocity_planned_sp")
```

### ❌ Wrong default DATABASE_URL
The default in `app/database.py` is `process_metrics`. If you see connection errors to a database named `metrics` (without prefix), you're missing `DATABASE_URL` in your `.env`.

### ❌ Querying without schema prefix
```python
# WRONG — ambiguous, fails if search_path not set correctly
conn.execute(text("SELECT * FROM issues"))

# CORRECT
conn.execute(text("SELECT * FROM clean_jira.issues"))
```

---

## Configuration Anti-Patterns

### ❌ Setting JIRA_PROJECTS env var expecting it to affect ingestion
`JIRA_PROJECTS` is in `docker-compose.yml` but has no effect on `raw.py`. Projects are configured only in `config/projects.yaml`.

### ❌ Editing config/projects.yaml to configure story points
Story points field binding is in `metrics.units` (DB), not in YAML. Edit via Admin API or SQL. The YAML does not sync to DB.

### ❌ Using `plans/*.md` as current specification
Files in `plans/` are AI session artifacts. They describe what was planned at a point in time — not what was implemented. The actual implementation is in code. Many plan files describe rejected or superseded approaches.

### ❌ Treating `_test_*.py` files as dead code
Files prefixed with `_` in `tests/unit/` are temporarily disabled tests. Do NOT delete or rename them.

---

## ORM Anti-Patterns

### ❌ Adding default="env" to secret_provider
```python
# WRONG — violates SQL CHECK constraint
secret_provider: Mapped[Optional[str]] = mapped_column(Text, default="env")

# CORRECT — no default, caller is explicit
secret_provider: Mapped[Optional[str]] = mapped_column(Text)
```

When creating a `ToolIntegration` with `api_token_unsafe`, explicitly set `secret_provider=None`.

### ❌ Using datetime.utcnow
```python
# WRONG — deprecated in Python 3.12
default=datetime.utcnow

# CORRECT
from datetime import UTC
default=lambda: datetime.now(UTC)
```

---

## Dagster Anti-Patterns

### ❌ compute_kind="sql" on Python-heavy assets
Only use `compute_kind="sql"` if the asset body contains ONLY `conn.execute(text(...))` with no Python control flow.

### ❌ DefaultScheduleStatus.RUNNING
```python
# WRONG — auto-starts schedule on deploy, bypasses operator control
default_status=DefaultScheduleStatus.RUNNING

# CORRECT
default_status=DefaultScheduleStatus.STOPPED
```

### ❌ print() in assets
Dagster does not capture stdout from assets. Use `logger.info()`.

### ❌ Omitting deps from @asset
```python
# WRONG — Dagster can execute this before sprint_issues is ready
@asset(group_name="metrics")
def calculate_velocity(...):
    df = read_table(engine, "clean_jira.sprint_issues")  # implicit dependency

# CORRECT
@asset(group_name="metrics", deps=["clean_jira_sprint_issues", "clean_jira_sprints"])
```

---

## Polars Anti-Patterns

### ❌ Polars 1.0 API on a <1.0 codebase
The project pins `polars<1.0.0`. Don't use Polars 1.0+ syntax. Specifically:
- `df.group_by()` (1.0 style) vs `df.groupby()` (0.x style) — verify for your exact version
- `pl.Categorical` handling changed in 1.0

### ❌ Writing Struct columns to DB without serialization
Polars Struct dtype → psycopg2 crash. Always serialize to JSON string first.

### ❌ Inplace mutation
```python
df["col"] = value  # TypeError in Polars
df = df.with_columns(pl.lit(value).alias("col"))  # correct
```

---

## Migration Anti-Patterns

### ❌ Hash-named migrations
```
# WRONG — breaks sorted ordering
e17a9cb848b6_my_change.py

# CORRECT
0032_my_change.py
```

### ❌ Editing existing migrations
Never modify a committed migration. Always create a new one.

### ❌ Non-idempotent seed migrations
```python
# WRONG — fails if run twice
op.execute("INSERT INTO metrics.grains (id, grain_code) VALUES (..., 'issue')")

# CORRECT
op.execute("""
    INSERT INTO metrics.grains (id, grain_code)
    VALUES (:id, 'issue')
    ON CONFLICT (grain_code) DO NOTHING
""")
```

---

## Non-Existent Functions (Common Hallucinations)

AI agents frequently hallucinate these — they do NOT exist:

| Wrong | Correct |
|---|---|
| `get_calc_id()` | `get_calculation_id()` from `metric_registry` |
| `clear_all_caches()` | `clear_cache()` from `metric_registry` |
| `filter_by_slice_value()` | does not exist — filter manually with `df.filter()` |
| `get_calc_settings()` | does not exist — query `metrics.calculation_settings` directly |
| `create_app()` in `app.main` | import `app` directly: `from app.main import app` |
| `write_fact_values(engine, df, calc_ids=[...])` | `write_fact_values(df, engine, metric_ids=[...], project_agg_ids=[...], time_id_start=..., time_id_end=...)` |
| `read_table(engine, "table.name", query="...", params={})` | `read_table(engine, "SELECT ...", {"param": val})` |
| `resolve_unit_field()` returns string | returns `dict {"source_field_id": uuid_str, "source_entity": str}` or `None` |

---

## Architecture Anti-Patterns

### ❌ Adding microservices
This is an intentional monolith. Don't add separate services for individual functions. All compute runs in Dagster. All API in FastAPI. All data in PostgreSQL.

### ❌ Implementing bi/providers/ for data access
`bi/` providers are for BI system integration (Metabase config, Superset setup) — not for querying metrics data. Data access goes through FastAPI.

### ❌ Assuming multi-replica deployment
Auth token store, advisory locks, and Dagster scheduler assume single-instance. Don't add features that require distributed state without re-architecting auth first.
