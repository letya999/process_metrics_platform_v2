# Metadata Management Strategy: Dagster-First Approach

## Overview
This project adopts a **Dagster-native Metadata Catalog** strategy. Following the "Simple Monolith" principle, we avoid heavy external tools (like DataHub or OpenMetadata) and leverage **Software-Defined Assets (SDA)** to serve as our primary data catalog, business glossary, and lineage tool.

## Core Principles
1. **Code as Documentation**: Metadata lives next to the code that produces the data.
2. **English Only**: All descriptions, metadata keys, and formulas must be in English (resolving audit issue C-9).
3. **Actionable Lineage**: Every metric must link to its visualization (Metabase) and its source.

---

## Implementation Plan

### Phase 1: Metric Asset Enrichment
Every asset in the `metrics` group must implement the following metadata structure:

#### Example Implementation
```python
@asset(
    group_name="metrics",
    description="Cycle Time: The time it takes for an issue to move from 'In Progress' to 'Done'.",
    metadata={
        "business_value": "Measures team speed and process efficiency.",
        "calculation_logic": MetadataValue.md("Detailed SQL or logic description here"),
        "unit": "Days",
        "dashboard_url": MetadataValue.url("http://localhost:3001/dashboard/5-cycle-time"),
        "sql_source": "metrics.v_facts where calc_code = 'cycle_time_days'"
    }
)
def calculate_cycle_time(context, ...):
    ...
```

### Phase 2: Documentation Migration
1. **Translate & Move**: Content from `METRICS_SCHEMA_DOCUMENTATION.md` (Russian) will be translated to English and moved into the `description` fields of respective Dagster assets.
2. **Deprecate**: Once migrated, the Russian documentation files will be deleted to avoid "stale artifact" confusion (audit issue C-10).

### Phase 3: Quality Transparency
Leverage `Asset Checks` to show the health of the catalog:
- Every metric must have at least one `Data Quality` check (e.g., no negative values, no nulls in critical fields).
- Check results must be visible in the Dagster Asset UI.

### Phase 4: Database-Native Schema Documentation
To support SQL-only users (Analysts, DBA) and BI tools (Metabase):
1. **SQL Comments**: Every table and column in `db/schemas/` must have a `COMMENT ON TABLE` and `COMMENT ON COLUMN` statement in English.
2. **Auto-Sync**: Explore automating the export of `description` fields from Dagster assets directly into PostgreSQL comments to maintain a single source of truth.
3. **Living Schema File**: Maintain an up-to-date `db/SCHEMA_REFERENCE.md` (or similar) that contains the full DDL with comments for LLM context and quick reference.

---

## Acceptance Criteria (Definition of Done)
- [ ] 100% of assets in `pipelines/assets/metrics/` have a non-empty `description`.
- [ ] Every Gold-layer metric has a `dashboard_url` metadata entry.
- [ ] No Russian language documentation remains in the root directory.
- [ ] Business formulas are documented using `MetadataValue.md` for readability in Dagster UI.
- [ ] "Freshness Policy" is defined for all Clean (Silver) and Metrics (Gold) assets.
- [ ] All critical tables/columns in `db/` have SQL comments mirroring Dagster descriptions.

## Why this approach?
- **Low Overhead**: Zero new containers or databases.
- **Developer Friendly**: No context switching between code and a separate catalog UI.
- **Single Source of Truth**: The code *is* the catalog. If the code changes, the catalog updates automatically.
