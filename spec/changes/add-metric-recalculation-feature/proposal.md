# Proposal: New Metric Recalculation Feature in Admin Panel

## Why
Currently, users can only launch a full metrics refresh or a set of predefined jobs for individual metrics. There is no flexible way to select specific metrics or combinations of metrics to recalculate directly from the Admin UI. This feature will allow administrators to have more granular control over the recalculation process, saving time and resources by only recalculating what is necessary.

## What Changes
- **Admin API**: New endpoint `/admin/jobs/recalculate` that accepts a list of metrics to recalculate.
- **Admin Schema**: Update Pydantic models to support the new request and response structures.
- **Dagster Integration**: Logic to dynamically select Dagster assets based on user input and trigger a custom run.
- **Admin UI (Streamlit)**: A new section in the Admin panel with a multi-select component for metrics and a button to launch the recalculation.

## Impact
- **app/api/admin.py**: Addition of the new recalculation endpoint.
- **app/schemas/admin.py**: New schema for `AdminRecalculateRequest`.
- **app/services/dagster_client.py**: New method to trigger runs with specific asset selections.
- **streamlit_admin/app.py**: UI update to include the new feature.
- **pipelines/jobs/schedules.py**: (Optional) New job definition if a generic recalculation job is needed, otherwise dynamic asset selection will be used.
