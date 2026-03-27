# Admin Security & Quality Fixes — 2026-03-26

## Context

Deep review of admin subsystem (`app/api/admin.py`, `app/services/admin_auth.py`,
`streamlit_admin/`) revealed 12 issues. This plan fixes all of them.

---

## Issues being fixed

| ID | Severity | Description |
|----|----------|-------------|
| F-001 | CRITICAL | Plaintext passwords in DB — migrate to bcrypt |
| F-002 | HIGH | Token stored in URL query param — remove entirely |
| F-003 | MEDIUM | In-memory token store — add size cap + TTL cleanup |
| F-004 | HIGH | No rate limiting on POST /admin/auth/login |
| F-005 | MEDIUM | ~390 lines dead v1 tab code in streamlit_admin/app.py |
| F-006 | MEDIUM | IntegrityError details (constraint names, table names) exposed in HTTP 409 |
| F-007 | MEDIUM | N+1 HTTP calls in _tab_metrics_catalog (3×N per project) |
| F-008 | MEDIUM | DELETE endpoints return 200 OK even if ID didn't exist |
| F-009 | MEDIUM | Tests test dead v1 tab functions, not the active v2 code path |
| F-010 | LOW | json_editor uses str().replace("'", '"') — breaks on apostrophes |
| F-011 | LOW | scope_selector in components.py unused in active code path |
| F-013 | LOW | CORS missing localhost:8501 (Streamlit port) |

---

## Files to create

### `app/limiter.py` (NEW)

Extract the slowapi limiter from `app/main.py` into a shared module so both
`main.py` and `admin.py` can import it without a circular dependency.

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

---

## Files to modify

### `pyproject.toml`

Add to `[project].dependencies`:
```
"bcrypt>=4.0.0,<5.0.0",
```

---

### `app/main.py`

Replace the inline `limiter = Limiter(...)` initialization with an import from
the new shared module:

```python
from app.limiter import limiter
```

Remove the original lines:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
...
limiter = Limiter(key_func=get_remote_address)
```

Replace with:
```python
from slowapi import _rate_limit_exceeded_handler
from app.limiter import limiter
```

Keep `app.state.limiter = limiter` and
`app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`
as-is.

Also add `http://localhost:8501` to the development ALLOWED_ORIGINS list (F-013):
```python
ALLOWED_ORIGINS.extend([
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "http://localhost:8501",  # Streamlit admin
])
```

---

### `app/services/admin_auth.py`

**F-001 fix — bcrypt with lazy migration:**

Add `import bcrypt` at the top.

Replace `verify_password` with a function that:
1. Detects whether the stored value is a bcrypt hash (starts with `$2b$` or `$2a$`)
2. If bcrypt hash → use `bcrypt.checkpw(plain.encode(), stored.encode())`
3. If plaintext → use `hmac.compare_digest(plain, stored)` for backward compat
4. Returns a tuple `(is_valid: bool, needs_rehash: bool)` so the login endpoint
   can rehash and update the DB on next successful login

Add a `hash_password(plain: str) -> str` function using `bcrypt.hashpw`.

**F-003 fix — store size cap and cleanup:**

Add a `MAX_TOKEN_STORE_SIZE = 1000` constant.

In `save_session`, before adding the new entry, if `len(_TOKEN_STORE) >= MAX_TOKEN_STORE_SIZE`:
- Purge all expired sessions (iterate and delete where `expires_at < now()`)
- If still >= MAX_TOKEN_STORE_SIZE, delete the oldest half by `expires_at`

Full revised `admin_auth.py`:

```python
"""Simple in-memory token auth for admin endpoints."""

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt

MAX_TOKEN_STORE_SIZE = 1000


@dataclass
class AdminSession:
    user_id: str
    email: str
    display_name: str
    is_admin: bool
    expires_at: datetime


_TOKEN_STORE: dict[str, AdminSession] = {}


def create_token(ttl_minutes: int = 480) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    return token, expires_at


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, stored: str) -> tuple[bool, bool]:
    """
    Returns (is_valid, needs_rehash).
    needs_rehash is True when the stored value is still plaintext.
    """
    is_bcrypt = stored.startswith(("$2b$", "$2a$", "$2y$"))
    if is_bcrypt:
        valid = bcrypt.checkpw(plain.encode(), stored.encode())
        return valid, False
    # Legacy plaintext path — constant-time compare to avoid timing attacks
    valid = hmac.compare_digest(plain, stored)
    return valid, valid  # needs_rehash only when valid (no point rehashing wrong password)


def _purge_expired() -> None:
    now = datetime.now(UTC)
    expired_keys = [k for k, s in _TOKEN_STORE.items() if s.expires_at < now]
    for k in expired_keys:
        _TOKEN_STORE.pop(k, None)


def save_session(token: str, session: AdminSession) -> None:
    if len(_TOKEN_STORE) >= MAX_TOKEN_STORE_SIZE:
        _purge_expired()
        if len(_TOKEN_STORE) >= MAX_TOKEN_STORE_SIZE:
            # Evict oldest half by expiry
            sorted_keys = sorted(_TOKEN_STORE, key=lambda k: _TOKEN_STORE[k].expires_at)
            for k in sorted_keys[: MAX_TOKEN_STORE_SIZE // 2]:
                _TOKEN_STORE.pop(k, None)
    _TOKEN_STORE[token] = session


def get_session(token: str) -> AdminSession | None:
    session = _TOKEN_STORE.get(token)
    if not session:
        return None
    if session.expires_at < datetime.now(UTC):
        _TOKEN_STORE.pop(token, None)
        return None
    return session


def revoke_token(token: str) -> None:
    _TOKEN_STORE.pop(token, None)


def parse_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return None
    token = auth_header[len(prefix):].strip()
    return token or None
```

