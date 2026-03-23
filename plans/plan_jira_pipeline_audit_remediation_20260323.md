# Plan: Jira Pipeline Audit Remediation — 29 Issues
**Date:** 2026-03-23
**Source:** jira_pipeline_audit.md + hardcore audit report
**Total issues:** 29 (5 critical / 9 high / 9 medium / 6 low)
**Strategy:** Phases ordered by impact-to-effort ratio. Each phase is independently deployable.

---

## PHASE 1 — Critical Data Integrity (5 issues)
**Goal:** Fix broken data that is wrong RIGHT NOW. Nothing in phases 2-4 matters until these are fixed.
**Files:** `pipelines/assets/jira/clean.py`, `db/schemas/clean_jira_schema.sql`

---

### Task 1.1 — Fix `clean_jira_comments`: wrong source table, body column missing [C-1]

**Problem:**
`clean_jira_comments` looks for `issues__fields__comment__comments` (ADF format, no `body` column).
Should use `issues__rendered_fields__comment__comments` (HTML format, has `body text`).
Result: `clean_jira.comments = 0`, `comment_issues = 0`, despite 3854 raw comments.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_comments` (line ~1561):
  - Change `possible_tables` list to prioritize `issues__rendered_fields__comment__comments` FIRST, then fall back to `issues__fields__comment__comments`.
  - If resolved table is ADF format (no `body` column detected), log warning and skip silently instead of running broken SQL.
  - Add column existence check: before running INSERT, verify `body` column exists in the resolved table via `information_schema`.
  - Remove `.format(table=comment_table)` string interpolation. Use a whitelist of allowed table names; if not in whitelist, raise. This also fixes H-3 SQL injection risk.
  - The final SQL must use `c.body` only against the rendered table.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.comments` ≥ 3000 after pipeline run.
- `SELECT COUNT(*) FROM clean_jira.comment_issues` = `SELECT COUNT(*) FROM clean_jira.comments` (each comment linked to exactly one issue).
- No comment is linked to a non-existent issue (FK integrity maintained).

**Quality Checks:**
- Verify join chain: `issues__rendered_fields__comment__comments._dlt_root_id` → `raw_jira.issues._dlt_id` → `clean_jira.issues.external_id`. Run as assertion in test.
- Verify that the rendered table is selected, not the ADF table. Check in test by asserting SQL contains `rendered_fields`.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraComments::test_uses_rendered_fields_table_first` — mock `information_schema` to return only rendered table, assert SQL references `rendered_fields`.
- `TestCleanJiraComments::test_falls_back_gracefully_if_no_rendered_table` — mock both tables absent, assert returns `{"status": "skipped"}`.
- `TestCleanJiraComments::test_rejects_table_not_in_whitelist` — mock resolved table as `malicious_table`, assert raises `ValueError`.
- `TestCleanJiraComments::test_body_column_verified_before_insert` — mock rendered table exists but no `body` column, assert skips with warning.

---

### Task 1.2 — Fix `sprint_issues.is_active` for closed sprints [C-2]

**Problem:**
7728 records in `clean_jira.sprint_issues` have `is_active = TRUE` but belong to `status = 'closed'` sprints.
`is_active` is set at insert time but never updated when sprint is closed.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_sprint_issues` (line ~1213):
  - After the main UPSERT block, add a reconciliation UPDATE:
    ```sql
    UPDATE clean_jira.sprint_issues si
    SET is_active = FALSE
    FROM clean_jira.sprints s
    WHERE si.sprint_id = s.id
      AND s.status = 'closed'
      AND si.is_active = TRUE;
    ```
  - Log count of rows updated.
- Add this reconciliation step to the `clean_jira_sprint_issues` asset (not a separate asset — it must run atomically).

**Acceptance Criteria:**
- After run: `SELECT COUNT(*) FROM clean_jira.sprint_issues si JOIN clean_jira.sprints s ON s.id = si.sprint_id WHERE s.status = 'closed' AND si.is_active = TRUE` → 0.
- Active sprint issues (`status='active'`) with `is_active=TRUE` should represent the actual current sprint membership.
- Future sprint issues can have either value (depends on whether issue was pre-loaded).

**Quality Checks:**
- Run velocity calculation before and after the fix. Planned SP should not change (velocity uses historical sprint data, not `is_active`). If it changes, velocity calc has a bug that depends on `is_active`.
- Confirm no cascade effect on `sprint_issues_changelog`.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraSprintIssues::test_reconciles_closed_sprint_is_active_false` — mock DB with closed sprints and active issues, assert UPDATE is executed and touches correct rows.
- `TestCleanJiraSprintIssues::test_does_not_affect_active_sprint_issues` — mock active sprint with `is_active=TRUE`, assert they remain TRUE after reconciliation.

---

### Task 1.3 — Populate `parent_id` in `clean_jira_issues` [C-3]

**Problem:**
`clean_jira.issues.parent_id = NULL` for all 2634 issues despite 1569 having parents in raw.
The INSERT SQL in `clean_jira_issues` does not attempt to resolve parent.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_issues` (line ~289):
  - After the main UPSERT of issues (all parent references may not exist yet), add a second-pass UPDATE:
    ```sql
    UPDATE clean_jira.issues ci
    SET parent_id = parent_issue.id
    FROM raw_jira.issues ri
    JOIN clean_jira.issues parent_issue
        ON parent_issue.project_id = ci.project_id
        AND parent_issue.external_id = ri.fields__parent__id::text
    WHERE ci.external_id = ri.id::text
      AND ri.fields__parent__id IS NOT NULL
      AND ci.parent_id IS NULL;
    ```
  - For cross-project parents (39 issues): add a separate UPDATE without `project_id = ci.project_id` filter to resolve cross-project parents:
    ```sql
    UPDATE clean_jira.issues ci
    SET parent_id = parent_issue.id
    FROM raw_jira.issues ri
    JOIN clean_jira.issues parent_issue
        ON parent_issue.external_id = ri.fields__parent__id::text
    WHERE ci.external_id = ri.id::text
      AND ri.fields__parent__id IS NOT NULL
      AND ci.parent_id IS NULL;
    ```
  - Log: same-project resolved count, cross-project resolved count, unresolvable count (parent not yet in clean).

**Acceptance Criteria:**
- `SELECT COUNT(parent_id) FROM clean_jira.issues` ≥ 1569 after run.
- `SELECT COUNT(*) FROM clean_jira.issues WHERE parent_id IS NOT NULL` ≥ 1569.
- No self-referential parent (`parent_id = id`).
- All `parent_id` values reference existing rows in `clean_jira.issues` (FK maintained automatically).

