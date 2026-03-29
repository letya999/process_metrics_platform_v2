# Implementation Tasks

1.  [ ] **Migration**: Create an Alembic migration to add `slice_rule_id` to:
    - `fact_velocity_slices`
    - `fact_throughput_slices`
    - `fact_backlog_growth_slices`
    - `fact_lead_time_slices`
    - `fact_time_to_market_slices`
    - `fact_flow_efficiency_slices`
    - `fact_work_item_aging_slices`
2.  [ ] **Utils Update**: Update `get_slice_rules` in `pipelines/calculations/slicing_utils.py` to include `id`.
3.  [ ] **Filter Logic**: Implement `filter_condition` handling in `apply_slicing` within `pipelines/calculations/slicing_utils.py`.
4.  [ ] **Asset Update**: Update individual metrics assets to ensure `slice_rule_id` is passed correctly to `write_table`.
5.  [ ] **Tests**: Update `tests/unit/test_slicing_utils.py` to verify `slice_rule_id` and `filter_condition` handling.
6.  [ ] **Validation**: Run the updated pipelines and check the database to confirm `slice_rule_id` is populated correctly.
