# Plan: Convert loose SQL files to proper Alembic migrations

**Branch:** `fix/jira-pipeline-clean-layer-integrity`
**Goal:** Replace 8 ad-hoc SQL files in `db/migrations/` with proper versioned Alembic migrations. Delete the SQL files after.

---

## Context

The project uses Alembic for schema versioning (`db/migrations/versions/0001_*.py` → `0028_*.py`).
During Phase 1-5 remediation, 8 SQL files were created outside Alembic — they are untracked and may not be applied.

Current Alembic head: `0028` (revision `"0028"`, `down_revision = "0027"`)

---

## Files to CREATE

### `db/migrations/versions/0029_add_phase1_clean_jira_tables.py`

```
revision = "0029"
down_revision = "0028"
```

**upgrade()** — execute the following SQL via `op.execute()`:

```sql
-- labels
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

CREATE INDEX IF NOT EXISTS idx_cj_labels_project ON clean_jira.labels(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_labels_issue ON clean_jira.issue_labels(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_labels_label ON clean_jira.issue_labels(label_id);

-- worklogs
CREATE TABLE IF NOT EXISTS clean_jira.worklogs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    author_id uuid REFERENCES clean_jira.jira_users(id),
    time_spent_seconds int NOT NULL,
    started_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issue_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_cj_worklogs_issue ON clean_jira.worklogs(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_worklogs_author ON clean_jira.worklogs(author_id);
CREATE INDEX IF NOT EXISTS idx_cj_worklogs_started ON clean_jira.worklogs(started_at);

-- priorities
CREATE TABLE IF NOT EXISTS clean_jira.issue_priorities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

ALTER TABLE clean_jira.issues ADD COLUMN IF NOT EXISTS priority_id uuid REFERENCES clean_jira.issue_priorities(id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_priorities_project ON clean_jira.issue_priorities(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_priority ON clean_jira.issues(priority_id);

-- resolutions
CREATE TABLE IF NOT EXISTS clean_jira.issue_resolutions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

ALTER TABLE clean_jira.issues ADD COLUMN IF NOT EXISTS resolution_id uuid REFERENCES clean_jira.issue_resolutions(id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_resolutions_project ON clean_jira.issue_resolutions(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_resolution ON clean_jira.issues(resolution_id);
```

**downgrade():**
```sql
ALTER TABLE clean_jira.issues DROP COLUMN IF EXISTS resolution_id;
DROP TABLE IF EXISTS clean_jira.issue_resolutions;
ALTER TABLE clean_jira.issues DROP COLUMN IF EXISTS priority_id;
DROP TABLE IF EXISTS clean_jira.issue_priorities;
DROP TABLE IF EXISTS clean_jira.worklogs;
DROP TABLE IF EXISTS clean_jira.issue_labels;
DROP TABLE IF EXISTS clean_jira.labels;
```

---

### `db/migrations/versions/0030_add_users_view_and_schema_cleanup.py`

```
revision = "0030"
down_revision = "0029"
```

**upgrade():**

```sql
-- v_unique_users view
CREATE OR REPLACE VIEW clean_jira.v_unique_users AS
SELECT DISTINCT ON (external_id)
    id, project_id, external_id, display_name, created_at, updated_at
FROM clean_jira.jira_users
ORDER BY external_id, updated_at DESC;

-- drop raw_jira_staging schema (no longer needed)
DROP SCHEMA IF EXISTS raw_jira_staging CASCADE;

-- fix field_keys unique constraint (allow same name, different key)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'field_keys_project_id_name_key'
          AND conrelid = 'clean_jira.field_keys'::regclass
    ) THEN
        ALTER TABLE clean_jira.field_keys DROP CONSTRAINT field_keys_project_id_name_key;
    END IF;
END $$;
DROP INDEX IF EXISTS clean_jira.field_keys_project_id_name_key;
```

**downgrade():**
```sql
DROP VIEW IF EXISTS clean_jira.v_unique_users;
-- raw_jira_staging and field_keys constraint cannot be reliably reversed
```

---

### `db/migrations/versions/0031_add_external_id_indexes.py`

```
revision = "0031"
down_revision = "0030"
```

**IMPORTANT:** This migration must NOT use `CREATE INDEX CONCURRENTLY` because Alembic wraps migrations in transactions. Use regular `CREATE INDEX IF NOT EXISTS` without CONCURRENTLY.

**upgrade():**
```sql
CREATE INDEX IF NOT EXISTS idx_cj_issues_ext_id ON clean_jira.issues(external_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprints_ext_id ON clean_jira.sprints(external_id);
CREATE INDEX IF NOT EXISTS idx_cj_releases_ext_id ON clean_jira.releases(external_id);
CREATE INDEX IF NOT EXISTS idx_cj_jira_users_ext_id ON clean_jira.jira_users(external_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprint_changelog_sprint_id_field
    ON clean_jira.sprint_changelog(sprint_id, field_name, changed_at DESC);
```

**downgrade():**
```sql
DROP INDEX IF EXISTS clean_jira.idx_cj_issues_ext_id;
DROP INDEX IF EXISTS clean_jira.idx_cj_sprints_ext_id;
DROP INDEX IF EXISTS clean_jira.idx_cj_releases_ext_id;
DROP INDEX IF EXISTS clean_jira.idx_cj_jira_users_ext_id;
DROP INDEX IF EXISTS clean_jira.idx_cj_sprint_changelog_sprint_id_field;
```

---

## Files to DELETE (after creating Alembic versions)

Remove these 8 files from `db/migrations/`:
- `add_labels.sql`
- `add_worklogs.sql`
- `add_priorities.sql`
- `add_resolutions.sql`
- `add_unique_users_view.sql`
- `drop_raw_jira_staging.sql`
- `fix_field_keys_unique_constraint.sql`
- `add_external_id_indexes.sql`

---

## Validation

After creating the files, run:
```
uv run pytest tests/unit/test_jira_clean_assets_unit.py tests/unit/test_jira_clean.py -x -q
```
All 53 tests must pass (migration files don't affect unit tests, but verify no regressions).

Also verify the migration chain is valid (no DB connection needed for this check):
```
uv run alembic -c db/migrations/alembic.ini branches
```

## Important notes for implementation

1. Each migration file must follow the exact same structure as existing version files (see `0028_add_ttm_calculation_settings.py` as template)
2. Use `op.execute(text("..."))` — import `from sqlalchemy import text` at top of each file
3. The `DO $$ ... END $$` block in 0030 needs special care: use `op.execute(text(...))` with the full PL/pgSQL block as a string
4. Do NOT use f-strings in migration files
5. After file creation, verify the chain: 0028 → 0029 → 0030 → 0031

## Commit

After all files created and tests pass:
```
git add db/migrations/versions/0029_*.py db/migrations/versions/0030_*.py db/migrations/versions/0031_*.py
git rm db/migrations/add_labels.sql db/migrations/add_worklogs.sql db/migrations/add_priorities.sql db/migrations/add_resolutions.sql db/migrations/add_unique_users_view.sql db/migrations/drop_raw_jira_staging.sql db/migrations/fix_field_keys_unique_constraint.sql db/migrations/add_external_id_indexes.sql
git commit -m "refactor: convert ad-hoc SQL files to versioned Alembic migrations (0029-0031)"
```