**Quality Checks:**
- Verify Epic → Story → Task chain is resolvable: pick 3 known issues from raw with `fields__parent__id`, assert all 3 have `parent_id` set after run.
- Check for circular references (edge case): `WITH RECURSIVE` CTE to detect cycles in parent chain. Should return 0 rows.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraIssues::test_parent_id_resolved_same_project` — mock raw with issue A having parent B (same project), both in clean, assert UPDATE sets A.parent_id = B.id.
- `TestCleanJiraIssues::test_parent_id_resolved_cross_project` — mock raw with issue A (project X) having parent B (project Y), assert cross-project resolution pass sets A.parent_id.
- `TestCleanJiraIssues::test_parent_id_null_when_parent_not_in_clean` — parent exists in raw but not synced yet to clean, assert parent_id remains NULL (no crash).
- `TestCleanJiraIssues::test_no_self_referential_parent` — mock issue with parent pointing to itself, assert UPDATE skips it.

---

### Task 1.4 — Add `clean_jira_user_issue_roles` asset [C-4]

**Problem:**
`clean_jira.jira_user_issue_roles = 0`. No `@asset` exists to populate this table.
Raw data has: 2116 assignees, 2634 reporters, 2634 creators.

**Changes:**
- `pipelines/assets/jira/clean.py` — add new `@asset` function `clean_jira_user_issue_roles`:
  ```python
  @asset(
      group_name="jira_clean",
      deps=["clean_jira_issues", "clean_jira_jira_users"],  # ensure both are ready
      description="Populate user roles (assignee, reporter, creator) per issue",
      compute_kind="sql",
  )
  def clean_jira_user_issue_roles(context, database):
  ```
  - SQL: UPSERT into `clean_jira.jira_user_issue_roles` for each role type:
    ```sql
    INSERT INTO clean_jira.jira_user_issue_roles (user_id, issue_id, role_type, assigned_at)
    SELECT u.id, i.id, 'assignee'::clean_jira.user_role_type, now()
    FROM clean_jira.issues i
    JOIN raw_jira.issues ri ON ri.id::text = i.external_id
    JOIN clean_jira.jira_users u ON u.external_id = ri.fields__assignee__account_id
        AND u.project_id = i.project_id
    WHERE ri.fields__assignee__account_id IS NOT NULL
    ON CONFLICT (user_id, issue_id, role_type) DO NOTHING;
    ```
  - Repeat for `reporter` (fields__reporter__account_id) and `creator` (fields__creator__account_id).
  - Log counts per role type.
- Add `clean_jira_user_issue_roles` to asset exports in `pipelines/assets/jira/__init__.py`.
- Add asset to the job definition so it runs as part of jira_sync_job.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.jira_user_issue_roles WHERE role_type = 'assignee'` ≈ 2116.
- `SELECT COUNT(*) FROM clean_jira.jira_user_issue_roles WHERE role_type = 'reporter'` ≈ 2634.
- `SELECT COUNT(*) FROM clean_jira.jira_user_issue_roles WHERE role_type = 'creator'` ≈ 2634.
- No row where `user_id` or `issue_id` is NULL (NOT NULL constraints enforced).
- No duplicate `(user_id, issue_id, role_type)` tuples.

**Quality Checks:**
- Verify the same `(user, issue)` pair can have multiple roles (e.g., creator + reporter). This is valid.
- Check that `user_id` always resolves — if `jira_users` is missing a user, that role is simply not created (LEFT JOIN pattern, not INNER).

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraUserIssueRoles::test_asset_exists_and_is_decorated` — assert `clean_jira_user_issue_roles` is a Dagster asset with correct group_name and deps.
- `TestCleanJiraUserIssueRoles::test_populates_all_three_role_types` — mock DB, verify 3 separate INSERT statements are executed (one per role type).
- `TestCleanJiraUserIssueRoles::test_skips_null_account_ids` — mock raw with NULL assignee, assert assignee INSERT is skipped (WHERE clause tested).
- `TestCleanJiraUserIssueRoles::test_upsert_on_conflict_do_nothing` — mock conflict on existing row, assert no exception raised.

---

### Task 1.5 — Add `clean_jira_issue_relations` asset [C-5]

**Problem:**
`clean_jira.relation_issue_issues = 0`, `relation_issue_types = 0`.
Raw has 830 issuelinks. No asset exists for this data.

**Changes:**
- `pipelines/assets/jira/clean.py` — add two new `@asset` functions:
  1. `clean_jira_relation_issue_types`: populate relation types (blocks, relates to, duplicates, etc.)
     ```sql
     INSERT INTO clean_jira.relation_issue_types (project_id, external_id, name)
     SELECT DISTINCT p.id, il.type__id, il.type__name
     FROM raw_jira.issues__fields__issuelinks il
     JOIN raw_jira.issues ri ON il._dlt_parent_id = ri._dlt_id
     JOIN clean_jira.projects p ON ri.fields__project__id::text = p.external_id
     WHERE il.type__id IS NOT NULL
     ON CONFLICT (project_id, external_id) DO UPDATE SET name = EXCLUDED.name;
     ```
  2. `clean_jira_relation_issue_issues`: populate issue-to-issue links
     - Handle both `inward_issue__id` (blocked by) and `outward_issue__id` (blocks) directions.
     - Both source and target must exist in `clean_jira.issues`; silently skip cross-project links where target is not synced.
     ```sql
     INSERT INTO clean_jira.relation_issue_issues (relation_type_id, source_issue_id, target_issue_id)
     SELECT rt.id, source_i.id, target_i.id
     FROM raw_jira.issues__fields__issuelinks il
     JOIN raw_jira.issues ri ON il._dlt_parent_id = ri._dlt_id
     JOIN clean_jira.projects p ON ri.fields__project__id::text = p.external_id
     JOIN clean_jira.relation_issue_types rt ON rt.project_id = p.id AND rt.external_id = il.type__id
     JOIN clean_jira.issues source_i ON source_i.external_id = ri.id::text
     JOIN clean_jira.issues target_i ON target_i.external_id = COALESCE(il.outward_issue__id::text, il.inward_issue__id::text)
     ON CONFLICT (relation_type_id, source_issue_id, target_issue_id) DO NOTHING;
     ```
- Add both to `__init__.py` and job definition.
- Add `clean_jira_relation_issue_types` as dep of `clean_jira_relation_issue_issues`.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.relation_issue_types` ≥ 1 (at minimum "blocks" type).
- `SELECT COUNT(*) FROM clean_jira.relation_issue_issues` ≥ 100 (830 raw, some are cross-project).
- No orphaned relations (source or target issue_id not in `clean_jira.issues`).
- `SELECT COUNT(*) FROM clean_jira.relation_issue_issues WHERE source_issue_id = target_issue_id` = 0 (no self-links).

