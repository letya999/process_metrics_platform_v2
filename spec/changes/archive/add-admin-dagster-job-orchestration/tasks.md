# Implementation Tasks

1. [x] Add OpenAPI/pydantic schemas for admin job launch, run status, and progress payloads.
2. [x] Extend `DagsterClient` with run-details query (step stats + recent events).
3. [x] Add admin API endpoints: list jobs, launch job, get run details.
4. [x] Validate launch contract against current Dagster Definitions and remove invalid run config entries.
5. [x] Add dedicated Streamlit jobs page/section separate from metrics configuration tabs.
6. [x] Implement live polling UI with duration, step progress, and error/success rendering.
7. [x] Add/update unit tests for new API endpoints and Streamlit jobs UI.
8. [x] Run targeted tests for dagster client, admin API, and streamlit admin app.