---

### `app/api/admin.py`

**F-004 fix — rate limiting on login:**

Add imports at top:
```python
from fastapi import Request
from app.limiter import limiter
```

Decorate the login endpoint and add `request: Request` as first parameter
(required by slowapi):
```python
@router.post("/auth/login", response_model=AdminLoginResponse)
@limiter.limit("10/minute")
async def admin_login(request: Request, payload: AdminLoginRequest, db: DBSession):
```

**F-001 integration — lazy rehash on login:**

Update the `verify_password` call in `admin_login` to handle the new tuple return
and rehash if needed:

```python
is_valid, needs_rehash = verify_password(payload.password, row["password_hash"])
if not is_valid:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

if needs_rehash:
    new_hash = hash_password(payload.password)
    await db.execute(
        text("UPDATE platform.users SET password_hash = :h WHERE id = :id"),
        {"h": new_hash, "id": str(row["id"])},
    )
```

Add import: `from app.services.admin_auth import ... hash_password` (add to existing import).

**F-006 fix — sanitize IntegrityError:**

Replace all three occurrences of:
```python
raise HTTPException(status_code=409, detail=f"Constraint violation: {exc.orig}") from exc
```
with:
```python
logger.warning("IntegrityError in %s: %s", __name__, exc.orig)
raise HTTPException(status_code=409, detail="Conflict: a record with this key already exists") from exc
```

Add `import logging` and `logger = logging.getLogger(__name__)` at top of admin.py.

**F-008 fix — DELETE 404 on missing record:**

Replace all three DELETE handlers with rowcount check:

```python
@router.delete("/commitment-rules/{rule_id}")
async def delete_commitment_rule(rule_id: UUID, db: DBSession, _admin: ...):
    result = await db.execute(
        text("DELETE FROM metrics.commitment_rules WHERE id=:id"),
        {"id": str(rule_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Commitment rule not found")
    return {"status": "ok"}
```

Apply the same pattern to `delete_calculation_setting` and `delete_slice_rule`.

---

### `streamlit_admin/app.py`

**F-002 fix — remove token from URL:**

In `_ensure_state()` (lines 56-62), remove the query_params block entirely:
```python
# REMOVE these lines:
if not st.session_state.token:
    query_token = st.query_params.get("admin_token")
    if query_token:
        st.session_state.token = str(query_token)
```

In `_login_view()` (line 85), remove:
```python
# REMOVE:
st.query_params["admin_token"] = st.session_state.token
```

In `_logout()` (lines 99-100), remove:
```python
# REMOVE:
if "admin_token" in st.query_params:
    del st.query_params["admin_token"]
```

In `main()` (lines 1447-1448), remove:
```python
# REMOVE:
if "admin_token" in st.query_params:
    del st.query_params["admin_token"]
```

**F-005 fix — remove dead v1 tab functions:**

Delete the following functions entirely from `streamlit_admin/app.py`:
- `_tab_contracts` (around line 104)
- `_tab_commitment` (around line 115)
- `_tab_settings` (around line 212)
- `_tab_units` (around line 287)
- `_tab_slices` (around line 360)
- `_tab_catalog` (around line 458)
- `_page_definitions_matrix` (around line 573)

These are confirmed dead: `_page_configuration` (the active entry point) uses
`_tab_metrics_catalog`, `_tab_commitment_v2`, `_tab_settings_v2`,
`_tab_units_v2`, `_tab_slices_v2`, and `_tab_validate` — none of the v1 variants.

**F-007 fix — bulk fetch in _tab_metrics_catalog:**

In `_tab_metrics_catalog` (around line 687-697), replace the per-project loop
with 3 bulk calls followed by client-side grouping:

```python
# Replace:
for project in projects:
    pid = project["project_id"]
    project_settings[pid] = client.request("GET", "/admin/calculation-settings", token=token, params={"project_id": pid})
    project_commitment_rules[pid] = client.request("GET", "/admin/commitment-rules", token=token, params={"project_id": pid})
    project_units[pid] = client.request("GET", "/admin/units", token=token, params={"project_id": pid})

# With:
all_settings = client.request("GET", "/admin/calculation-settings", token=token)
all_commitment_rules = client.request("GET", "/admin/commitment-rules", token=token)
all_units = client.request("GET", "/admin/units", token=token)

project_settings = {}
project_commitment_rules = {}
project_units = {}
for project in projects:
    pid = project["project_id"]
    project_settings[pid] = [s for s in all_settings if s.get("project_id") == pid]
    project_commitment_rules[pid] = [r for r in all_commitment_rules if r.get("project_id") == pid]
    project_units[pid] = [u for u in all_units if u.get("project_id") == pid]
```

---

### `streamlit_admin/components.py`

**F-010 fix — json_editor apostrophe bug:**

Replace the broken serialization:
```python
# REMOVE:
value=("{}" if value is None else str(value).replace("'", '"')),

# REPLACE WITH:
value=("{}" if value is None else json.dumps(value, ensure_ascii=False, indent=2)),
```

Move the `import json` from inside the function body to the top of the file.

**F-011 fix — remove unused scope_selector:**

Delete the entire `scope_selector` function from `components.py`. It is not called
from any active code path in `app.py`. If tests import it, those tests are also
for dead code and will be updated below.

---

## Test file updates

### `tests/unit/test_admin_auth.py`

Update `test_verify_password_uses_constant_time_compare` (and any other tests
calling `verify_password`) to:
1. Accept the new `(bool, bool)` return type
2. Test both the bcrypt path and the legacy plaintext path
3. Test `hash_password` produces valid bcrypt hashes
4. Test that `save_session` evicts entries when store exceeds `MAX_TOKEN_STORE_SIZE`

### `tests/unit/test_api_admin_unit.py`

- Add a test that `POST /admin/auth/login` is rate-limited (mock the limiter or
  verify the `@limiter.limit` decorator is applied)
- Update any login tests that mock `verify_password` to account for the tuple
  return value `(True, False)` / `(False, False)` / `(True, True)`
- Add tests that `DELETE /commitment-rules/{uuid}`, `DELETE /calculation-settings/{uuid}`,
  and `DELETE /slice-rules/{uuid}` return 404 when no row is deleted
  (mock `result.rowcount = 0`)
- Add tests that `IntegrityError` responses return generic message (no `exc.orig` content)

### `tests/unit/test_app_main_admin_router.py`

- Remove or rewrite test that checks limiter is configured on app (verify
  `app.state.limiter` is set from `app.limiter` module)

### `tests/unit/test_streamlit_admin_app.py`

- Delete tests for dead v1 functions: `test_tab_contracts_*`, `test_tab_commitment_*`,
  `test_tab_settings_*`, `test_tab_units_*`, `test_tab_slices_*`, `test_tab_catalog_*`,
  `test_page_definitions_matrix_*`
- Rewrite `test_main_renders_tabs_when_authenticated` to patch the v2 tab functions
  (`_tab_metrics_catalog`, `_tab_commitment_v2`, `_tab_settings_v2`,
  `_tab_units_v2`, `_tab_slices_v2`, `_tab_validate`) and verify they are called
- Add test that `_ensure_state` does NOT read from `st.query_params`
- Add test that `_login_view` does NOT write to `st.query_params` after successful login

### `tests/unit/test_streamlit_admin_components.py`

- Update `test_json_editor_*` to verify apostrophes in string values round-trip
  correctly through `json.dumps` (they should no longer be corrupted)
- Remove any test for `scope_selector` if it exists (dead code)

### `tests/unit/test_streamlit_admin_client.py`

- No changes needed (client.py is correct)

---

## Migration note (plaintext → bcrypt)

No batch SQL migration is required. The lazy-rehash approach in the login
endpoint will transparently upgrade each admin user's password hash to bcrypt
on their next successful login. This requires zero downtime and no manual DB
changes.

---

## Summary of file changes

| File | Action |
|------|--------|
| `pyproject.toml` | add `bcrypt>=4.0.0,<5.0.0` |
| `app/limiter.py` | CREATE — shared slowapi Limiter instance |
| `app/main.py` | import from app.limiter, add localhost:8501 to CORS |
| `app/services/admin_auth.py` | bcrypt verify/hash, tuple return, store size cap |
| `app/api/admin.py` | rate limit login, lazy rehash, sanitize IntegrityError, DELETE 404 |
| `streamlit_admin/app.py` | remove query_params token, delete 7 dead v1 functions, fix N+1 |
| `streamlit_admin/components.py` | json.dumps in json_editor, remove scope_selector |
| `tests/unit/test_admin_auth.py` | update for new verify_password signature + new coverage |
| `tests/unit/test_api_admin_unit.py` | add rate limit, DELETE 404, IntegrityError tests |
| `tests/unit/test_app_main_admin_router.py` | update limiter test |
| `tests/unit/test_streamlit_admin_app.py` | delete dead tests, add query_params absence tests |
| `tests/unit/test_streamlit_admin_components.py` | update json_editor test |