**Quality Checks:**
- Spot-check: pick a known blocking link from raw, verify it appears in `relation_issue_issues`.
- Verify inward vs outward direction is preserved correctly (not doubled).

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraRelations::test_relation_types_asset_exists` — assert asset decorated correctly.
- `TestCleanJiraRelations::test_relation_issues_asset_depends_on_types` — assert dep on `clean_jira_relation_issue_types`.
- `TestCleanJiraRelations::test_skips_links_with_no_target_in_clean` — mock target issue not in clean, assert INSERT skips (no FK violation).
- `TestCleanJiraRelations::test_handles_both_inward_outward_columns` — mock issuelinks with both inward and outward, assert both are attempted.

---

## PHASE 2 — High Priority Data Recovery (9 issues)
**Goal:** Recover all data that exists in raw but is lost before clean layer. Fix infrastructure risks.

---

### Task 2.1 — Drop `raw_jira_staging` ghost schema [H-1]

**Problem:**
Schema `raw_jira_staging` has 70 tables, 89 issues vs 2634 in `raw_jira`. Artifact of old migration. Zero references in code.

**Changes:**
- `db/migrations/` — create new migration file `drop_raw_jira_staging.sql`:
  ```sql
  -- Drop stale staging schema leftover from migration
  DROP SCHEMA IF EXISTS raw_jira_staging CASCADE;
  ```
- Verify no code references `raw_jira_staging` before applying.
- Run via `docker-compose exec postgres psql` or Alembic if tracked.

**Acceptance Criteria:**
- `SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'raw_jira_staging'` → 0 rows.
- No code references in codebase (`grep -r "raw_jira_staging" .` → 0 results).

**Quality Checks:**
- `grep -rn "raw_jira_staging" pipelines/ app/ tests/` returns nothing before dropping.

**Tests to add:**
- `tests/unit/test_jira_raw_unit.py::test_no_staging_schema_references` — `grep`-style test that scans Python files for `raw_jira_staging` string and asserts zero matches.

---

### Task 2.2 — Document `from_status_id = NULL` behavior, add guard in calculations [H-2]

**Problem:**
30.2% of `issue_status_changelog` rows have `from_status_id = NULL` (first transition, no previous status). This is correct for initial "Created → In Progress" transitions. But metrics that compute time-in-status must handle NULL explicitly.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_issue_status_changelog`: add comment explaining NULL means "issue created directly in this status".
- `pipelines/calculations/flow_efficiency.py` — verify `from_status_id IS NULL` rows are treated as "time starts at jira_created_at", not skipped.
- `pipelines/calculations/cycle_time_ext.py` — same verification.
- `pipelines/calculations/lead_time.py` — same.
- If any calculation silently skips NULL rows: fix by using `COALESCE(from_status_id, initial_status_sentinel_id)` or filtering explicitly.

**Acceptance Criteria:**
- All metric calculations produce identical or improved results after this fix.
- Calculation for a known issue with `from_status_id = NULL` first entry returns a valid (non-null) result.
- No metric uses raw `from_status_id IS NOT NULL` filter without explicit justification.

**Quality Checks:**
- Pick 5 issues where first changelog entry has `from_status_id = NULL`. Verify lead_time, flow_efficiency, cycle_time all compute for those issues without NULL result.

**Tests to add — `tests/unit/test_jira_clean.py`:**
- `TestStatusChangelog::test_null_from_status_is_first_transition` — assert that a row with `from_status_id = NULL` is valid and represents issue creation.
- `TestStatusChangelog::test_calculations_handle_null_from_status` — mock changelog with NULL from_status, verify flow_efficiency calc does not skip the issue.

---

### Task 2.3 — Replace `.format()` SQL interpolation with whitelist [H-3]

