---
name: testing-patterns
description: Project-specific testing strategy for Polars calculations (pure unit) and integration tests. Pytest config in pyproject.toml with asyncio_mode=auto.
triggers:
  - "test"
  - "pytest"
  - "unit test"
  - "integration test"
  - "fixture"
  - "conftest"
context:
  - agent.md
  - .agents/skills/09-polars-patterns.md
---

# Skill: Testing Patterns

Testing strategy for this project. See also installed marketplace skill `python-testing` for general pytest patterns.

---

## Core Rule

**Unit tests for calculations: no database, no mocks of internal code.**
All calculation functions in `pipelines/calculations/` take Polars DataFrames as input.
Build those DataFrames in-memory in tests.

---

## Test Structure

```
tests/
├── conftest.py               # Shared fixtures
├── unit/                     # Fast, no DB needed
│   ├── test_velocity.py
│   ├── test_lead_time.py
│   ├── test_cfd.py
│   ├── _test_*.py            # Disabled tests (underscore prefix) — DO NOT DELETE
│   └── ...
└── integration/              # Needs DB or HTTP
    ├── test_api_*.py
    └── test_dagster_assets.py
```

Disabled test files (`_test_*.py`) are temporarily skipped, not deleted. They cover calculations under active development. Do not rename them to `test_*.py` unless the implementation is complete.

---

## Unit Test Pattern (Polars fixtures)

```python
import polars as pl
import pytest
from datetime import date, datetime, timezone

from pipelines.calculations.velocity import calculate_velocity


@pytest.fixture
def sprint_issues_df():
    """Minimal sprint_issues fixture for velocity tests."""
    return pl.DataFrame({
        "issue_key": ["PROJ-1", "PROJ-2", "PROJ-3"],
        "sprint_id": ["sprint-uuid-1"] * 3,
        "project_id": ["project-uuid-1"] * 3,
        "story_points": [3.0, 5.0, None],   # None = unestimated
        "is_active": [True, True, True],
        "added_at": [datetime(2026, 1, 1, tzinfo=timezone.utc)] * 3,
        "removed_at": [None, None, None],
    })


@pytest.fixture
def sprints_df():
    return pl.DataFrame({
        "id": ["sprint-uuid-1"],
        "project_id": ["project-uuid-1"],
        "name": ["Sprint 1"],
        "start_date": [date(2026, 1, 1)],
        "end_date": [date(2026, 1, 14)],
        "complete_date": [date(2026, 1, 14)],
        "state": ["closed"],
    })


def test_velocity_completed_sp(sprint_issues_df, sprints_df):
    result = calculate_velocity(sprint_issues_df, sprints_df, unit="story_points")

    assert result.shape[0] == 1  # one sprint
    completed_row = result.filter(pl.col("calc_code") == "velocity_completed_sp")
    assert completed_row["value"][0] == 8.0  # 3 + 5, None excluded
```

---

## What to Test in Calculation Functions

For each calculation module, test:

1. **Happy path** — normal input produces expected output
2. **Empty input** — returns empty DataFrame, does not raise
3. **All-None values** — gracefully handles missing story_points, dates, etc.
4. **Edge case: single issue/sprint** — doesn't blow up with n=1
5. **Slicing correctness** — filtered subset produces proportional results
6. **Date boundaries** — issues exactly on boundary dates are included/excluded correctly

---

## Datetime Fixtures

Always use timezone-aware datetimes:
```python
from datetime import datetime, timezone, UTC

# Correct
dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

# Wrong — naive datetime causes comparison failures with tz-aware DB data
dt = datetime(2026, 1, 15, 12, 0, 0)
```

---

## Testing Slicing Logic

`apply_slicing()` requires a real DB engine (it queries `metrics.slice_rules` and `clean_jira` FK graph). Test it in integration tests, not unit tests.

For unit tests, test slice behavior by manually filtering the DataFrame:
```python
def test_slicing_by_issue_type(issues_df):
    # Simulate what apply_slicing does: filter by dimension value, run calc
    bug_df = issues_df.filter(pl.col("type_name") == "Bug")
    story_df = issues_df.filter(pl.col("type_name") == "Story")

    bug_result = calculate_my_metric(bug_df)
    story_result = calculate_my_metric(story_df)

    assert not bug_result.is_empty()
    assert bug_result["value"].sum() <= issues_df.shape[0]
```

---

## Testing Admin Auth

```python
from app.services.admin_auth import clear_token_store

@pytest.fixture(autouse=True)
def reset_token_store():
    """Clear in-memory token store between tests."""
    yield
    clear_token_store()  # Prevents token leakage between tests
    # clear_token_store() is the correct function name — NOT clear_all_caches()
```

---

## API Tests (FastAPI)

`app/main.py` does not have a `create_app()` factory — the app is created at module level. Import the `app` instance directly:

```python
import pytest
from httpx import AsyncClient
from app.main import app   # import the app instance, not a factory function


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
```

Note: `asyncio_mode = "auto"` in `pytest.ini` — `@pytest.mark.asyncio` is not needed. Adding it is harmless but redundant.

---

## Metric Registry Cache in Tests

If your test exercises code that calls `get_calculation_id()` or `get_project_agg_id()`, clear the cache between tests:

```python
from pipelines.utils.metric_registry import clear_cache  # correct name: clear_cache()

@pytest.fixture(autouse=True)
def clear_registry_cache():
    yield
    clear_cache()  # NOT clear_all_caches() — that function does not exist
```

Otherwise UUID lookups from one test pollute the next (the cache is module-level).

**Two separate cache functions — not interchangeable:**
- `clear_cache()` from `pipelines.utils.metric_registry` — clears metric UUID registry cache
- `clear_token_store()` from `app.services.admin_auth` — clears auth token store

Neither is called `clear_all_caches()` — that function does not exist anywhere.

---

## What NOT to Mock

- `pipelines/calculations/*.py` — test these directly with real DataFrames
- `polars` operations — never mock DataFrame methods
- `metrics.fact_values` schema — if testing write logic, use a real test DB

What IS appropriate to mock:
- External HTTP calls (Jira API in `raw.py`)
- `DatabaseResource` in Dagster asset tests
- `get_db()` in FastAPI tests (use `app.dependency_overrides`)

---

## Running Tests

```bash
make test                          # All tests with coverage
pytest tests/unit/ -v              # Unit only
pytest tests/unit/test_velocity.py # Single file
pytest -k "velocity" -v            # By name pattern
pytest --co -q                     # List tests without running
```

Coverage report: `htmlcov/index.html` after `make test`.

Pytest config is in `pyproject.toml` (`[tool.pytest.ini_options]`):
- `asyncio_mode = "auto"` — all async tests run without `@pytest.mark.asyncio`
- `testpaths = ["tests"]`

---

## Marketplace Skill Reference

For general pytest patterns (fixtures, parametrize, marks, conftest), see:
```
/python-testing  (laurigates/claude-plugins@python-testing)
```
