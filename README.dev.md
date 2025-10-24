# Local Dev: Prefect + DLT Jira Loader

## Prereqs
- Docker + docker-compose
- `.env` in repo root with strong secrets (use `make gen-env`)

Minimal vars:
- POSTGRES_PASSWORD=...
- REDIS_PASSWORD=...
- PREFECT_WORK_POOL=default (optional)
- PREFECT_WORK_QUEUE=default (optional)

## Start core
```bash
make up-core
```
This starts postgres, redis, Prefect server, two workers (`prefect-worker`, `dlt_jira_worker`) and a one-shot `prefect-deploy-init` that registers deployments.

Check health:
- Prefect UI: http://localhost:4200
- DB debug: `make debug-db`

## Add Jira integration secret
We keep only secret references in DB. Real tokens are in env.

Option A (quick local):
- Insert tool integration row (stub): use `platform.tool_integrations` via psql.
- Set two env vars before `docker-compose up`:
  - `INTEGRATION_SECRET_REF_<tool_integration_id>=JIRA_API_TOKEN__ACME`
  - `JIRA_API_TOKEN__ACME=<actual_token>`

Also provide `JIRA_INSTANCE_URL` and `JIRA_USER_EMAIL` via env or per-project credentials.

## Trigger a run
- Prefect UI → Deployments → `jira-sync-manual-<env>` → Run
- Or CLI inside worker: `prefect deployment run 'jira_sync_flow/jira-sync-manual-<env>' --param config=...`

Config example (JSON):
```json
{
  "project_uuids": ["11111111-1111-1111-1111-111111111111"],
  "dataset_name": "raw_jira_cloud_dlt"
}
```

## DLT real load
Set in worker env (compose already sets default 0):
- `DLT_ENABLE_REAL_RUN=1`

## Check data
- Raw schema: `raw_jira_cloud_dlt` (DLT-managed)
- Optional legacy checkpoints disabled by default; enable via `ENABLE_LEGACY_CHECKPOINTS=1`.
- Pipeline run summaries are tracked in-memory in tests; DB upsert placeholder logs during init.

## Troubleshooting
- Ensure `PREFECT_WORK_POOL` matches `--pool` in worker commands (compose sets both).
- `prefect deployment ls` inside any Prefect image should show two deployments.
- Re-register deployments: `make deploy-jira`.