**Problem:**
`clean.py:1651`: `insert_sql = insert_sql_template.format(table=comment_table)`. `comment_table` comes from `information_schema` but the pattern is fragile and violates parameterized query principles.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_comments`:
  - Define `ALLOWED_COMMENT_TABLES = frozenset(["issues__rendered_fields__comment__comments", "issues__fields__comment__comments"])`.
  - After resolving `comment_table`, assert `comment_table in ALLOWED_COMMENT_TABLES`. Raise `ValueError` if not.
  - This was already required by Task 1.1 — consolidate into that task's implementation. Mark as fixed by 1.1.
- Grep entire `clean.py` for other `.format()` SQL patterns. Found: `link_query` at line ~1664 uses `f"{comment_table}"`. Fix same way.

**Acceptance Criteria:**
- `grep -n "\.format(" pipelines/assets/jira/clean.py` → 0 results (or documented exceptions with reason).
- All SQL strings use SQLAlchemy `text()` with `:param` binding or whitelist-validated table names.

**Quality Checks:**
- Run `ruff` or `bandit` scan on clean.py for S608 (SQL injection) violations.

**Tests to add:**
- Already covered in Task 1.1 test `test_rejects_table_not_in_whitelist`.

---

### Task 2.4 — Add retry logic for Jira API calls [H-4]

**Problem:**
`raw.py:114` — `requests.get()` without retry. HTTP 429 or 503 kills the entire pipeline.

**Changes:**
- `pipelines/assets/jira/raw.py`:
  - Add `tenacity` import (already in project deps, verify in `pyproject.toml`; add if missing).
  - Wrap all `requests.get()` calls with retry decorator:
    ```python
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

    @retry(
        retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def _get_with_retry(url, auth, params):
        response = requests.get(url, auth=auth, params=params)
        if response.status_code == 429:
            raise requests.HTTPError("Rate limited", response=response)
        response.raise_for_status()
        return response
    ```
  - Replace all `requests.get(...)` + `response.raise_for_status()` with `_get_with_retry(...)`.
  - For 429: extract `Retry-After` header and use as wait time if available.
- `pyproject.toml` — add `tenacity>=8.0` to dependencies if not present.

**Acceptance Criteria:**
- `grep -n "requests.get(" pipelines/assets/jira/raw.py` → 0 direct calls (all through `_get_with_retry`).
- Unit test simulates 2 x 429 then success → pipeline completes normally.
- On 5th consecutive error → raises exception (not infinite retry).

**Quality Checks:**
- `tenacity` version pinned with `>=8.0,<9.0`.

**Tests to add — `tests/unit/test_jira_raw_unit.py`:**
- `TestJiraRetry::test_retries_on_429_and_succeeds` — mock requests to return 429 twice then 200, assert 3 total calls, returns correct data.
- `TestJiraRetry::test_gives_up_after_5_attempts` — mock 6 consecutive errors, assert exception raised after 5 retries.
- `TestJiraRetry::test_uses_retry_after_header` — mock 429 with `Retry-After: 5` header, assert wait applied.
- `TestJiraRetry::test_passes_through_200_directly` — mock 200 immediately, assert called once.

---

### Task 2.5 — Add Labels to clean layer [H-5]

**Problem:**
1097 labels in `raw_jira.issues__fields__labels`. No clean table or asset.

**Changes:**
- `db/schemas/clean_jira_schema.sql` — add two new tables:
  ```sql
  CREATE TABLE IF NOT EXISTS clean_jira.labels (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
      name text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(project_id, name)
  );

  CREATE TABLE IF NOT EXISTS clean_jira.issue_labels (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
      label_id uuid NOT NULL REFERENCES clean_jira.labels(id) ON DELETE CASCADE,
      UNIQUE(issue_id, label_id)
  );
  ```
- `db/migrations/` — add `add_labels_tables.sql` migration.
- `pipelines/assets/jira/clean.py` — add new `@asset` function `clean_jira_labels`:
  - deps: `clean_jira_issues`
  - Step 1: UPSERT labels from `raw_jira.issues__fields__labels`:
    ```sql
    INSERT INTO clean_jira.labels (project_id, name)
    SELECT DISTINCT p.id, l.value
    FROM raw_jira.issues__fields__labels l
    JOIN raw_jira.issues ri ON l._dlt_parent_id = ri._dlt_id
    JOIN clean_jira.projects p ON ri.fields__project__id::text = p.external_id
    WHERE l.value IS NOT NULL AND l.value != ''
    ON CONFLICT (project_id, name) DO NOTHING;
    ```
  - Step 2: UPSERT `issue_labels` M2M links.
- Add to `__init__.py` exports and job definition.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.labels` ≥ 1 (at least some distinct labels).
- `SELECT COUNT(*) FROM clean_jira.issue_labels` ≈ 1097 (matches raw label count).
- No label name is NULL or empty string.
- Each `issue_labels` row references valid `issue_id` and `label_id`.

**Quality Checks:**
- Check `raw_jira.issues__fields__labels.value` column name — verify it's actually called `value` (check column list). If not, update query.
- Run `SELECT column_name FROM information_schema.columns WHERE table_schema='raw_jira' AND table_name='issues__fields__labels'` and align SQL.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraLabels::test_asset_exists_with_correct_deps` — asset has `clean_jira_issues` in deps.
- `TestCleanJiraLabels::test_deduplicates_label_names` — mock raw with same label on 2 issues, assert only one `labels` row inserted.
- `TestCleanJiraLabels::test_skips_empty_labels` — mock raw with empty string label, assert skipped.
- `TestCleanJiraLabels::test_creates_m2m_links` — mock 3 labels for 1 issue, assert 3 `issue_labels` rows.

---

### Task 2.6 — Add Worklogs to clean layer [H-6]

**Problem:**
26 worklogs in `raw_jira.issues__fields__worklog__worklogs`. No clean table or asset.

**Changes:**
- `db/schemas/clean_jira_schema.sql` — add new table:
  ```sql
  CREATE TABLE IF NOT EXISTS clean_jira.worklogs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
      author_id uuid REFERENCES clean_jira.jira_users(id),
      external_id text NOT NULL,
      time_spent_seconds int NOT NULL,
      started_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(issue_id, external_id)
  );
  CREATE INDEX IF NOT EXISTS idx_cj_worklogs_issue ON clean_jira.worklogs(issue_id);
  ```
- `db/migrations/` — add `add_worklogs_table.sql`.
- `pipelines/assets/jira/clean.py` — add new `@asset` function `clean_jira_worklogs`:
  - deps: `clean_jira_issues`, `clean_jira_jira_users`
  - Join chain: `issues__fields__worklog__worklogs._dlt_parent_id → raw_jira.issues._dlt_id → clean_jira.issues.external_id`
  - Verify column names: `time_spent_seconds`, `started`, `author__account_id` from `information_schema` before running.
- Add to `__init__.py` and job.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.worklogs` = 26.
- `time_spent_seconds > 0` for all rows.
- `issue_id` resolves for all rows.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraWorklogs::test_asset_exists` — decorated correctly.
- `TestCleanJiraWorklogs::test_maps_time_spent_correctly` — mock raw with `time_spent_seconds=3600`, assert clean row has same value.
- `TestCleanJiraWorklogs::test_null_author_allowed` — mock worklog with no author, assert NULL author_id row inserted without error.

---

### Task 2.7 — Fix user duplication: make `jira_users` globally unique by `external_id` [H-7]

**Problem:**
54 users duplicated across 2 projects (132 total vs 78 unique). Each project gets its own copy.
JOINs on `jira_users` by `external_id` without `project_id` produce Cartesian products.

**Decision:** Keep current `project_id` scoping (it's a FK design) but enforce that metrics queries always include `project_id` in joins. Add a view for global user lookups.

**Changes:**
- `db/views/` or `db/schemas/clean_jira_schema.sql` — add view:
  ```sql
  CREATE OR REPLACE VIEW clean_jira.v_unique_users AS
  SELECT DISTINCT ON (external_id)
      external_id,
      display_name,
      MIN(id) OVER (PARTITION BY external_id) as canonical_id
  FROM clean_jira.jira_users
  ORDER BY external_id, display_name;
  ```
- `pipelines/assets/jira/clean.py` — function `clean_jira_issues` (user sync block):
  - Add comment: "Users are intentionally per-project scoped. Use `v_unique_users` for cross-project user deduplication."
- `pipelines/calculations/` — audit all files that JOIN `clean_jira.jira_users`. Ensure all JOINs include `project_id` or explicitly use `DISTINCT ON (external_id)` if cross-project.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.v_unique_users` = 78 (matches unique count).
- No calculation SQL produces a Cartesian product due to user duplication.
- Existing metrics calculations produce identical results after this change.

