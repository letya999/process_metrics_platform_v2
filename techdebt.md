# Tech Debt

## TD-001: Incremental clean layer (C-6)
**Status:** Known / Not Started
All clean layer assets perform full re-scan of `raw_jira.*` on every run.
No watermark, no dlt `_dlt_load_id` range filter, no `WHERE updated_at > last_run_at`.
**Risk:** Runtime scales linearly with data. Hourly schedule breaks beyond ~50k issues.
**Resolution:** Implement per-asset high-watermark using `_dlt_load_id` or `fields__updated`.

## TD-002: Single-transaction-per-asset strategy (Architecture)
**Status:** Known / Not Started
Two conflicting patterns in codebase:
- `issues.py` — single commit at end (atomic)
- `supplementary.py` — two separate commits (partial write possible)
**Resolution:** Standardize: one `engine.begin()` (auto-commit on success) per asset. Never call `conn.commit()` manually except after deliberate checkpoint pattern.

## TD-003: Clean layer parallel run safety (C-3 partial)
**Status:** Partially fixed (TRUNCATE → DELETE in single tx)
The hourly metrics refresh job runs independently of the clean layer job. If clean layer
is mid-run, metrics compute on partially updated data.
**Resolution:** Add Dagster sensor that delays metrics refresh until clean layer finishes.

## TD-004: Issues ingestion load strategy (Raw Jira)
**Status:** Deferred / Not Started
Current `raw_jira.issues` extraction uses heavy payload and long re-read window by default.
Proposed changes were intentionally deferred:
- add config knobs for `expand` and rendered fields
- reduce default incremental lookback for daily runs
- add separate periodic backfill with larger lookback window
**Reason deferred:** functional concerns from product side about changing current extraction behavior.
**Resolution (future):** implement tunable daily-vs-backfill strategy after alignment on acceptable freshness/load tradeoff.

## TD-005: Universal Clean Layer - Multi-Source Abstraction (Architecture)
**Status:** Known / Not Started
Metrics read directly from `clean_jira.*`. Adding any second source (Linear, GitHub, Jira Server) requires a full refactor of the metrics layer. `IntegrationType` enum already contains `github`, `gitlab`, `linear`, `asana`, but pipelines for these sources will not work without changes to metrics. Jira-specific concepts (story points custom field, board columns as "done" signal) have leaked into `calculations/`.

**Root cause:** No intermediate layer between source-clean and metrics.

**Resolution:** Introduce a `universal` schema with four tables:
- `universal.work_items` - normalized issues/tasks/tickets (`status_category` always one of: todo / in_progress / done)
- `universal.iterations` - sprints, cycles, milestones
- `universal.transitions` - status change history (critical for lead time, CFD)
- `universal.workflow_states` - workflow definition / board columns

Add `platform.field_mappings` - per-project config for source field mapping (story points field name, done statuses).

Write an adapter asset per source (`pipelines/assets/jira/universal_adapter.py`) that writes into `universal.*`. Switch all `calculations/*.py` from `FROM clean_jira.*` to `FROM universal.*`.

**Files requiring refactor:** `calculations/velocity.py`, `lead_time.py`, `throughput.py`, `cycle_time_ext.py`, `cumulative_flow.py`, `aging.py`, `flow_dynamics.py`, `flow_efficiency.py`, `quality.py`, `sprint_health.py`, `estimation.py`, `commitment_resolver.py` (hardest - contains Jira-specific heuristics), all `assets/metrics/*.py`.

**Strategy:** incremental - Jira pipeline keeps running at every step. Adapter writes to `universal.*` in parallel with the existing clean layer; metrics are switched one at a time with verification.

**Impact:** once complete, adding a new source requires only raw layer + clean layer + adapter. Metrics and BI pack remain unchanged.
