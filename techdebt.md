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