**Tests to add — `tests/unit/test_jira_clean.py`:**
- `TestUserDeduplication::test_view_returns_unique_users` — mock 2 projects with same user external_id, assert view returns 1 row.
- `TestUserDeduplication::test_project_scoped_join_returns_correct_count` — JOIN with project_id filter, assert no cartesian product.

---

### Task 2.8 — Add Priority to clean layer [H-8]

**Problem:**
Priority data exists in raw (5 values across 2634 issues). No clean table or asset.

**Changes:**
- `db/schemas/clean_jira_schema.sql` — add tables:
  ```sql
  CREATE TABLE IF NOT EXISTS clean_jira.priorities (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      external_id text NOT NULL UNIQUE,
      name text NOT NULL UNIQUE,
      icon_url text,
      display_order int,
      created_at timestamptz NOT NULL DEFAULT now()
  );
  ```
  - Note: priorities are global in Jira (not per-project), so no `project_id` FK.
  - Add `priority_id uuid REFERENCES clean_jira.priorities(id)` column to `clean_jira.issues` table.
  - Add index: `CREATE INDEX IF NOT EXISTS idx_cj_issues_priority ON clean_jira.issues(priority_id);`
- `db/migrations/` — `add_priorities_table.sql` (includes ALTER TABLE issues ADD COLUMN priority_id).
- `pipelines/assets/jira/clean.py` — add `@asset` function `clean_jira_priorities`:
  - UPSERT priorities from raw.
  - After priorities exist: UPDATE `clean_jira.issues.priority_id` by joining raw.
- Add as dep of `clean_jira_issues` (must run before or in same transaction).

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.priorities` = 5 (Medium, High, Highest, Low, Lowest).
- `SELECT COUNT(*) FROM clean_jira.issues WHERE priority_id IS NOT NULL` = 2634 (all issues have priority).
- No NULL `priority_id` after full pipeline run.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraPriorities::test_creates_5_priority_levels` — mock 5 distinct priorities in raw, assert 5 inserted.
- `TestCleanJiraPriorities::test_updates_issue_priority_id` — mock issues with priority, assert `priority_id` column updated.
- `TestCleanJiraPriorities::test_priority_is_global_not_per_project` — assert no `project_id` column in priorities table schema.

---

### Task 2.9 — Add Resolution to clean layer [H-9]

**Problem:**
`fields__resolution__name` and `fields__resolution__id` exist in raw (2429 resolved issues). No clean table.

**Changes:**
- `db/schemas/clean_jira_schema.sql` — add table:
  ```sql
  CREATE TABLE IF NOT EXISTS clean_jira.resolutions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      external_id text NOT NULL UNIQUE,
      name text NOT NULL UNIQUE,
      description text,
      created_at timestamptz NOT NULL DEFAULT now()
  );
  ```
  - Add `resolution_id uuid REFERENCES clean_jira.resolutions(id)` to `clean_jira.issues`.
- `db/migrations/` — `add_resolutions_table.sql`.
- `pipelines/assets/jira/clean.py` — add `@asset` function `clean_jira_resolutions`:
  - UPSERT from `raw_jira.issues` `fields__resolution__id`, `fields__resolution__name`, `fields__resolution__description`.
  - Then UPDATE `clean_jira.issues.resolution_id`.
- `clean_jira_resolutions` should run before/alongside `clean_jira_issues` update of resolution_id.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.resolutions` = 2 (Done, Canceled).
- `SELECT COUNT(*) FROM clean_jira.issues WHERE resolution_id IS NOT NULL` ≈ 2429.
- Issues with `jira_resolved_at IS NULL` should have `resolution_id IS NULL`.

**Tests to add — `tests/unit/test_jira_clean_assets_unit.py`:**
- `TestCleanJiraResolutions::test_creates_resolution_entries` — mock raw with 2 resolutions, assert both inserted.
- `TestCleanJiraResolutions::test_links_resolution_to_issues` — mock issue with resolution, assert `resolution_id` set on `clean_jira.issues`.
- `TestCleanJiraResolutions::test_unresolved_issues_have_null_resolution` — mock issue with NULL resolution, assert `resolution_id` stays NULL.

---

## PHASE 3 — Schema & Medium Issues (9 issues)

---

### Task 3.1 — Remove hardcoded platform UUID [M-1]

**Problem:**
`platform_project_id = "00000000-0000-0000-0000-000000000001"` in `clean.py:35`.
Non-scalable for multi-tenant/multi-instance setups.

**Changes:**
- `pipelines/assets/jira/clean.py`:
  - Replace hardcoded UUID with lookup:
    ```sql
    SELECT id FROM platform.projects
    WHERE name = :project_name
    LIMIT 1
    ```
  - Source `project_name` from config (projects.yaml) or env `PLATFORM_PROJECT_NAME`.
  - Create a shared helper `_get_platform_project_id(conn, project_key) -> UUID` to avoid repetition.
  - If project not found: raise `RuntimeError` with actionable message.
- `config/schema.py` — add `platform_project_name` field to project config schema.

**Acceptance Criteria:**
- `grep -n "00000000-0000-0000-0000-000000000001" pipelines/` → 0 results.
- With `platform_project_name` set in config, pipeline resolves UUID dynamically.

**Tests:**
- `TestCleanJiraProjects::test_resolves_platform_project_id_dynamically` — mock DB returning UUID, assert no hardcoded string used.
- `TestCleanJiraProjects::test_raises_if_platform_project_not_found` — mock DB returning nothing, assert RuntimeError.

---

### Task 3.2 — Fix hierarchy_level mapping: use `hierarchyLevel` metadata [M-2]

**Problem:**
`ILIKE '%epic%'` pattern determines hierarchy level. Fragile for custom issue types.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_issue_types`:
  - Add `fields__issuetype__hierarchy_level` to the raw data check.
  - Check if column `fields__issuetype__hierarchy_level` exists in `raw_jira.issues`.
  - If it exists, use numeric mapping:
    ```sql
    CASE
        WHEN r.fields__issuetype__hierarchy_level > 0 THEN 'epic'
        WHEN r.fields__issuetype__hierarchy_level = 0 THEN 'story'
        WHEN r.fields__issuetype__hierarchy_level < 0 THEN 'subtask'
        ELSE 'task'
    END
    ```
  - If column doesn't exist (older Jira versions), fall back to current ILIKE logic with a warning log.

