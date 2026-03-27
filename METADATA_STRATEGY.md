# Metadata Management Strategy (Pragmatic Dagster + SQL)

## Overview
This project uses a lightweight metadata strategy aligned with the monolith architecture:
- Dagster asset metadata is the primary catalog for metric logic.
- PostgreSQL `COMMENT ON` is the primary catalog for schema semantics.
- No external metadata platform (DataHub/OpenMetadata) at current scale.

Goal: improve discoverability and consistency without adding operational overhead.

## Principles
1. Code-first metadata: keep metadata close to assets and schema DDL.
2. English-only metadata: descriptions, keys, comments, formulas.
3. No dead documentation: avoid hand-maintained docs that drift from code.
4. Incremental rollout: enforce a small mandatory baseline, then expand.

---

## Scope

### In scope
- `pipelines/assets/metrics/*.py` metadata baseline
- Metadata asset check in Dagster for required fields
- SQL comments for critical `metrics.*` objects
- Synchronization rules for `db/migrations` and `db/schemas/*.sql`

### Out of scope (for now)
- External metadata catalog (DataHub/OpenMetadata)
- Mandatory owner model
- Stable dashboard URLs in metadata
- Manual `SCHEMA_REFERENCE.md` maintenance

---

## Target State

### A) Metric Asset Metadata Baseline
Each metrics asset must have:
1. `description` (non-empty, meaningful)
2. `metadata["grain"]`
3. `metadata["unit"]`
4. `metadata["calculation_logic"]` (short readable explanation)

Recommended shape:
```python
@asset(
    group_name="metrics",
    description="Cycle Time for completed issues.",
    metadata={
        "grain": "issue",
        "unit": "days",
        "calculation_logic": MetadataValue.md(
            "Duration between work start and completion timestamps per issue."
        ),
    },
)
def calculate_cycle_time(...):
    ...
```

Notes:
- Do not require `dashboard_url`.
- Do not require `owner`.
- Keep metadata concise and stable across dashboard refactors.

### B) Metadata Quality Check
Add a metadata-focused asset check that fails when required metadata keys are missing.

Minimum validation:
1. Asset has non-empty `description`
2. Metadata contains `grain`, `unit`, `calculation_logic`
3. Values are non-empty strings or Dagster metadata values

This check must run with the rest of asset checks and be visible in Dagster UI.

### C) Database Schema Metadata
Schema semantics must live in SQL, not Markdown:
1. Add/maintain `COMMENT ON TABLE` and `COMMENT ON COLUMN` in English.
2. Prioritize critical objects first:
   - `metrics.fact_values`
   - `metrics.v_facts`
   - `metrics.calculations`
   - `metrics.definitions`
   - `metrics.dim_projects`
   - `metrics.dim_dates`
3. Expand to remaining objects iteratively.

### D) Migration + Schema Sync Rule
When DB schema changes:
1. Create Alembic migration in `db/migrations/versions/`.
2. Update the corresponding canonical SQL schema file in `db/schemas/*.sql`.
3. Include required comments for new/changed objects.

Migration without schema file update is considered incomplete.

---

## Execution Plan

### Phase 1 (Immediate)
1. Update top-priority metric assets with baseline metadata (`description`, `grain`, `unit`, `calculation_logic`).
2. Add metadata asset check and wire it in Dagster definitions.
3. Add missing `metrics.*` comments in canonical SQL schema location.

### Phase 2 (Short-term)
1. Extend baseline metadata to all assets in `pipelines/assets/metrics/`.
2. Normalize wording/style for units and grain names.
3. Ensure every schema object touched by recent migrations has comments.

### Phase 3 (Steady-state)
1. Enforce CI validation for metadata baseline and schema sync.
2. Keep changes incremental: each feature touching metrics or DB schema must include metadata updates in the same PR.

---

## Definition of Done
- [ ] 100% of assets in `pipelines/assets/metrics/` have non-empty `description`.
- [ ] 100% of metrics assets have `metadata.grain`, `metadata.unit`, `metadata.calculation_logic`.
- [ ] Metadata asset check exists and runs in Dagster.
- [ ] Critical `metrics.*` tables/views/columns have English SQL comments.
- [ ] Every schema-changing migration has matching updates in `db/schemas/*.sql`.

---

## Why This Works
- Low overhead: no new infrastructure.
- Less drift: metadata stays in code/SQL where changes actually happen.
- Clear enforcement: checks make metadata requirements explicit and testable.
