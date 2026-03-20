# Implementation Tasks: Migrate All Metric Assets to GLMS

1.  **Infrastructure: Metric Registry & DB Write**:
    *   [ ] Create `pipelines/utils/metric_registry.py` (`get_calculation_id`, `get_project_agg_id`, `resolve_unit_field`).
    *   [ ] Update `pipelines/utils/polars_db.py` with `write_fact_values` function (ADBC + idempotent DELETE/INSERT).
    *   [ ] Create `pipelines/utils/commitment_resolver.py` for rule-based start/end column lookup.
    *   [ ] Add tests for infrastructure utils.
2.  **Asset Migration: Velocity**:
    *   [ ] Update `pipelines/assets/metrics/velocity.py` to write 4 calculation types to `fact_values`.
    *   [ ] Use `units` table to resolve story points fields dynamically.
    *   [ ] Add `@asset_check`.
3.  **Asset Migration: Flow Metrics (Lead Time, TTM, Advanced)**:
    *   [ ] Update `pipelines/assets/metrics/lead_time.py` (use `commitment_resolver`, write `lead_time_days` + timestamps).
    *   [ ] Update `pipelines/assets/metrics/time_to_market.py` (write `ttm_days`).
    *   [ ] Update `pipelines/assets/metrics/advanced.py` (write `aging_days`, `flow_active_days`, `flow_wait_days`, `flow_efficiency_pct`).
    *   [ ] Add `@asset_check`s.
4.  **Asset Migration: Aggregate Metrics (Throughput, CFD, Backlog)**:
    *   [ ] Update `pipelines/assets/metrics/throughput.py` (write `throughput_count` with week grain).
    *   [ ] Update `pipelines/assets/metrics/cumulative_flow.py` (write `cfd_count` with `board_column` entity, no slices).
    *   [ ] Update `pipelines/assets/metrics/backlog_growth.py` (write 8 calculations).
    *   [ ] Add `@asset_check`s.
5.  **Validation**:
    *   [ ] Materialize all metric assets via Dagster.
    *   [ ] Verify data in `metrics.v_facts` view.
    *   [ ] Run existing test suite and fix assertions (pointing to new tables/views).