**Acceptance Criteria:**
- `SELECT hierarchy_level, name FROM clean_jira.issue_types` shows correct mapping for known types.
- ILIKE fallback still passes all existing tests.

**Tests:**
- `TestCleanJiraIssueTypes::test_uses_hierarchy_level_column_when_available` — mock column exists, assert numeric mapping used.
- `TestCleanJiraIssueTypes::test_falls_back_to_ilike_when_no_hierarchy_column` — mock column absent, assert ILIKE used.

---

### Task 3.3 — Add Full Sync mechanism for ghost issues [M-3]

**Problem:**
dlt incremental merge by `id` doesn't remove deleted Jira issues. Ghost records accumulate.

**Changes:**
- `pipelines/assets/jira/raw.py` — add optional full sync mode:
  - Add env var `JIRA_FULL_SYNC=true` trigger.
  - In full sync: fetch ALL issues without `updated >=` filter. After successful load, do cleanup:
    ```python
    # Delete raw_jira issues whose IDs are NOT in the latest fetched batch
    # Use a temporary table approach
    ```
  - Actually simpler: add `@asset` `jira_ghost_cleanup` that runs separately (weekly schedule):
    - Fetches all current Jira issue IDs for all configured projects.
    - Deletes from `raw_jira.issues` WHERE `id::text NOT IN (fetched_ids)`.
    - Cascades to clean via FK.
- `pipelines/jobs/schedules.py` — add weekly schedule for ghost cleanup.

**Acceptance Criteria:**
- Ghost cleanup job exists in Dagster definitions.
- After simulated delete (remove issue from raw manually), cleanup job removes it from clean too.
- FK CASCADE ensures `clean_jira.issues` row is deleted when `raw_jira.issues` row is deleted.

**Tests:**
- `TestGhostCleanup::test_cleanup_job_exists_in_definitions` — assert job in Dagster defs.
- `TestGhostCleanup::test_cleanup_identifies_deleted_issues` — mock Jira returning 10 issues, raw has 12, assert 2 deleted.

---

### Task 3.4 — Limit API fields to reduce memory and raw schema bloat [M-4]

**Problem:**
`fields=*all` + `expand=changelog,renderedFields` fetches everything. 100+ raw tables, OOM risk.

**Changes:**
- `pipelines/assets/jira/raw.py` — function `get_issues`:
  - Define a whitelist of fields:
    ```python
    JIRA_ISSUE_FIELDS = [
        "summary", "description", "issuetype", "status", "priority",
        "assignee", "reporter", "creator", "created", "updated",
        "resolutiondate", "resolution", "parent", "subtasks", "issuelinks",
        "comment", "worklog", "labels", "fixVersions", "customfield_10020",  # sprint
        "customfield_10016",  # story points (estimate)
        "customfield_10028",  # story points (actual)
    ]
    ```
  - Replace `"fields": "*all"` with `"fields": ",".join(JIRA_ISSUE_FIELDS)`.
  - Keep `expand=changelog` (needed for status tracking), remove `renderedFields` from expand — fetch rendered comments separately only when needed.
  - Add env var `JIRA_FIELDS_OVERRIDE` to allow customization without code change.
- Add comment documenting why each field is included.

**Acceptance Criteria:**
- API request params no longer contain `fields=*all`.
- After re-sync with limited fields, all existing metrics still compute correctly.
- Raw schema does NOT grow with new `customfield_XXXXX` child tables on next sync.

**Tests:**
- `TestJiraRawSource::test_issues_resource_uses_field_whitelist` — mock get_issues call, assert `params["fields"]` doesn't contain `*all`.
- `TestJiraRawSource::test_fields_override_env_var_works` — set env var, assert it's used.

---

### Task 3.5 — Handle duplicate field key names [M-5]

**Problem:**
5 field names exist twice in `clean_jira.field_keys` (one per project).
JOIN by `name` without `project_id` → duplicates.

**Changes:**
- `pipelines/assets/jira/clean.py` — function `clean_jira_field_keys`:
  - Remove the `UNIQUE(project_id, name)` conflict as the driver and instead allow rename (update name when external_key matches but name differs).
  - Add warning log when same `external_key` has different `name` across projects.
- `db/schemas/clean_jira_schema.sql`:
  - Change `UNIQUE(project_id, name)` to just `UNIQUE(project_id, external_key)`. Remove the name uniqueness constraint — field names CAN be the same across projects.
  - Add migration to drop the old unique constraint.
- All calculation queries that JOIN `field_keys` by `name`: add `AND fk.project_id = i.project_id` to JOIN condition.

**Acceptance Criteria:**
- `SELECT name, COUNT(*) FROM clean_jira.field_keys GROUP BY name HAVING COUNT(*) > 1` returns 0 after fixing constraint (since now scoped per project, duplicates are valid and expected).
- All calculations produce correct results.

**Tests:**
- `TestFieldKeys::test_allows_same_name_in_different_projects` — insert same field name for 2 projects, assert no conflict raised.
- `TestFieldKeys::test_calculations_join_field_keys_with_project_scope` — assert all calculation SQL includes `project_id` in field_keys join.

---

### Task 3.6 — Auto-detect sprint custom field ID [M-6]

**Problem:**
`customfield_10020` hardcoded in 4+ places. Different Jira instances may use different IDs.

**Changes:**
- `pipelines/assets/jira/clean.py` — add helper function `_detect_sprint_field_id(conn) -> str`:
  ```python
  def _detect_sprint_field_id(conn: Connection) -> str:
      """Detect the sprint custom field ID from raw_jira.fields table."""
      result = conn.execute(text("""
          SELECT id FROM raw_jira.fields
          WHERE schema__custom = 'com.pyxis.greenhopper.jira:gh-sprint'
          LIMIT 1
      """)).scalar()
      return result or "customfield_10020"  # fallback to known default
  ```
- Replace all hardcoded `customfield_10020` references with `sprint_field_id = _detect_sprint_field_id(conn)`.
- `pipelines/assets/jira/raw.py` — JIRA_ISSUE_FIELDS list (from Task 3.4): also use detection there, or keep `customfield_10020` as fallback with comment.

**Acceptance Criteria:**
- `grep -n "customfield_10020" pipelines/assets/jira/clean.py` → 0 hardcoded occurrences (only in helper fallback).
- With a mocked different sprint field ID in `raw_jira.fields`, detection returns the new ID.

