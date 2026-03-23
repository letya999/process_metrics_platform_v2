# Proposal: Refactor Advanced Metrics and Implement Dynamic Slicing

**Change ID**: refactor-advanced-metrics-slicing
**Author**: Gemini CLI
**Date**: 2026-03-22

## Why
The current `advanced.py` asset file combines multiple unrelated metrics (Aging and Flow Efficiency), making it difficult to maintain and scale. Furthermore, these metrics do not support dynamic slicing, which limits the analytical capabilities of the platform.

## What Changes
1. **Refactor `advanced.py`**: Split the `calculate_advanced_metrics` asset into two separate assets: `calculate_aging` and `calculate_flow_efficiency`.
2. **New Asset Files**:
   - Create `pipelines/assets/metrics/aging.py`
   - Create `pipelines/assets/metrics/flow_efficiency.py`
3. **Implement Slicing**: Update both new assets to use the `apply_slicing` pattern from `pipelines.calculations.slicing_utils`.
4. **Metadata Resolution**: Ensure `definition_id` and `calculation_id` are resolved correctly for both metrics.
5. **Cleanup**: Remove `pipelines/assets/metrics/advanced.py` once the new assets are verified.

## Impact
- **Dagster**: New assets `calculate_aging` and `calculate_flow_efficiency` will be available in the `metrics` group.
- **Database**: `metrics.fact_values` will now contain sliced data for Aging and Flow Efficiency if slice rules are enabled.
- **Maintainability**: Clear separation of concerns for different metric types.
