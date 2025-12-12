# Dagster Asset Testing Guide

This guide helps verify that all Dagster assets work correctly after MVP optimization.

## Asset Dependencies

```
raw_jira_data (dlt extraction)
    ↓
clean_jira_issues → check_no_orphan_issues (asset check)
clean_jira_projects
clean_jira_sprints → check_sprint_dates_valid (asset check)
clean_jira_status_changes
    ↓
refresh_metrics_views (materialize gold layer)
    ↓
Success ✅
```

## Pre-requisites

1. ✅ Docker containers running: `make docker-up`
2. ✅ Database initialized: `make migrate`
3. ✅ Jira credentials configured in `.env`
4. ✅ Code compiles: `python -m compileall app/ pipelines/`

## Testing Steps

### 1. Access Dagster UI
```bash
# Dagster should be running at:
open http://localhost:3000
```

### 2. Check Assets
In Dagster UI:
- Navigate to **Assets** tab
- You should see:
  - 📦 `jira_raw_data` (dlt source)
  - 🧹 `clean_jira_issues` (transformation)
  - 🧹 `clean_jira_projects`
  - 🧹 `clean_jira_sprints`
  - 🧹 `clean_jira_status_changes`
  - 🎯 `refresh_metrics_views` (materialization)

### 3. Materialize Assets Manually
```bash
# Option A: Via Dagster UI
# Click "Materialize" button on individual assets

# Option B: Via CLI
docker compose exec app dagster asset materialize \
  --select "clean_jira_issues" \
  --select "clean_jira_projects" \
  --select "clean_jira_sprints"

# Option C: Via job execution
docker compose exec app dagster job execute \
  -j jira_sync_job
```

### 4. Monitor Execution
- Watch the run in Dagster UI → Runs
- Check logs for errors
- Verify asset checks pass ✅

### 5. Verify Data in Database
```bash
# Check raw data was loaded
docker compose exec postgres psql -U postgres -d metrics -c \
  "SELECT count(*) FROM raw_jira.issues;"

# Check clean data was transformed
docker compose exec postgres psql -U postgres -d metrics -c \
  "SELECT count(*) FROM clean_jira.issues;"

# Check system project was created
docker compose exec postgres psql -U postgres -d metrics -c \
  "SELECT * FROM platform.projects WHERE id='00000000-0000-0000-0000-000000000001';"
```

## Expected Results

### MVP Schema
```
✅ platform.users (1 system user)
✅ platform.integration_types (7 types including jira_cloud)
✅ platform.tool_integrations (1 system integration)
✅ platform.projects (1 default Jira project)
✅ platform.audit_log (empty initially)
✅ clean_jira.projects (N from Jira)
✅ clean_jira.issues (N from Jira)
✅ clean_jira.sprints (N from Jira)
✅ metrics.mv_lead_time (materialized view)
✅ metrics.mv_velocity (materialized view)
✅ metrics.mv_throughput (materialized view)
```

### Removed for MVP
```
❌ external_tool_users (BI tool sync - add later)
❌ project_access (multi-user roles - add later)
❌ pipelines/pipeline_runs/pipeline_tasks (Prefect - using Dagster instead)
```

## Troubleshooting

### Asset fails with "ForeignKeyViolation"
**Cause:** Missing default Jira project
**Fix:** Run migration again
```bash
docker compose exec app alembic downgrade 0004_add_system_user
docker compose exec app alembic upgrade head
```

### dlt extraction fails
**Cause:** Missing or invalid Jira credentials
**Check:**
```bash
echo $JIRA_BASE_URL
echo $JIRA_USER_EMAIL
echo $JIRA_API_TOKEN
```

### Asset checks fail
**Cause:** Data integrity issues
**Debug:**
```bash
# View orphan issues
docker compose exec postgres psql -U postgres -d metrics -c \
  "SELECT i.id FROM clean_jira.issues i WHERE i.project_id NOT IN (SELECT id FROM clean_jira.projects);"
```

### Metrics views are stale
**Fix:** Refresh manually
```bash
docker compose exec postgres psql -U postgres -d metrics -c \
  "REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;"
```

## Success Indicators

✅ All assets show "Materialized" status in Dagster UI
✅ No asset checks failing
✅ Data appears in metrics views
✅ Metabase can connect and query data
✅ No database errors in logs

## Next Steps

After verification:
1. ✅ Load real Jira data via `jira_sync_job`
2. ✅ Configure Metabase dashboards
3. ✅ Set up scheduled syncs (cron jobs in Dagster)
4. ✅ Deploy to production

---

**Need help?** Check Dagster logs:
```bash
docker compose logs -f app | grep -i error
```