**Tests:**
- `TestSprintFieldDetection::test_detects_from_raw_fields_table` — mock DB with sprint field having custom schema, assert detected correctly.
- `TestSprintFieldDetection::test_falls_back_to_default_if_not_found` — mock DB with no sprint field, assert returns `customfield_10020`.

---

### Task 3.7 — Cross-project parent resolution for 39 issues [M-7]

**Problem:**
39 issues have parents in different Jira projects. Same-project-only parent lookup misses them.
Already partially addressed in Task 1.3, but needs explicit documentation and test.

**Changes:**
- Task 1.3 already implements the two-pass resolution. This task adds:
  - Log how many cross-project parents were resolved.
  - If cross-project parent is not synced (project not configured), log warning with the foreign project key.
  - Add `fields__parent__key` column lookup: if `fields__parent__id` doesn't resolve, try lookup by `external_key`.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.issues WHERE parent_id IS NOT NULL AND project_id != (SELECT project_id FROM clean_jira.issues p WHERE p.id = parent_id)` shows cross-project parents are resolved.

**Tests:**
- `TestCrossProjectParent::test_resolves_parent_from_different_project` — mock 2 projects, issue A (proj 1) has parent in proj 2, assert resolved.
- `TestCrossProjectParent::test_warns_on_unsynced_project_parent` — parent project not configured, assert warning logged.

---

### Task 3.8 — Fix `release_changelog` asset: verify and repair [M-8]

**Problem:**
`clean_jira.release_changelog = 0` despite `releases = 208`. Asset likely exists but has a bug.

**Changes:**
- Read `clean_jira_release_changelog` asset code in `clean.py` (line ~2017 area).
- Identify why it produces 0 rows. Likely: joins the changelog items table looking for `Fix Version` field changes, but the field name or table structure differs.
- Fix the field name detection (may be `Fix Version/s`, `fixVersions`, etc.).
- Add diagnostic: if 0 rows returned, log count of raw changelog items with fix version fields found.

**Acceptance Criteria:**
- `SELECT COUNT(*) FROM clean_jira.release_changelog` > 0 after fix.
- Only version date/name changes are recorded (not sprint changes, etc.).

**Tests:**
- `TestCleanJiraReleaseChangelog::test_detects_fix_version_field_variations` — test all known field name variants.
- `TestCleanJiraReleaseChangelog::test_produces_rows_when_changelog_has_version_changes` — mock changelog with version change, assert row inserted.

---

### Task 3.9 — Investigate and fix `sprint_changelog` sparsity [M-9]

**Problem:**
Only 4 rows in `sprint_changelog` for 161 sprints. Asset may be incorrectly tracking changes.

**Changes:**
- Read `clean_jira_sprint_changelog` asset code (~line 2017 in clean.py).
- Identify: is this intentionally sparse (only close events) or a bug?
- If bug: fix to capture all sprint property changes (name, dates, goal) from Jira Sprint changelog (separate Jira Agile API endpoint if needed).
- If intentional design (only close events): document clearly and add comment.

**Acceptance Criteria:**
- Clear documentation of what sprint_changelog captures.
- If it's a bug: `SELECT COUNT(*) FROM clean_jira.sprint_changelog` > 4 after fix.

**Tests:**
- `TestCleanJiraSprintChangelog::test_captures_sprint_close_events` — mock sprint close, assert row added.
- `TestCleanJiraSprintChangelog::test_captures_sprint_date_changes` — mock sprint date update, assert row added (if applicable).

---

## PHASE 4 — Architecture & Low Priority (6 issues)

---

### Task 4.1 — Add data quality checksum layer [L-2]

**Problem:**
No row count verification between raw and clean layers. Silent data loss goes undetected.

**Changes:**
- `pipelines/assets/metrics/` or new `pipelines/assets/jira/quality_checks.py` — add asset `jira_data_quality_report`:
  - Runs after full clean sync.
  - Checks: `raw_issues_count == clean_issues_count`, `raw_sprints_count == clean_sprints_count`, etc.
  - Emits Dagster asset checks or metadata with actual counts.
  - Raises `DagsterError` if delta > threshold (e.g., >5% discrepancy).
- Use existing `@asset_check` pattern (already used in `clean.py`).

**Acceptance Criteria:**
- Asset check `jira_data_quality_report` runs after clean layer.
- If raw_issues != clean_issues, check FAILS in Dagster.
- Asset check appears in Dagster UI.

**Tests:**
- `TestJiraDataQuality::test_check_fails_when_raw_clean_count_differs` — mock raw=100, clean=50, assert check fails.
- `TestJiraDataQuality::test_check_passes_when_counts_match` — mock equal counts, assert passes.

---

### Task 4.2 — Fix `pg_temp` schema leaks [L-4]

**Problem:**
16 stale `pg_temp` schemas indicate connection leaks.

**Changes:**
- `pipelines/resources/database.py` — review SQLAlchemy engine pool settings:
  - Add `pool_pre_ping=True` to detect broken connections.
  - Add `pool_recycle=3600` to recycle stale connections.
  - Ensure all `engine.connect()` calls use context manager (already done in most places, verify all).
- `pipelines/assets/jira/clean.py` — verify all `conn.commit()` calls happen inside `with engine.connect() as conn:` blocks. Missing commits leave transactions open → temp schemas.

**Acceptance Criteria:**
- After running pipeline, `SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name LIKE 'pg_temp%'` stays at ≤ 2 (at most one per active connection).

**Tests:**
- `TestDatabaseResource::test_engine_uses_pool_pre_ping` — assert engine created with `pool_pre_ping=True`.
- `TestDatabaseResource::test_connection_uses_context_manager` — assert all callers use `with engine.connect()`.

---

### Task 4.3 — Secrets management: move credentials out of `.env` [L-5]

**Problem:**
Real Jira API token, DB passwords, JWT secrets in `.env`. Accessible to anyone with shell access.

**Changes:**
- `README.md` / internal docs — add section on proper secrets management (Docker secrets, Vault, env injection).
- `.env.example` — ensure this exists with placeholder values only.
- `pipelines/assets/jira/raw.py` and `app/` — verify no secrets are logged (e.g., `context.log.info(f"Using token: {api_token}")` patterns).
- Add `scripts/check_secrets.sh` — pre-commit hook or CI check that greps for known secret patterns in `.env` if committed accidentally.
- Optional: integrate `python-dotenv` with `python-decouple` for validated env loading with typed defaults.

