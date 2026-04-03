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

## TD-006: Production hardening backlog ("по-взрослому")
**Status:** Deferred / Post-MVP
Postpone until OSS MVP is validated in internal company rollout.

Included scope:
- DORA metrics completion (Deployment Frequency, Lead Time for Changes end-to-end)
- Multi-tenancy (tenant isolation and access controls)
- DR/SLO program (backup+restore drills, SLO/SLI, alerting policies)
- Full observability stack (structured logs, metrics, tracing, actionable alerts)

## TD-007: Admin UX before first sync (Project catalog source-of-truth mismatch)
**Status:** Known / In Progress
Admin Studio currently builds multiple dropdowns from `clean_jira.projects`, while project onboarding is done in `platform.projects`. Before the first successful `jira_sync_job`, clean layer is empty, so:
- `Project Filter` shows only `All`
- Metrics catalog/commitment/settings screens look empty or misleading
- users think integration import failed even when `platform.projects` already has data

Related reliability issues observed in the same flow:
- API `create_integration` returned `500` on DB check-constraint violations instead of a user-actionable `409/422`
- Streamlit tabs could crash with `KeyError: None` when global scope required a source project but project list was empty

**Root cause:** UI/UX coupling to clean layer state for configuration screens that should be driven by platform configuration state.

**Resolution:** Make Admin Studio two-phase and explicit:
1. **Configuration phase (source: `platform.*`)**
   - Integrations, imported projects, active flags, and project filters should use `platform.projects` as primary source.
2. **Data-ready phase (source: `clean_jira.*`)**
   - Catalog-dependent selectors (boards/statuses/field keys) can require clean data, but must show a clear "sync required" state with CTA.

Implementation details:
- Add API endpoint(s) for onboarding health (per integration/project): imported/active/synced timestamps and row counts (`raw_jira.projects`, `clean_jira.projects`).
- In UI, if clean catalog is empty, show blocking banner with one-button action: "Run jira_sync_job now".
- Keep guards in Streamlit to avoid `KeyError`/empty-select crashes.
- Keep integration create/update aligned with DB token-storage constraints and return deterministic 4xx errors for operator mistakes.

**Impact:** onboarding becomes deterministic, fewer false "empty system" incidents, faster first successful sync in production.

## TD-008: Mixed-project sprint board scope vs project scope mismatch (Velocity/Sprint Health)
**Status:** Known / Not Started
For some Jira boards (notably `TWBACKEND`), sprint scope includes issues from multiple project keys on the same board. Jira sprint reports are board-scoped, but current platform aggregation is primarily project-scoped (`project_agg_id`), so metrics diverge from Jira in mixed sprints.

Observed effect in production:
- `TWWB` and `TWMOB` are close to Jira after SP-field fixes
- `TWBACKEND` still has large deltas on planned/completed SP for specific sprints
- root cause is mixed sprint composition, not only SP field mapping

**Resolution:** Add explicit board-scoped metric mode:
- introduce board-level dimensions/facts (or board slice) for sprint metrics
- calculate velocity/sprint-health on sprint issue set as seen by board scope
- keep project-scoped metrics in parallel (do not replace), make scope explicit in BI filters
- add validation job comparing board-scoped results against Jira sprint report API

**Impact:** allows 1:1 reconciliation with Jira for mixed boards while preserving current project analytics.

## TD-009: Reuse active/passive column mapping by shared column names across projects
**Status:** Known / Not Started
Flow-efficiency setup currently requires explicit per-project configuration and duplicates similar mappings for columns with the same semantic meaning (`In Progress`, `On review`, `Testing`, etc.).

**Resolution:** Add reusable mapping layer:
- global dictionary of column-name patterns -> active/passive bucket
- project-level overrides for exceptions
- dry-run preview to show resolved mapping before apply

**Impact:** faster onboarding of new projects and fewer manual config errors.

## TD-010: Finish metrics recalculation launch and schedule management from Admin UI
**Status:** Known / In Progress
Admin API/UI already supports manual launches for many jobs, but end-to-end operational flow is incomplete for schedule lifecycle management.

**Resolution:** complete full control surface in Admin:
- start/stop schedules and sensors
- run history + last success/failure visibility
- one-click rerun for failed jobs

**Impact:** operations can manage ETL/metrics lifecycle without direct Dagster CLI access.

## TD-011: Programmatic card/dashboard creation from Admin UI
**Status:** Known / Not Started
Dashboard/card provisioning is script-based and not fully exposed via Admin workflows.

**Resolution:** add Admin-managed BI provisioning:
- create/update cards and dashboards from templates
- bind dashboard filters and slices from UI
- idempotent apply with preview and diff

**Impact:** removes manual Metabase setup bottlenecks and improves reproducibility.

## TD-012: Unified user management for Admin UI and Metabase
**Status:** Known / Not Started
User provisioning is split across systems and not centrally governed.

**Resolution:** implement centralized user management:
- create/update/disable users for Admin + Metabase from one panel
- role mapping across systems
- audit trail for access changes

**Impact:** safer and faster access operations.

## TD-013: Admin UI migration to React with RBAC
**Status:** Known / Deferred
Current Streamlit admin is productive for MVP but limited for advanced role-based UI and large-scale operations.

**Resolution:** migrate Admin to React frontend + API-backed RBAC:
- role-permission model
- route and action guards
- granular feature flags by role

**Impact:** enterprise-ready admin experience and stronger access control.

## TD-014: SSO for Admin UI, Metabase, Dagster and related services
**Status:** Known / Deferred
Authentication is fragmented across platform components.

**Resolution:** introduce unified SSO:
- single identity provider integration (OIDC/SAML)
- token/session propagation across Admin, Metabase, Dagster endpoints
- consistent logout/session invalidation policy

**Impact:** lower auth friction and improved security posture.

## TD-015: Metric-level contextual tooltips/info hints
**Status:** Known / Not Started
Many metrics are opaque for non-technical users without embedded explanation of formula and interpretation.

**Resolution:** add metric help metadata and UI rendering:
- definition, formula, data source notes, caveats
- consistent tooltip/info panel in dashboard/admin

**Impact:** fewer support questions and more reliable metric interpretation.

## TD-016: AI assistant for platform guidance + Text2SQL
**Status:** Known / Research
No embedded assistant for user guidance and ad-hoc analytical questions.

**Resolution:** add in-product AI copilot:
- operational help for platform usage
- guarded Text2SQL for analytics queries
- query safety controls, scope restrictions, and audit logging

**Impact:** faster self-service analytics and reduced analyst load.

## TD-017: Multi-project commitment point mapping by shared names
**Status:** Known / Not Started
Commitment-point configuration is board/project-specific and difficult to align when equivalent stages exist across multiple projects.

**Resolution:** support shared commitment mapping:
- select by common column names across projects
- allow multi-project mapping sets in one rule
- keep project overrides for edge cases

**Impact:** consistent commitment logic and lower setup cost across portfolio boards.
