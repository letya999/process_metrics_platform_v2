---
name: clean-layer-jira
description: Clean (Silver) layer normalization from raw_jira to clean_jira schema. Strict FK dependency order and single-transaction per asset.
triggers:
  - "clean layer"
  - "clean_jira"
  - "normalization"
  - "clean asset"
  - "silver"
  - "jira normalization"
context:
  - agent.md
  - .agents/skills/02-database-patterns.md
  - .agents/skills/12-tech-debt.md
---

# Skill: Clean Layer (Jira Normalization)

The clean layer transforms raw Jira data from `raw_jira` schema into normalized relational tables in `clean_jira` schema.

---

## Responsibilities

Clean layer does NOT calculate metrics. It only:
- Normalizes raw JSON/flat structures into typed relational tables
- Resolves foreign keys between entities (issues → statuses, sprints → issues)
- Applies Jira-specific business rules (status category mapping, hierarchy levels)
- Handles multi-instance Jira setups (one platform.project per Jira project key)

---

## Asset Dependency Order (CRITICAL)

Must materialize in this order due to FK constraints:

```
raw_jira_data
 └─ clean_jira_projects          (requires: platform.projects exists)
     ├─ clean_jira_issue_types
     ├─ clean_jira_issue_statuses
     ├─ clean_jira_priorities
     ├─ clean_jira_resolutions
     └─ clean_jira_issues         (requires all dimension assets above)
         ├─ clean_jira_sprints
         │   └─ clean_jira_sprint_issues
         │       ├─ clean_jira_sprint_issues_changelog
         │       └─ clean_jira_issue_status_changelog
         ├─ clean_jira_boards
         │   └─ clean_jira_board_columns
         ├─ clean_jira_releases
         │   └─ clean_jira_release_issues
         ├─ clean_jira_field_keys
         │   └─ clean_jira_field_values
         │       └─ clean_jira_field_value_changelog
         └─ clean_jira_users
             └─ clean_jira_user_issue_roles
```

The `jira_ghost_cleanup` asset runs independently and only via manual trigger.

---

## Transaction Pattern (MANDATORY)

Every clean asset must use a single `engine.begin()` per operation. Never split into multiple commits.

```python
def _upsert_issue_statuses(engine: Engine, project_id: str, statuses: list[dict]) -> None:
    with engine.begin() as conn:
        # DELETE old for this project, then INSERT fresh
        conn.execute(
            text("DELETE FROM clean_jira.issue_statuses WHERE project_id = :pid"),
            {"pid": project_id},
        )
        conn.execute(
            text("""
                INSERT INTO clean_jira.issue_statuses (id, project_id, jira_status_id, name, category)
                VALUES (:id, :project_id, :jira_id, :name, :category)
            """),
            statuses,
        )
    # Commits here. Rolls back entirely on exception.
```

---

## Status Category Mapping

Jira statuses have categories. This project maps them to a strict enum:

| Jira category name | `issue_status_category` enum value |
|---|---|
| `"To Do"` | `to_do` |
| `"In Progress"` | `in_progress` |
| `"Done"` | `done` |

Unknown categories default to `in_progress`. Do not add new enum values without a migration.

```python
CATEGORY_MAP = {
    "To Do": "to_do",
    "In Progress": "in_progress",
    "Done": "done",
}
category = CATEGORY_MAP.get(jira_category_name, "in_progress")
```

---

## Issue Hierarchy Levels

```python
HIERARCHY_MAP = {
    "epic": "epic",
    "story": "story",
    "task": "task",
    "sub-task": "subtask",
    "bug": "task",        # Bugs are task-level
    "improvement": "task",
}
```

Unknown types default to `"task"`. Level determines which metrics include the issue (e.g. TTM only counts `story` level by default).

---

## Table-Exists Check

Always check if raw_jira tables exist before querying:

```python
from pipelines.assets.jira.clean._utils import table_exists

if not table_exists(engine, "raw_jira", "issues"):
    logger.warning("raw_jira.issues does not exist yet — run raw_jira_data first")
    return
```

This prevents asset failure during first-time setup when raw layer hasn't been populated yet.

---

## system@metrics.local User

There is a special system user in `platform.users`:
- email: `system@metrics.local`
- Used for: integration ownership when no real user is set up

**Never delete this user.** Foreign keys in `platform.tool_integrations` reference it. The `0004_seed_system_user` migration creates it.

---

## Sprint Issues: `is_active` Flag

`clean_jira.sprint_issues.is_active` — whether the sprint was active at the time of the last sync. Not historical.

For historical sprint membership, use `clean_jira.sprint_issues_changelog` which records `added_at` / `removed_at` events.

Velocity calculation uses `is_active = true` for "planned" scope and `removed_at IS NULL AND added_at < sprint.complete_date` for "completed" scope.

---

## Board Columns vs Statuses

`clean_jira.board_columns` — columns as shown on the Jira board (e.g. "In Progress", "Code Review", "Done")
`clean_jira.board_column_statuses` — maps each board column to one or more Jira statuses

This mapping is critical for commitment rule resolution (which column = "work started", which = "done").

---

## Ghost Cleanup Asset

`jira_ghost_cleanup` removes orphan rows in clean_jira when issues are deleted from Jira:
- Runs only via `jira_ghost_cleanup_job`
- Schedule defined: Sundays 2 AM UTC (`0 2 * * 0`) — but the schedule is STOPPED by default
- To activate: enable the schedule in Dagster UI (`jira_ghost_cleanup_job` → Schedules → Enable)
- Without enabling, the asset only runs on manual trigger — it will not fire automatically
- Safe to skip — just leaves stale rows, doesn't break calculations

Do not add cleanup logic to regular clean assets. Ghost cleanup is separate.

---

## Full Re-Scan (TD-001)

Every clean asset reads ALL of `raw_jira.*` on each run. There is no incremental/watermark logic.

This is a known limitation (TD-001). Do not attempt to add watermark logic unless you understand the full impact:
- The clean layer must be consistent at a point in time
- Partial watermark updates break FK integrity
- Fix requires a project-level design change (batch ID tracking)

---

## Adding a New Clean Asset

Template:

```python
@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues"],    # declare all upstream
    compute_kind="python",         # almost always python
    description="...",
)
def clean_jira_my_table(database: DatabaseResource) -> None:
    engine = database.get_engine()

    if not table_exists(engine, "raw_jira", "my_source_table"):
        return

    raw_df = read_table(engine, "raw_jira.my_source_table")

    if raw_df.is_empty():
        return

    # Transform...
    clean_rows = [...]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM clean_jira.my_table WHERE ..."), ...)
        conn.execute(text("INSERT INTO clean_jira.my_table ..."), clean_rows)
```

Export from `pipelines/assets/jira/clean/__init__.py` and add to `pipelines/definitions.py`.
