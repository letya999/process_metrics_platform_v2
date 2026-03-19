# Proposal: Migrate All Metric Assets to GLMS (Phase 1 & 2)

**Change ID**: migrate-to-glms-assets
**Scope**: Infrastructure Layer & All Metric Assets Migration

## Why
After seeding the foundational metadata for the Generic Long Metric Store (GLMS), we need to update our Dagster assets to write into the unified `fact_values` table instead of the old wide tables. This migration will enable unified BI reporting, easier scaling of new metrics, and improved performance through ADBC/COPY protocol. Migrating all assets ensures a clean break from the old schema and allows us to deprecate the old wide tables.

## What Changes
1.  **Infrastructure (utils)**:
    *   `pipelines/utils/metric_registry.py`: New module to resolve calculation IDs, project IDs, and units from the database.
    *   `pipelines/utils/commitment_resolver.py`: New module to resolve commitment points (start/end columns) dynamically based on rules instead of hardcoded strings.
    *   `pipelines/utils/polars_db.py`: Enhanced `write_fact_values` function with ADBC support and idempotent DELETE+INSERT logic.
2.  **Asset Migrations (All Metrics)**:
    *   `velocity.py`: Rewrite to 4 calculation types (`planned_sp`, `completed_sp`, `planned_count`, `completed_count`).
    *   `lead_time.py`: Use `commitment_resolver`, output `lead_time_days` with `event_start_at`/`event_end_at`.
    *   `throughput.py`: Output `throughput_count` with weekly grain.
    *   `cumulative_flow.py`: Output `cfd_count` using `board_column` as `entity_type` (no slicing).
    *   `backlog_growth.py`: Output 8 calculation types (size, created, resolved, net_growth, avg_age, stale_count, oldest_days, stale_pct).
    *   `time_to_market.py`: Output `ttm_days`.
    *   `advanced.py`: Add `aging_days` and `flow_efficiency` (active, wait, pct) logic.
3.  **Asset Checks**:
    *   Add `@asset_check` for all migrated assets to verify row counts, absence of NULL values, and data integrity in `fact_values`.

## Impact
*   **Performance**: Bulk inserts will be 10-50x faster across the entire pipeline.
*   **Storage**: Data for ALL metrics will now reside in `metrics.fact_values`.
*   **Metabase**: The `v_facts` view will become the single source of truth for all dashboards.
*   **Deprecation**: Paves the way to drop old `fact_*` tables in a future cleanup migration.
