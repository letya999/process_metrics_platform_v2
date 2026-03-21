# Plan: Metrics Expansion — 21 New Calculations
**Date:** 2026-03-21
**Branch:** metrics-expansion-and-calculation-unification
**Spec:** METRICS_EXPANSION.md (22 entries, 21 implemented — `defect_density_by_type` #10 is a parameterized variant that shares infrastructure)

---

## Context & Architecture Rules

### Existing Schema (DO NOT MODIFY existing tables, only add/extend)
- `metrics.definitions` — metric group codes
- `metrics.grains` — time/entity granularity
- `metrics.calculations` — calc_code registry (calc_code must be unique)
- `metrics.units` — display units per project
- `metrics.fact_values` — generic long-form store (THE single fact table)
  - Columns: id, metric_id, project_agg_id, time_id, value, entity_type, entity_id,
    event_start_at, event_end_at, slice_rule_id, slice_value, commitment_rule_id,
    settings_id, context_json (JSONB), created_at, updated_at
- `metrics.calculation_settings` — parameterized settings per calculation (already exists from 0023)
  - Columns: id, project_id (nullable), target_calculation_id, settings_type, settings_json (JSONB), enabled
- `metrics.v_facts` — view joining all dimensions (already includes settings_id, context_json)

### Clean Jira Tables Available
- `clean_jira.sprints` — sprint metadata (id, iteration_id, project_id, name, start_date, end_date, state)
- `clean_jira.issues` — issue metadata (id, issue_key, project_id, created_at, updated_at, issue_type_id, parent_id, story_points or via field_values)
- `clean_jira.sprint_issues` — junction (sprint_id, issue_id)
- `clean_jira.sprint_issues_changelog` — scope changes (sprint_id, issue_id, action='added'|'removed', change_time)
- `clean_jira.issue_status_changelog` — status transitions (issue_id, from_status_id, to_status_id, change_time)
- `clean_jira.board_columns` — columns with position (id, board_id, name, position, status_ids array)
- `clean_jira.boards` — (id, project_id)
- `clean_jira.field_keys` — custom field definitions (id, field_key, field_name)
- `clean_jira.field_values` — current field values (issue_id, field_key_id, value)
- `clean_jira.field_value_changelog` — historical field changes (issue_id, field_key_id, old_value, new_value, change_time)
- `clean_jira.issue_types` — (id, name)
- `clean_jira.projects` — (id, key, name)

### Existing Utility Functions to Reuse
- `pipelines/utils/metric_registry.py`: `get_calculation_id()`, `get_definition_id()`, `get_project_agg_id()`, `resolve_unit_field()`
- `pipelines/utils/polars_db.py`: `read_table()`, `write_fact_values()`
- `pipelines/calculations/slicing_utils.py`: `get_slice_rules()`, `apply_slicing()`
- `pipelines/calculations/commitment_resolver.py`: `load_commitment_rules_for_calc()`, `resolve_rule_from_cache()`, `get_done_column_ids()`
- `pipelines/calculations/velocity.py`: `determine_story_points_at_date()` — REUSE this function for SP lookups

### Idempotency Keys in write_fact_values
- Sprint-grain: `(metric_id, project_agg_id, time_id)` where time_id = sprint_start YYYYMMDD
- Issue-grain: `(metric_id, project_agg_id, time_id, entity_id)` — note: current write_fact_values may need entity_id-aware upsert, verify and extend if needed
- Day-grain (burndown/activation): `(metric_id, project_agg_id, time_id, entity_id)` where entity_id=iteration_id

---

## Phase 1: Database Migration (file: `db/migrations/versions/0026_add_expanded_metrics.py`)

```
revision = "0026"
down_revision = "0025"
```

### 1.1 New grain: `project`
```sql
INSERT INTO metrics.grains (grain_code, description)
VALUES ('project', 'One row per project (release/version scope)')
ON CONFLICT (grain_code) DO NOTHING;
```

### 1.2 New unit: `ratio`
```sql
INSERT INTO metrics.units (project_id, unit_code, display_symbol)
VALUES (NULL, 'ratio', 'x')
ON CONFLICT DO NOTHING;
```

### 1.3 New definitions (7)
```sql
INSERT INTO metrics.definitions (metric_code) VALUES
('sprint_health'),
('flow_dynamics'),
('quality'),
('delivery'),
('waste'),
('estimation'),
('cycle_time')
ON CONFLICT (metric_code) DO NOTHING;
```

### 1.4 New calculations (22 total)

Map each calc_code to definition + grain + unit:

| calc_code | definition | grain | unit | uses_commitment_points |
|---|---|---|---|---|
| sprint_added_issues_count | sprint_health | sprint | issues | false |
| sprint_added_sp_sum | sprint_health | sprint | story_points | false |
| sprint_removed_issues_count | sprint_health | sprint | issues | false |
| sprint_removed_sp_sum | sprint_health | sprint | story_points | false |
| sprint_spillover_count | sprint_health | sprint | issues | false |
| sprint_burndown_remaining_sp | sprint_health | day | story_points | false |
| activation_velocity_pct | sprint_health | day | percent | true |
| field_value_sprint_pct | sprint_health | sprint | percent | false |
| unestimated_closed_count | sprint_health | sprint | issues | true |
| daily_status_entry_count | flow_dynamics | day | issues | false |
| field_change_count | flow_dynamics | sprint | issues | false |
| input_flow_weekly | throughput | week | issues | true |
| defect_density_by_type | quality | sprint | ratio | false |
| backflow_column_rate | quality | sprint | percent | true |
| release_burnup_scope_sp | delivery | project | story_points | false |
| release_burnup_done_sp | delivery | project | story_points | true |
| issue_lifetime_days | cycle_time | issue | days | false |
| cycle_time_custom | cycle_time | issue | days | true |
| cancellation_rate_weekly | waste | week | issues | false |
| estimate_volatility_abs | estimation | issue | story_points | false |
| blocked_time_total | aging | issue | hours | false |
| stale_days | aging | issue | days | false |
| epic_delivery_time | ttm | issue | days | true |

**Note:** `release_burnup_sp` from spec becomes TWO calc_codes (scope line + done line) for proper Metabase visualization.
`blocked_time_total` and `stale_days` go under existing `aging` definition.
`epic_delivery_time` goes under existing `ttm` definition.
`input_flow_weekly` goes under existing `throughput` definition.

SQL pattern (following 0020 migration):
```sql
WITH defs AS (SELECT id, metric_code FROM metrics.definitions),
     grns AS (SELECT id, grain_code FROM metrics.grains)
INSERT INTO metrics.calculations (definition_id, calc_code, grain_id, unit_code, uses_commitment_points)
VALUES
  ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_added_issues_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
  -- ... all 22 rows
ON CONFLICT (calc_code) DO NOTHING;
```

### 1.5 Downgrade
```python
def downgrade():
    op.execute("""
        DELETE FROM metrics.calculations WHERE calc_code IN (
            'sprint_added_issues_count', 'sprint_added_sp_sum', 'sprint_removed_issues_count',
            'sprint_removed_sp_sum', 'sprint_spillover_count', 'sprint_burndown_remaining_sp',
            'activation_velocity_pct', 'field_value_sprint_pct', 'unestimated_closed_count',
            'daily_status_entry_count', 'field_change_count', 'input_flow_weekly',
            'defect_density_by_type', 'backflow_column_rate', 'release_burnup_scope_sp',
            'release_burnup_done_sp', 'issue_lifetime_days', 'cycle_time_custom',
            'cancellation_rate_weekly', 'estimate_volatility_abs', 'blocked_time_total',
            'stale_days', 'epic_delivery_time'
        )
    """)
    op.execute("DELETE FROM metrics.definitions WHERE metric_code IN ('sprint_health','flow_dynamics','quality','delivery','waste','estimation','cycle_time')")
    op.execute("DELETE FROM metrics.grains WHERE grain_code = 'project'")
    op.execute("DELETE FROM metrics.units WHERE unit_code = 'ratio' AND project_id IS NULL")
```

---

## Phase 2: Calculation Engine

### 2.1 `pipelines/calculations/sprint_health.py` (NEW FILE)

#### Imports needed:
```python
import polars as pl
from pipelines.calculations.velocity import determine_story_points_at_date
```

#### Function: `calculate_sprint_scope_changes(sprints_df, sprint_changelog_df, issues_df, field_values_df, unit_field_entity)`
- **Input DataFrames:**
  - `sprints_df`: [id, iteration_id, project_id, name, start_date, end_date]
  - `sprint_changelog_df`: [sprint_id, issue_id, action, change_time]
  - `issues_df`: [id, issue_key, project_id]
  - `field_values_df`: [issue_id, field_key_id, value] — for current SP
  - `unit_field_entity`: str — the entity/field_key for story_points (e.g., 'customfield_10036')
- **Logic:**
  1. For each sprint, find `added_issues`: sprint_changelog WHERE action='added' AND change_time > sprint.start_date AND change_time <= sprint.end_date
  2. For each sprint, find `removed_issues`: sprint_changelog WHERE action='removed' AND change_time > sprint.start_date AND change_time <= sprint.end_date
  3. Count issues (sprint_added_issues_count, sprint_removed_issues_count)
  4. Join added/removed with field_values to get SP sum (sprint_added_sp_sum, sprint_removed_sp_sum)
  5. For SP: use `determine_story_points_at_date()` at sprint.start_date if field_value_changelog available, else current SP from field_values
- **Output:** pl.DataFrame with columns [project_id, iteration_id, iteration_name, sprint_start_date, added_count, added_sp, removed_count, removed_sp]

#### Function: `calculate_sprint_spillover(sprints_df, sprint_issues_df)`
- **Logic:**
  1. Count issues that appear in more than one sprint
  2. `sprint_issues_df`: [sprint_id, issue_id]
  3. Group by issue_id, count distinct sprint_ids -> filter count > 1
  4. Join back to current sprint context
- **Output:** pl.DataFrame [project_id, iteration_id, iteration_name, sprint_start_date, spillover_count]

#### Function: `calculate_sprint_burndown(sprints_df, sprint_issues_df, issue_status_changelog_df, board_columns_df, field_values_df, unit_field_entity)`
- **Logic:**
  1. For each sprint, get total planned SP (same logic as velocity commitment snapshot)
  2. For each day D in [sprint_start, sprint_end]:
     - Find issues that transitioned to done status ON day D (from issue_status_changelog)
     - completed_sp_on_day_D = sum(SP of those issues)
  3. cumulative_completed_sp[D] = sum(completed_sp for all days <= D)
  4. remaining_sp[D] = total_planned_sp - cumulative_completed_sp[D]
  5. One row per (sprint, day): entity_type='sprint', entity_id=iteration_id, time_id=YYYYMMDD(D)
- **Output:** pl.DataFrame [project_id, iteration_id, time_date, remaining_sp]

#### Function: `calculate_activation_velocity(sprints_df, sprint_issues_df, sprint_changelog_df, issue_status_changelog_df, field_values_df, unit_field_entity, initial_status_id)`
- **initial_status_id:** resolved via commitment_resolver for activation_velocity_pct
- **Logic:**
  1. For each sprint, total_planned_sp = sum SP of commitment at sprint start
  2. For each day D in [sprint_start, sprint_end]:
     - Find issues moved FROM initial_status ON day D (from issue_status_changelog where from_status_id=initial_status_id)
     - moved_sp_on_day_D = sum SP of those issues
  3. cumulative_moved_sp[D] = sum(moved_sp for all days <= D)
  4. activation_pct[D] = (cumulative_moved_sp[D] / total_planned_sp) * 100
  5. Clamp to [0, 100], handle division by zero (planned_sp=0 → 0%)
- **Output:** pl.DataFrame [project_id, iteration_id, time_date, activation_pct]

#### Function: `calculate_field_value_sprint_pct(sprints_df, sprint_issues_df, issues_df, field_name, field_value, issues_field_df)`
- **Parameters:** field_name and field_value come from calculation_settings.settings_json
- **Logic:**
  1. For each sprint, get all issues in that sprint
  2. Filter issues where field=field_value (join with field_values or check issue column directly)
  3. pct = count(filtered) / total * 100
- **Output:** pl.DataFrame [project_id, iteration_id, sprint_start_date, field_pct]

#### Function: `calculate_unestimated_closed(sprints_df, sprint_issues_df, issues_df, issue_status_changelog_df, done_status_ids, field_values_df, sp_field_key_id)`
- **Logic:**
  1. Get all issues in sprint
  2. Filter: final status in done_status_ids AND (sp is null OR sp=0)
  3. SP check: join with field_values where field_key_id=sp_field_key_id, check value is null or '0'
  4. Count per sprint
- **Output:** pl.DataFrame [project_id, iteration_id, sprint_start_date, unestimated_closed_count]

### 2.2 `pipelines/calculations/flow_dynamics.py` (NEW FILE)

#### Function: `calculate_daily_status_entry(sprints_df, sprint_issues_df, issue_status_changelog_df, target_status_id)`
- **target_status_id:** resolved from calculation_settings.settings_json["target_status"]
- **Logic:**
  1. For each sprint, for each day D:
     - count(issue_id) where to_status_id=target_status_id AND change_time on day D AND issue in sprint
  2. One row per (sprint, day)
- **Output:** pl.DataFrame [project_id, iteration_id, time_date, entry_count]

#### Function: `calculate_field_change_count(sprints_df, sprint_issues_df, field_value_changelog_df, field_key_id)`
- **field_key_id:** resolved from calculation_settings.settings_json["field"]
- **Logic:**
  1. Count changes in field_value_changelog where field_key_id matches AND change_time BETWEEN sprint_start AND sprint_end AND issue in sprint
  2. Sum per sprint
- **Output:** pl.DataFrame [project_id, iteration_id, sprint_start_date, change_count]

### 2.3 `pipelines/calculations/input_flow.py` (NEW FILE — extends throughput concept)

#### Function: `calculate_input_flow_weekly(issue_status_changelog_df, start_status_ids, issues_df)`
- **start_status_ids:** resolved via commitment_rules for input_flow_weekly
- **Logic:**
  1. Find transitions TO start_status_ids from issue_status_changelog
  2. Group by ISO week (extract week from change_time)
  3. Count distinct issues per week per project
- **Output:** pl.DataFrame [project_id, iso_week_start_date, flow_count]
  - iso_week_start_date = Monday of that ISO week, formatted as YYYYMMDD for time_id

### 2.4 `pipelines/calculations/quality.py` (NEW FILE)

#### Function: `calculate_defect_density(sprints_df, sprint_issues_df, issues_df, issue_types_df, numerator_type, denominator_type)`
- **numerator_type, denominator_type:** from calculation_settings.settings_json
- **Logic:**
  1. Join issues with issue_types to get type names
  2. Per sprint:
     - n = count(issues where type_name=numerator_type)
     - d = count(issues where type_name=denominator_type)
     - ratio = n / d (return null or 0 if d=0, do NOT divide by zero)
- **Output:** pl.DataFrame [project_id, iteration_id, sprint_start_date, density_ratio]

#### Function: `calculate_backflow_rate(sprints_df, sprint_issues_df, issue_status_changelog_df, board_columns_df)`
- **Logic:**
  1. Build status_id → position mapping from board_columns (status_ids is array, unnest)
  2. For each transition in issue_status_changelog within sprint date range:
     - from_pos = position[from_status_id]
     - to_pos = position[to_status_id]
     - is_backward = (to_pos < from_pos)
  3. Per sprint: backflow_rate = (count backward transitions / total transitions) * 100
  4. Handle: transitions to/from statuses not in any column (position=null) → exclude from count
- **Output:** pl.DataFrame [project_id, iteration_id, sprint_start_date, backflow_pct]

### 2.5 `pipelines/calculations/delivery.py` (NEW FILE)

#### Function: `calculate_release_burnup(issues_df, issue_status_changelog_df, done_status_ids, field_values_df, sp_field_key_id, versions_df_or_fix_versions_col)`
- **Note:** fix_versions might be a JSONB column on issues or a separate join table. Check `clean_jira.issues` actual columns. If it's JSONB, parse it. If it's a separate table (fix_version_issues), join it.
- **Fallback:** If fix_versions data is empty/unavailable, log a warning and return empty DataFrame gracefully.
- **Logic:**
  1. Group issues by version (fix_version)
  2. For each version, for each day D from first issue creation to release date (or today):
     - scope_sp = sum(current SP of all issues in version as of day D)
     - done_sp = sum(SP of issues in version that were in done status as of day D)
  3. Two rows per (version, day): one for scope, one for done
- **Output:** pl.DataFrame [project_id, version_name, time_date, scope_sp, done_sp]
  - Split into two rows: calc_code='release_burnup_scope_sp' and 'release_burnup_done_sp'

### 2.6 `pipelines/calculations/cycle_time_ext.py` (NEW FILE)

#### Function: `calculate_issue_lifetime(issues_df, issue_status_changelog_df, done_status_ids)`
- **Logic:**
  1. For each issue: find first transition into done_status_ids
  2. lifetime_days = date_diff(done_date, issues.created_at)
  3. Exclude: issues not yet done (return null), issues with created_at after done_date (data error, skip)
- **Output:** pl.DataFrame [project_id, issue_id, issue_key, created_at, done_date, lifetime_days]

#### Function: `calculate_cycle_time_custom(issues_df, issue_status_changelog_df, start_status_id, end_status_id)`
- **start_status_id, end_status_id:** resolved via commitment_rules for cycle_time_custom
- **Logic:**
  1. For each issue: find FIRST transition INTO start_status_id (from_status != start_status, to_status = start_status)
  2. Find FIRST transition INTO end_status_id AFTER the start time
  3. cycle_days = date_diff(end_time, start_time)
  4. Skip issues where start or end times not found
- **Output:** pl.DataFrame [project_id, issue_id, issue_key, start_at, end_at, cycle_days]

#### Function: `calculate_epic_delivery_time(epics_df, issues_df, issue_status_changelog_df, commitment_start_status_ids, done_status_ids)`
- **Logic:**
  1. For each epic (issues where issue_type='Epic' or issues with children):
     - children = issues where parent_id = epic.id
     - epic_start = min(first_transition_to_start_status for each child)
     - epic_end = max(final_transition_to_done_status for each child)
     - delivery_time_days = date_diff(epic_end, epic_start)
  2. Exclude epics with no children, no start events, or no done events
  3. **Fallback for parent_id:** if parent_id column missing from issues_df, skip calculation with warning
- **Output:** pl.DataFrame [project_id, epic_id, epic_key, epic_start, epic_end, delivery_days]

### 2.7 `pipelines/calculations/waste.py` (NEW FILE)

#### Function: `calculate_cancellation_rate_weekly(issue_status_changelog_df, cancelled_status_ids, issues_df)`
- **cancelled_status_ids:** resolved from calculation_settings.settings_json["cancelled_status"] OR from status names containing 'reject', 'cancel', 'won\'t fix', 'duplicate'
- **Fallback:** if no calculation_settings, attempt to detect cancellation statuses from status names
- **Logic:**
  1. Find transitions INTO cancelled_status_ids
  2. Group by ISO week
  3. Count distinct issues per week per project
- **Output:** pl.DataFrame [project_id, iso_week_start_date, cancellation_count]

### 2.8 `pipelines/calculations/estimation.py` (NEW FILE)

#### Function: `calculate_estimate_volatility(issues_df, field_value_changelog_df, field_values_df, sp_field_key_id)`
- **Logic:**
  1. For each issue:
     - initial_sp: first entry in field_value_changelog for sp field where old_value IS NULL (first time set), OR first old_value in changelog
     - If no changelog, initial_sp = current_sp (volatility = 0)
     - current_sp from field_values
     - volatility = abs(current_sp_float - initial_sp_float)
  2. Handle null SP as 0 for calculation
  3. Skip issues with no SP data at all
- **Output:** pl.DataFrame [project_id, issue_id, issue_key, initial_sp, final_sp, volatility]

### 2.9 Extend `pipelines/calculations/aging.py` (MODIFY EXISTING)

#### New function: `calculate_blocked_time(issues_df, field_value_changelog_df, blocked_field_key_id)`
- **blocked_field_key_id:** resolved by looking up field_key='blocked' or field_name ILIKE '%blocked%' in field_keys
- **Fallback:** if no blocked field exists in field_keys, return empty DataFrame with warning
- **Logic:**
  1. Get all changes to the blocked field ordered by change_time per issue
  2. Find intervals where value = 'true' (or '1' or 'yes' depending on field type)
  3. For each blocked interval: blocked_at = change_time of entry, unblocked_at = change_time of next change
  4. If still blocked (no exit): unblocked_at = now()
  5. blocked_hours = sum(date_diff in hours for each interval) per issue
- **Output:** pl.DataFrame [project_id, issue_id, issue_key, blocked_hours]

#### New function: `calculate_stale_days(issues_df, issue_status_changelog_df, done_status_ids, now_date)`
- **Logic:**
  1. Filter issues: current status NOT in done_status_ids
  2. stale_days = date_diff(now_date, issues.updated_at)
  3. Return all open issues with their stale count
- **Output:** pl.DataFrame [project_id, issue_id, issue_key, current_status_id, stale_days]

---

## Phase 3: Dagster Assets

### Pattern to follow: `pipelines/assets/metrics/velocity.py`
Each asset file follows this structure:
```python
@asset(group_name="metrics", deps=[...], compute_kind="python")
def calculate_<metric_group>(context, database: DatabaseResource):
    engine = database.get_engine()
    # 1. Resolve IDs
    # 2. Load data with read_table()
    # 3. Resolve commitment rules (if needed)
    # 4. Load calculation_settings (if needed)
    # 5. Calculate
    # 6. Apply slicing (optional)
    # 7. write_fact_values()
    # 8. Return MaterializeResult with metadata

@asset_check(asset=calculate_<metric_group>)
def <metric_group>_data_quality_check(database: DatabaseResource):
    # Verify rows were written, values in valid range
```

### 3.1 `pipelines/assets/metrics/sprint_health.py` (NEW FILE)

```
@asset calculate_sprint_health(context, database)
deps: [clean_jira_sprints, clean_jira_sprint_issues, clean_jira_sprint_issues_changelog,
       clean_jira_issues, clean_jira_field_values, clean_jira_board_columns, clean_jira_boards,
       clean_jira_issue_status_changelog]

Calculations handled:
- sprint_added_issues_count
- sprint_added_sp_sum
- sprint_removed_issues_count
- sprint_removed_sp_sum
- sprint_spillover_count
- sprint_burndown_remaining_sp  (daily rows)
- activation_velocity_pct       (daily rows, needs commitment rule)
- unestimated_closed_count      (needs commitment rule for done status)

Parameterized (from calculation_settings, skip gracefully if not configured):
- field_value_sprint_pct        (needs settings per project)
```

**Data loading queries:**
```sql
-- sprints
SELECT s.id, s.iteration_id, s.project_id, s.name, s.start_date, s.end_date
FROM clean_jira.sprints s WHERE s.state IN ('closed', 'active')

-- sprint_issues
SELECT si.sprint_id, si.issue_id FROM clean_jira.sprint_issues si

-- sprint_issues_changelog
SELECT sc.sprint_id, sc.issue_id, sc.action, sc.change_time
FROM clean_jira.sprint_issues_changelog sc

-- issues (with SP field)
SELECT i.id, i.issue_key, i.project_id, i.created_at, i.updated_at
FROM clean_jira.issues i

-- field_values (for SP)
SELECT fv.issue_id, fv.field_key_id, fv.value
FROM clean_jira.field_values fv
JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
WHERE fk.field_key = (resolved from metrics.units for unit_code='story_points')

-- issue_status_changelog
SELECT isc.issue_id, isc.from_status_id, isc.to_status_id, isc.change_time
FROM clean_jira.issue_status_changelog isc
```

**Writing to fact_values for sprint-grain metrics:**
```python
# for sprint_added_issues_count per sprint:
# time_id = int(sprint.start_date.strftime('%Y%m%d'))
# entity_type = 'sprint'
# entity_id = sprint.iteration_id
# value = count
```

**Writing for day-grain metrics (burndown, activation):**
```python
# for each (sprint, day) row:
# time_id = int(day.strftime('%Y%m%d'))
# entity_type = 'sprint'
# entity_id = sprint.iteration_id
# value = remaining_sp or activation_pct
```

### 3.2 `pipelines/assets/metrics/flow_dynamics.py` (NEW FILE)

```
@asset calculate_flow_dynamics(context, database)
deps: [clean_jira_sprints, clean_jira_sprint_issues, clean_jira_issue_status_changelog,
       clean_jira_field_value_changelog, clean_jira_field_keys]

Calculations:
- daily_status_entry_count  (from calculation_settings, skip if not configured)
- field_change_count        (from calculation_settings, skip if not configured)
```

**Loading calculation_settings:**
```python
def load_settings_for_calc(engine, calc_code):
    # Query: SELECT cs.* FROM metrics.calculation_settings cs
    #        JOIN metrics.calculations c ON c.id = cs.target_calculation_id
    #        WHERE c.calc_code = %(calc_code)s AND cs.enabled = true
    # Returns list of dicts, one per project (or global)
```

### 3.3 `pipelines/assets/metrics/input_flow.py` (NEW FILE)

```
@asset calculate_input_flow(context, database)
deps: [clean_jira_issue_status_changelog, clean_jira_issues, clean_jira_boards, clean_jira_board_columns]

Calculations:
- input_flow_weekly (uses commitment_rules for start columns)
```

### 3.4 `pipelines/assets/metrics/quality.py` (NEW FILE)

```
@asset calculate_quality_metrics(context, database)
deps: [clean_jira_sprints, clean_jira_sprint_issues, clean_jira_issues, clean_jira_issue_types,
       clean_jira_issue_status_changelog, clean_jira_boards, clean_jira_board_columns]

Calculations:
- defect_density_by_type   (from calculation_settings)
- backflow_column_rate     (needs board_columns.position)
```

### 3.5 `pipelines/assets/metrics/delivery.py` (NEW FILE)

```
@asset calculate_delivery_metrics(context, database)
deps: [clean_jira_issues, clean_jira_issue_status_changelog, clean_jira_field_values,
       clean_jira_boards, clean_jira_board_columns]

Calculations:
- release_burnup_scope_sp
- release_burnup_done_sp

Note: entity_type='version', entity_id=version_name
      project grain → time_id = YYYYMMDD of each data point day
```

### 3.6 `pipelines/assets/metrics/cycle_time_ext.py` (NEW FILE)

```
@asset calculate_cycle_time_extended(context, database)
deps: [clean_jira_issues, clean_jira_issue_status_changelog, clean_jira_boards,
       clean_jira_board_columns, clean_jira_issue_types]

Calculations:
- issue_lifetime_days
- cycle_time_custom        (uses commitment_rules)
- epic_delivery_time       (uses commitment_rules, requires parent_id column)
```

### 3.7 `pipelines/assets/metrics/waste.py` (NEW FILE)

```
@asset calculate_waste_metrics(context, database)
deps: [clean_jira_issue_status_changelog, clean_jira_issues, clean_jira_boards, clean_jira_board_columns]

Calculations:
- cancellation_rate_weekly (uses calculation_settings or auto-detect cancelled statuses)
```

### 3.8 `pipelines/assets/metrics/estimation.py` (NEW FILE)

```
@asset calculate_estimation_metrics(context, database)
deps: [clean_jira_issues, clean_jira_field_value_changelog, clean_jira_field_values,
       clean_jira_field_keys]

Calculations:
- estimate_volatility_abs
```

### 3.9 Extend `pipelines/assets/metrics/advanced.py` (MODIFY EXISTING)

Add two new calculations to the existing `calculate_advanced_metrics` asset OR create a new `calculate_aging_extended` asset:
- blocked_time_total
- stale_days

Prefer creating a separate asset `calculate_aging_extended` to keep separation of concerns.

---

## Phase 4: Registration Updates

### 4.1 `pipelines/assets/metrics/__init__.py` (MODIFY)

Add imports for all new assets:
```python
from .sprint_health import calculate_sprint_health, sprint_health_data_quality_check
from .flow_dynamics import calculate_flow_dynamics, flow_dynamics_data_quality_check
from .input_flow import calculate_input_flow, input_flow_data_quality_check
from .quality import calculate_quality_metrics, quality_data_quality_check
from .delivery import calculate_delivery_metrics, delivery_data_quality_check
from .cycle_time_ext import calculate_cycle_time_extended, cycle_time_ext_data_quality_check
from .waste import calculate_waste_metrics, waste_data_quality_check
from .estimation import calculate_estimation_metrics, estimation_data_quality_check
from .advanced import calculate_aging_extended, aging_extended_data_quality_check
```

Add all new names to `__all__`.

### 4.2 `pipelines/assets/metrics/refresh.py` (MODIFY)

Add new assets to the existing job definitions. Check if there's a `metrics_all` job - add all new assets to it:
```python
metrics_all = define_asset_job(
    name="metrics_all",
    selection=AssetSelection.groups("metrics"),
)
```
If using `AssetSelection.groups("metrics")` pattern, new assets with `group_name="metrics"` will be auto-included. Verify this is the case.

---

## Phase 5: Tests

### Testing Pattern (from existing tests)
All tests use Polars DataFrames as in-memory fixtures. NO database connections. Functions are called directly.

**Example fixture pattern:**
```python
def make_sprints_df():
    return pl.DataFrame({
        "id": ["sp1"], "iteration_id": ["100"],
        "project_id": ["proj1"], "name": ["Sprint 1"],
        "start_date": [date(2026, 1, 1)], "end_date": [date(2026, 1, 14)]
    })
```

### 5.1 `tests/unit/test_sprint_health.py` (NEW FILE)

Test cases:
1. `test_sprint_added_issues_count_basic` — issues added after sprint start are counted
2. `test_sprint_added_issues_count_excludes_initial` — issues added before sprint start not counted
3. `test_sprint_removed_issues_count_basic` — removed after start, before end
4. `test_sprint_sp_sum_uses_field_values` — SP summed correctly from field_values
5. `test_sprint_spillover_count_basic` — issue in 2 sprints → spillover=1
6. `test_sprint_spillover_excludes_single_sprint` — issue in 1 sprint not counted
7. `test_burndown_starts_at_total_sp` — day 0 remaining = total planned SP
8. `test_burndown_decreases_on_completion` — remaining decreases as issues complete
9. `test_burndown_reaches_zero_on_full_completion` — all done → 0 remaining
10. `test_activation_velocity_cumulative` — cumulative percent increases over days
11. `test_activation_velocity_division_by_zero` — 0 planned SP → 0% (no exception)
12. `test_unestimated_closed_counts_null_sp` — issues with null SP in done status
13. `test_unestimated_closed_excludes_estimated` — issues with SP > 0 excluded
14. `test_field_value_sprint_pct_basic` — correct percentage calculation

### 5.2 `tests/unit/test_flow_dynamics.py` (NEW FILE)

Test cases:
1. `test_daily_status_entry_count_basic` — correct count per day
2. `test_daily_status_entry_count_filters_by_sprint` — only sprint issues counted
3. `test_field_change_count_within_sprint_dates` — changes outside date range excluded
4. `test_field_change_count_correct_field` — only target field counted

### 5.3 `tests/unit/test_input_flow.py` (NEW FILE)

Test cases:
1. `test_input_flow_weekly_groups_by_week` — multiple issues in same week = one row
2. `test_input_flow_weekly_filters_by_start_status` — only target status transitions
3. `test_input_flow_weekly_deduplicates_issues` — same issue entering status twice in week = count 1

### 5.4 `tests/unit/test_quality.py` (NEW FILE)

Test cases:
1. `test_defect_density_basic` — 2 bugs / 10 stories = 0.2
2. `test_defect_density_zero_denominator` — 0 stories → return 0 or null, no exception
3. `test_backflow_rate_basic` — 1 backward transition out of 4 = 25%
4. `test_backflow_rate_no_backward_transitions` — all forward → 0%
5. `test_backflow_rate_excludes_unmapped_statuses` — statuses with no position excluded

### 5.5 `tests/unit/test_delivery.py` (NEW FILE)

Test cases:
1. `test_release_burnup_scope_grows` — adding issues increases scope line
2. `test_release_burnup_done_increases` — completing issues increases done line
3. `test_release_burnup_empty_version` — no fix_versions data → empty result, no exception
4. `test_release_burnup_two_calc_codes` — output has both scope and done rows

### 5.6 `tests/unit/test_cycle_time_ext.py` (NEW FILE)

Test cases:
1. `test_issue_lifetime_basic` — created_at to done_date correct diff
2. `test_issue_lifetime_skips_open_issues` — issues without done date excluded
3. `test_cycle_time_custom_basic` — start to end status time
4. `test_cycle_time_custom_uses_first_occurrence` — first start, first end after start
5. `test_epic_delivery_time_basic` — min(child starts) to max(child dones)
6. `test_epic_delivery_time_no_children` — epic with no children → excluded
7. `test_epic_delivery_time_partial_children` — some children not done → excluded

### 5.7 `tests/unit/test_waste.py` (NEW FILE)

Test cases:
1. `test_cancellation_weekly_groups_by_week` — cancellations per ISO week
2. `test_cancellation_weekly_filters_by_status` — only cancellation status counted
3. `test_cancellation_weekly_auto_detect_cancelled` — fallback to status name matching

### 5.8 `tests/unit/test_estimation.py` (NEW FILE)

Test cases:
1. `test_estimate_volatility_basic` — abs(5 - 2) = 3
2. `test_estimate_volatility_unchanged` — same initial and final = 0
3. `test_estimate_volatility_no_changelog` — no history → volatility = 0
4. `test_estimate_volatility_null_sp` — null treated as 0

### 5.9 `tests/unit/test_aging_extended.py` (NEW FILE)

Test cases:
1. `test_blocked_time_basic` — 2-hour blocked interval = 2 hours
2. `test_blocked_time_multiple_intervals` — sums multiple intervals
3. `test_blocked_time_still_blocked` — open interval uses now()
4. `test_blocked_time_no_blocked_field` — returns empty DataFrame gracefully
5. `test_stale_days_open_issues` — correct date diff for open issues
6. `test_stale_days_excludes_done` — issues in done status excluded

---

## Phase 6: Verification Checklist

After implementation, run:

```bash
# 1. Run all new unit tests
python -m pytest tests/unit/test_sprint_health.py -v
python -m pytest tests/unit/test_flow_dynamics.py -v
python -m pytest tests/unit/test_input_flow.py -v
python -m pytest tests/unit/test_quality.py -v
python -m pytest tests/unit/test_delivery.py -v
python -m pytest tests/unit/test_cycle_time_ext.py -v
python -m pytest tests/unit/test_waste.py -v
python -m pytest tests/unit/test_estimation.py -v
python -m pytest tests/unit/test_aging_extended.py -v

# 2. Run full test suite to check no regressions
python -m pytest tests/unit/ -v

# 3. Check imports work
python -c "from pipelines.assets.metrics import *"
python -c "from pipelines.calculations.sprint_health import *"

# 4. Check migration syntax
alembic check  # or equivalent

# 5. Run ruff linter
ruff check pipelines/calculations/ pipelines/assets/metrics/
ruff check tests/unit/test_sprint_health.py tests/unit/test_flow_dynamics.py
```

---

## Implementation Notes & Edge Cases

### Critical: write_fact_values idempotency for entity-grain metrics
The current `write_fact_values()` in `polars_db.py` deletes by `(metric_id, project_agg_id, time_id)`.
For issue-grain metrics, this is insufficient since multiple issues share same time_id.
**Solution:** Before calling `write_fact_values()`, verify if `entity_id` is needed in the delete key.
If so, extend `write_fact_values()` to optionally include `entity_id` in the match key.
Alternatively, use `time_id = date(issue.created_at)` + entity_id matching.
Check existing lead_time.py asset for how it handles issue-grain writes.

### Critical: SP field resolution
Use `resolve_unit_field(engine, project_id, 'story_points')` from metric_registry.py to get the correct field_key_id per project before any SP calculations.

### Graceful degradation
ALL calculations that depend on optional data (fix_versions, blocked flag, parent_id) must:
1. Check if data exists
2. Log a warning if data is empty/missing
3. Return an empty DataFrame (not raise an exception)
This ensures assets don't fail for projects that don't have this data configured.

### Time zones
All datetimes are UTC. Use `pl.Datetime("us", "UTC")` where timestamps needed.

### Sprint date boundaries
Use HALF-OPEN intervals: `[start_date, end_date)` for sprint membership.
"During sprint" = `change_time > sprint_start_date AND change_time <= sprint_end_date`.

### calculation_settings loading helper
Add `load_settings_for_calc(engine, calc_code)` helper function in `metric_registry.py` (or each asset file) that:
1. Queries `metrics.calculation_settings JOIN metrics.calculations` by calc_code
2. Returns a list of (project_id, settings_json) tuples
3. Falls back to global settings (project_id IS NULL) if no project-specific setting exists

---

## Files to Create

### New migration:
- `db/migrations/versions/0026_add_expanded_metrics.py`

### New calculation files:
- `pipelines/calculations/sprint_health.py`
- `pipelines/calculations/flow_dynamics.py`
- `pipelines/calculations/input_flow.py`
- `pipelines/calculations/quality.py`
- `pipelines/calculations/delivery.py`
- `pipelines/calculations/cycle_time_ext.py`
- `pipelines/calculations/waste.py`
- `pipelines/calculations/estimation.py`

### New asset files:
- `pipelines/assets/metrics/sprint_health.py`
- `pipelines/assets/metrics/flow_dynamics.py`
- `pipelines/assets/metrics/input_flow.py`
- `pipelines/assets/metrics/quality.py`
- `pipelines/assets/metrics/delivery.py`
- `pipelines/assets/metrics/cycle_time_ext.py`
- `pipelines/assets/metrics/waste.py`
- `pipelines/assets/metrics/estimation.py`

### New test files:
- `tests/unit/test_sprint_health.py`
- `tests/unit/test_flow_dynamics.py`
- `tests/unit/test_input_flow.py`
- `tests/unit/test_quality.py`
- `tests/unit/test_delivery.py`
- `tests/unit/test_cycle_time_ext.py`
- `tests/unit/test_waste.py`
- `tests/unit/test_estimation.py`
- `tests/unit/test_aging_extended.py`

## Files to Modify

- `db/migrations/versions/0026_add_expanded_metrics.py` (new, sets down_revision="0025")
- `pipelines/calculations/aging.py` (add blocked_time_total, stale_days functions)
- `pipelines/assets/metrics/__init__.py` (add new imports and __all__ entries)
- `pipelines/assets/metrics/refresh.py` (verify new assets included in metrics_all job)
- `pipelines/utils/metric_registry.py` (optionally add load_settings_for_calc helper)
