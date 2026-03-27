# Proposal: Admin Studio for Metrics Configuration

## Why
The project already stores metric logic in database-driven metadata (`commitment_rules`, `calculation_settings`, `units`, `slice_rules`), but there is no complete admin UX/API to manage these settings safely. This causes manual SQL work, missing configuration, and metric gaps.

## What Changes
1. Add secured admin API endpoints for:
- Authentication for admin users.
- Catalog loading (projects, boards, statuses, custom fields, clean_jira schema map).
- Contract-driven configuration metadata for calculations.
- CRUD + batch operations for `commitment_rules`, `calculation_settings`, `units`, and `slice_rules`.
- Validation endpoint to detect missing/invalid config by project/calculation.

2. Add a Streamlit Admin Studio:
- Login/password auth.
- Shared component-driven layout with reusable controls.
- Fast configuration flows for contracts, units, commitment points, settings, and slices.

3. Deploy admin UI as a separate Docker image/service in compose stacks.

## Impact
- Removes direct SQL dependency for routine metric configuration.
- Improves consistency via contract-driven forms and validation.
- Adds secure access boundary for admin operations.
- Keeps architecture modular by separating API and Streamlit runtime containers.
