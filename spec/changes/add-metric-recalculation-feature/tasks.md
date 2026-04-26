# Implementation Tasks: Metric Recalculation Feature

1. [API] Create `AdminRecalculateRequest` in `app/schemas/admin.py` with a list of metric codes or job names.
2. [API] Add `/admin/jobs/recalculate` endpoint in `app/api/admin.py` to handle selected metrics.
3. [Service] Update `app/services/dagster_client.py` with `trigger_asset_run` method to support arbitrary asset selections.
4. [Service] Update `app/services/dagster_client.py` to map user-friendly metric names to Dagster asset keys or job names.
5. [UI] Update `streamlit_admin/client.py` to include a method for the new recalculate endpoint.
6. [UI] Implement a new section in `streamlit_admin/app.py` for selecting metrics to recalculate.
7. [UI] Add a confirmation dialog and progress tracking for the recalculation job.
8. [Test] Add unit tests for the new API endpoint and Dagster client method.
9. [Integration] Verify the full flow from selecting metrics in the UI to triggering a run in Dagster.