**Acceptance Criteria:**
- `grep -n "ATATT3xFf" .` → 0 results (no token in tracked files).
- `.env` remains in `.gitignore`.
- `grep -rn "api_token\|password\|secret" pipelines/assets/jira/raw.py` → only variable references, not literal values.

**Tests:**
- `TestSecretsLeak::test_no_api_token_logged` — mock context.log.info, run raw pipeline with mock token, assert token value not in any log call.

---

### Task 4.4 — Drop `raw_jira_staging` ghost schema (migration) [H-1 → already in 2.1]

*(Merged with Task 2.1)*

---

### Task 4.5 — Add `is_active` lifecycle management [L-3]

**Problem:**
`sprint_issues.is_active` not updated when sprint closes. Responsibility unclear.
*(Core fix already in Task 1.2. This task adds lifecycle for future sprints.)*

**Changes:**
- `pipelines/assets/jira/clean.py` — `clean_jira_sprint_issues`:
  - Reconciliation UPDATE already added in Task 1.2.
  - Also handle: when a sprint transitions `active → closed` in current run, update `is_active = FALSE` for all its issues.
  - Add comment: "is_active=TRUE means issue is currently assigned to this sprint AND sprint is not closed."
- `db/schemas/clean_jira_schema.sql` — add comment to `is_active` column definition explaining semantics.

**Acceptance Criteria:**
*(Already defined in Task 1.2)*

**Tests:**
*(Already defined in Task 1.2)*

---

### Task 4.6 — Document and enforce parameterized query standard [L-6 + H-3]

**Problem:**
Massive SQL strings in Python. `.format()` interpolation. Hard to test, maintain, and audit.

**Changes:**
- `pipelines/assets/jira/clean.py` — extract all SQL strings into module-level constants:
  ```python
  _SQL_UPSERT_PROJECTS = """
  INSERT INTO clean_jira.projects ...
  """
  ```
  - This is a refactor, NOT a logic change. SQL content stays identical.
- Add `ruff` rule `S608` to `pyproject.toml` linting section with `# noqa: S608` removed from current usages (fix them instead).
- Add `bandit` to dev dependencies for security scanning.
- `Makefile` — add `make lint-security` target: `bandit -r pipelines/ -ll`.

**Acceptance Criteria:**
- `grep -rn "\.format(" pipelines/assets/jira/clean.py` → 0 (or documented exceptions).
- `bandit -r pipelines/ -ll` → 0 HIGH severity issues.

**Tests:**
- `tests/unit/test_jira_clean.py::TestSQLInjectionPrevention::test_no_format_interpolation_in_sql` — scan clean.py AST for f-string SQL patterns, assert 0.

---

## PHASE 5 — Data Model Improvements (deferred)
**Goal:** Improvements that require schema migrations and coordination.

---

### Task 5.1 — Numeric external_id indexes [L-1]
- Where Jira IDs are always numeric (issue id, sprint id): add functional index `CREATE INDEX ON clean_jira.issues ((external_id::bigint))` for faster joins.
- Keep column type as TEXT (Jira API returns text) but optimize join paths.

### Task 5.2 — Closure table for deep hierarchy [#10]
- Add `clean_jira.issue_hierarchy_paths` closure table.
- Populate from `parent_id` chain via recursive CTE.
- Enables Epic-level metric aggregation.

### Task 5.3 — Unified blockings table [#11]
- Create `clean_jira.issue_blockings` that unions `relation_issue_issues` (blocks type) + future `issue_comment_blockings`.
- Requires Task 1.1 and Task 1.5 to be complete first.

### Task 5.4 — SCD Type 2 for sprints [#15]
- Track full sprint history (not just close event).
- Requires Jira Agile API `/rest/agile/1.0/sprint/{id}` polling.

---

## Summary: Execution Order

```
Phase 1 (P0 - Fix Now):
  1.1 comments table fix + SQL injection
  1.2 sprint is_active reconciliation
  1.3 parent_id population
  1.4 user issue roles asset
  1.5 issue relations assets

Phase 2 (P1 - Data Recovery, run after Phase 1 deploy):
  2.1 drop raw_jira_staging
  2.2 null from_status_id documentation + calc guards
  2.3 (merged into 1.1)
  2.4 retry logic
  2.5 labels
  2.6 worklogs
  2.7 user dedup view
  2.8 priorities + schema change
  2.9 resolution + schema change

Phase 3 (P2 - Schema & Medium):
  3.1 remove hardcoded UUID
  3.2 hierarchy level fix
  3.3 ghost cleanup mechanism
  3.4 limit API fields
  3.5 field key name constraint fix
  3.6 auto-detect sprint field
  3.7 (covered in 1.3)
  3.8 release changelog fix
  3.9 sprint changelog investigation

Phase 4 (P3 - Architecture):
  4.1 data quality checksum asset
  4.2 pg_temp leaks / connection pool fix
  4.3 secrets management
  4.5 is_active lifecycle (merged with 1.2)
  4.6 SQL parameterization standard

Phase 5 (P4 - Deferred):
  5.1 numeric external_id indexes
  5.2 closure table
  5.3 unified blockings
  5.4 SCD Type 2 sprints
```

## Files Modified Summary

| File | Phases |
|------|--------|
| `pipelines/assets/jira/clean.py` | 1, 2, 3, 4 |
| `pipelines/assets/jira/raw.py` | 2, 3 |
| `pipelines/assets/jira/__init__.py` | 1 |
| `db/schemas/clean_jira_schema.sql` | 2, 3 |
| `db/migrations/` (new files) | 2, 3 |
| `db/views/` (new view) | 2 |
| `pipelines/resources/database.py` | 4 |
| `pipelines/jobs/schedules.py` | 3 |
| `config/schema.py` | 3 |
| `pyproject.toml` | 2, 4 |
| `Makefile` | 4 |
| `tests/unit/test_jira_clean_assets_unit.py` | 1, 2, 3 |
| `tests/unit/test_jira_raw_unit.py` | 2 |
| `tests/unit/test_jira_clean.py` | 2, 3 |

## Test Count by Phase

| Phase | New Unit Tests | New Integration Tests |
|-------|---------------|-----------------------|
| 1 | 16 | 5 |
| 2 | 22 | 3 |
| 3 | 14 | 2 |
| 4 | 6 | 1 |
| **Total** | **58** | **11** |
