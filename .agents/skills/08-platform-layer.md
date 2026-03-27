---
name: platform-layer
description: Platform layer - FastAPI endpoints, in-memory token auth, Alembic migrations, and platform schema. Async context only (asyncpg).
triggers:
  - "platform layer"
  - "fastapi"
  - "api endpoint"
  - "alembic"
  - "migration"
  - "platform schema"
  - "authentication"
  - "token"
context:
  - agent.md
  - .agents/skills/02-database-patterns.md
---

# Skill: Platform Layer (FastAPI + Admin)

The platform schema and FastAPI application manage operational state: users, integrations, projects, and admin configuration.

---

## Schema: `platform`

```
platform.users               — platform accounts (bcrypt passwords)
platform.integration_types   — catalog: jira_cloud, gitlab, github, etc.
platform.tool_integrations   — user ↔ external system credentials
platform.projects            — registered projects (1:1 with clean_jira.projects)
platform.audit_log           — user action trail
```

The `platform` schema is managed by Alembic migrations. FastAPI uses it via SQLAlchemy ORM (async, asyncpg).

---

## Authentication

**In-memory token store.** No JWT. Tokens are `secrets.token_urlsafe(48)`.

```python
# Login → token
token = await auth_service.login(username, password)

# Authenticate request
session = await auth_service.validate_token(token)  # None if expired/invalid
```

Token TTL: 8 hours. Store max: 1000 tokens (oldest expire first on overflow).

**Limitations (by design):**
- Token store resets on server restart — users must re-login
- Not shared between replicas or uvicorn workers
- Not cluster-safe — single-instance deployment only

Do not add JWT or distributed session without discussion. The current design is intentional for simplicity.

---

## Adding a New API Endpoint

Pattern:
```python
# app/api/my_feature.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.admin_auth import require_admin  # auth dependency

router = APIRouter(prefix="/api/v1", tags=["MyFeature"])


@router.get("/my-feature/{item_id}")
async def get_my_feature(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _session=Depends(require_admin),   # require authentication
):
    result = await db.execute(select(MyModel).where(MyModel.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item
```

Register in `app/main.py`:
```python
from app.api.my_feature import router as my_feature_router
app.include_router(my_feature_router)
```

---

## Database Session Pattern (FastAPI)

```python
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

# Dependency injection — session auto-commits on success, rolls back on exception
async def my_endpoint(db: AsyncSession = Depends(get_db)):
    db.add(MyModel(...))
    await db.flush()       # write without commit (get generated IDs)
    await db.refresh(obj)  # reload from DB
    # commit happens automatically at end of request
```

Do NOT call `await db.commit()` manually in endpoint handlers. The `get_db()` dependency handles commit/rollback.

---

## ORM Models (`app/models/orm.py`)

```python
class ToolIntegration(Base):
    __tablename__ = "tool_integrations"
    __table_args__ = {"schema": "platform"}

    # Credential storage — one of these pairs is set, never both:
    # Secure: secret_reference + secret_provider
    # Insecure (dev/demo): api_token_unsafe (secret_provider MUST be None)
    secret_reference: Mapped[Optional[str]] = mapped_column(Text)
    secret_provider: Mapped[Optional[str]] = mapped_column(Text)  # No default!
    api_token_unsafe: Mapped[Optional[str]] = mapped_column(Text)
```

**CHECK constraint rule:**
- If `api_token_unsafe` is set → `secret_provider` and `secret_reference` MUST be None
- If `secret_reference` is set → `secret_provider` MUST be set, `api_token_unsafe` MUST be None

Do not add `default=` to `secret_provider`. The column has no default — caller must be explicit.

---

## Audit Log

Every admin action should be logged:
```python
from app.models.orm import AuditLog

audit = AuditLog(
    user_id=session.user_id,
    action="created_slice_rule",
    entity_type="slice_rule",
    entity_id=str(new_rule.id),
    details={"name": rule.name, "definition_id": str(rule.definition_id)},
)
db.add(audit)
```

---

## Dagster Client

FastAPI can trigger Dagster jobs via GraphQL:
```python
from app.services.dagster_client import DagsterClient

client = DagsterClient(url=settings.DAGSTER_GRAPHQL_URL)
run_id = await client.launch_job("recalculate_velocity_job")
```

`DAGSTER_GRAPHQL_URL` defaults to `http://dagster:3000/graphql` (docker service name).
For local dev (non-docker), set to `http://localhost:3000/graphql`.

---

## CORS Configuration

CORS origins are configured in `app/main.py`. In production (`ENVIRONMENT=production`):
```python
# Only these origins are allowed in production
PRODUCTION_ORIGINS = ["https://metrics.company.com"]
```

In development, localhost ports are added automatically. Never hardcode a specific domain in CORS — add it to the origins list and control via `ENVIRONMENT` env var.

---

## Rate Limiting

Rate limiting uses `slowapi` (backed by in-memory store — same single-instance limitation as auth).

```python
from app.limiter import limiter

@router.post("/expensive-operation")
@limiter.limit("10/minute")
async def expensive_operation(request: Request, ...):
    ...
```

`request: Request` must be the first parameter when using `@limiter.limit`.

---

## platform.projects ↔ clean_jira.projects

These are linked 1:1:
- `platform.projects.id` → `clean_jira.projects.platform_project_id`
- Creating a project in `platform.projects` (via Admin API) allows the clean layer to route Jira data to it
- Deleting a `platform.projects` row will cascade-break `clean_jira.projects` if FK is enforced

The `sync_project_partitions_sensor` in Dagster watches `platform.projects` and updates Dagster partition definitions.

---

## Adding a New Admin Configuration Type

Pattern for configuration stored in `metrics.*` tables (not `platform.*`):

1. Add migration: new table or new setting_key in `metrics.calculation_settings`
2. Add ORM model if needed (for `platform.*` tables only)
3. Add Pydantic schemas in `app/schemas/admin.py`
4. Add CRUD endpoints in `app/api/admin.py`
5. Add audit log entries for write operations
