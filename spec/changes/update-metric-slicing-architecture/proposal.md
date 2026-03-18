# Proposal: Update Metric Slicing Architecture

## Why
The current slicing architecture relies on `slice_rule_name`, which is fragile when rules are renamed. Adding `slice_rule_id` ensures stable linkage to the configuration. Additionally, `filter_condition` in `metric_slice_rules` is currently ignored by the calculation logic, limiting the flexibility of slices (e.g., unable to exclude certain issue types from a "By Status" slice).

## What Changes
1.  **Database Schema**:
    - Add `slice_rule_id` column to all metrics slice tables (`metrics.fact_*_slices`).
    - Add foreign key constraints from `slice_rule_id` to `metrics.metric_slice_rules(id)`.
2.  **Calculation Logic (`slicing_utils.py`)**:
    - Include `id` (as `slice_rule_id`) in the `get_slice_rules` query.
    - Implement support for `filter_condition` using Polars to filter the source DataFrame before slicing.
    - Update `apply_slicing` to include `slice_rule_id` in the result DataFrame.
3.  **Metrics Assets**:
    - Update all metrics assets (Velocity, Throughput, Lead Time, etc.) to include `slice_rule_id` in their `write_table` calls or schema selection.

## Impact
- **Database**: 7-8 slice tables will be modified.
- **Data Integrity**: Historical data will be more robust against configuration changes.
- **Reporting**: BI tools can now join on stable IDs instead of strings.
- **Features**: Slicing becomes more flexible by supporting SQL-like filters.
