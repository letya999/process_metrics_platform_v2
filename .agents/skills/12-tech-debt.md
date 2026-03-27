---
name: tech-debt
description: Known technical debt items (TD-001 to TD-005) with risk levels, workarounds, and fix strategies. Read before touching affected areas.
triggers:
  - "tech debt"
  - "techdebt"
  - "TD-001"
  - "TD-002"
  - "TD-003"
  - "known issue"
  - "workaround"
context:
  - agent.md
---

# Skill: Working with Technical Debt

Known limitations of the platform. Before touching affected areas, read the relevant TD item.
Full tracker: `techdebt.md` at project root.

---

## TD-001: Clean Layer Full Re-Scan (OPEN)

**Area:** `pipelines/assets/jira/clean/*.py`
**Risk:** High at scale (>50k issues)

Every clean asset reads ALL of `raw_jira.*` on each run — no watermark, no incremental.

**What this means for you:**
- Do NOT attempt to add watermark logic to individual clean assets in isolation — it requires a coordinated change across all clean assets and a batch-ID tracking mechanism
- Do NOT optimize individual assets by filtering `WHERE _dlt_load_id > last_processed` — this creates inconsistency between related tables (e.g. issues and changelogs must be from the same batch)
- The hourly schedule is currently STOPPED — this is why. Enable it only after validating runtime with your data volume.

**Acceptable workaround:** Filter source data by `updated` timestamp from Jira API (pull only recently updated issues). This is done at the dlt level, not the clean level.

**If you're asked to fix TD-001:** The correct approach is a full project-level batch ID:
1. dlt writes `_dlt_load_id` per run
2. Clean assets record last processed `_dlt_load_id` in a watermark table
3. All clean assets in a run must use the SAME `_dlt_load_id` snapshot

---

## TD-002: Inconsistent Transaction Patterns (OPEN)

**Area:** `pipelines/assets/jira/clean/issues.py` vs `pipelines/assets/jira/clean/supplementary.py`

Two patterns exist:
- `issues.py`: one `engine.begin()` block — atomic ✓
- `supplementary.py`: multiple manual `conn.commit()` calls — partial write risk ✗

**What this means for you:**
- When adding a new clean asset, always use the `issues.py` pattern (single `engine.begin()`)
- Do not copy from `supplementary.py` as a template
- TD-002 will eventually be fixed by refactoring `supplementary.py` to use single transaction

**If you're asked to fix TD-002:** Refactor `supplementary.py` to wrap all operations in a single `engine.begin()` block. Verify that the data types match (no mixed commit semantics for the same table).

---

## TD-003: Metrics Refresh During Clean Layer Update (PARTIALLY FIXED)

**Area:** Schedule coordination between `jira_sync_job` and `metrics_refresh_job`

**Risk:** Metrics refresh reads from `clean_jira.*` while clean assets are mid-write. This can cause metrics to compute against partially-updated data.

**Status:** Schedules are both STOPPED by default. Partially mitigated by manual schedule control.

**Remaining gap:** If an operator enables both schedules and they overlap, inconsistent metrics are possible.

**If you're asked to fix TD-003:** Add a Dagster asset sensor that delays `metrics_refresh_job` until `jira_sync_job` completes. Use `RunStatusSensorContext` and `RunRequest` with `run_key` deduplication.

---

## TD-004: Jira Ingestion Load Strategy (DEFERRED)

**Area:** `pipelines/assets/jira/raw.py`

dlt pulls issues with a broad re-read window. For large Jira instances with complex JQL filters, this can hit Jira rate limits or timeout.

**Status:** Not being worked on. Deferred until scale requires it.

**If you're asked to fix TD-004:**
- Implement daily-only mode (only issues `updated >= today - 2 days`)
- Keep monthly backfill mode (full history, runs weekends)
- Control via `config/projects.yaml` per project: `sync_mode: daily | full`

---

## TD-005: In-Memory Auth (IMPLICIT, NOT IN TRACKER)

**Area:** `app/services/admin_auth.py`

Token store is a process-local dict. Resets on restart. Not multi-worker-safe.

**What this means for you:**
- Don't scale FastAPI to multiple workers or replicas without first replacing the token store
- If a user reports "I keep getting logged out", it's because the server restarted
- Adding uvicorn `--workers N` will cause each worker to have its own token store — tokens from worker A won't be valid on worker B

**If you're asked to fix this:** Replace `_TOKEN_STORE` with Redis-backed session store, or implement proper JWT (stateless tokens don't need a store).

---

## TD-006: bi/ Module Incomplete (IMPLICIT)

**Area:** `bi/providers/`

The `bi/providers/` directory is empty. `bi/main.py` is a stub.

**What this means for you:**
- Don't add features that depend on `BIProvider` implementations until at least one provider exists
- Metabase is configured separately via `scripts/setup_metabase.py` — not through the `bi/` module

**If you're asked to implement a BIProvider:** See `bi/provider_base.py` for the Protocol. Start with `MetabaseProvider` as it's already used (manually) in the project.

---

## Tracking New Tech Debt

When you introduce a known limitation, add it to `techdebt.md`:

```markdown
## TD-007: Description

**Area:** file/module
**Risk:** Low | Medium | High
**Status:** Open | Partially Fixed | Deferred

Brief description of the limitation.

**Workaround:** What to do in the meantime.

**Fix approach:** How to properly resolve it when prioritized.
```

Add a cross-reference in the relevant code file:
```python
# TD-007: This does not handle the case where X — see techdebt.md
```
