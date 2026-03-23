# Implementation Tasks: Refactor Advanced Metrics Slicing

1.  [ ] **Asset Creation: Aging**: Create `pipelines/assets/metrics/aging.py` with `calculate_aging` asset.
    - Implement `apply_slicing` pattern.
    - Resolve metadata for `aging_days`.
    - Use `aging_logic.calculate_work_item_aging_facts`.
2.  [ ] **Asset Creation: Flow Efficiency**: Create `pipelines/assets/metrics/flow_efficiency.py` with `calculate_flow_efficiency` asset.
    - Implement `apply_slicing` pattern.
    - Resolve metadata for `flow_active_days`, `flow_wait_days`, and `flow_efficiency_pct`.
    - Use `flow_logic.calculate_flow_efficiency_per_issue`.
3.  [ ] **Metadata Verification**: Confirm that `aging_days`, `flow_active_days`, `flow_wait_days`, and `flow_efficiency_pct` exist in `metrics.calculations`.
4.  [ ] **Asset Integration**: Ensure the new assets are properly registered in `pipelines/definitions.py`.
5.  [ ] **Cleanup**: Remove `pipelines/assets/metrics/advanced.py`.
6.  [ ] **Testing**: Verify that the new assets calculate both base and sliced facts.
7.  [ ] **Validation**: Run Dagster materializations for the new assets and check the database.
