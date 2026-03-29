# Proposal: Admin Dagster Job Orchestration Page

## Why
Админам нужно запускать ETL-цепочки (`raw`, `clean`, `metrics`, `jira sync`) и видеть ход выполнения без открытия интерфейса Dagster. Сейчас в Streamlit Admin Studio нет отдельной страницы orchestration, а существующий sync flow покрывает только часть сценариев.

## What Changes
1. Add admin API for Dagster job orchestration:
- list supported jobs for admin UI;
- launch selected job from an allow-list;
- return run status, duration, step-level progress, and recent error events.

2. Extend Dagster GraphQL client with run-details query for step stats and recent events.

3. Add a dedicated Streamlit admin page/section for job orchestration:
- run buttons for `jira_sync_job`, `jira_raw_job`, `jira_clean_job`, `metrics_refresh_job`;
- live status polling;
- progress indicator;
- success/failure summary with errors.

4. Keep existing integrations/config tabs unchanged.

## Impact
- Admin operations become possible directly from Streamlit Admin Studio.
- Reduces dependency on Dagster web UI for routine runs.
- Adds explicit observability (status/progress/error/time) in admin workflow.
