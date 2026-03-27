# Migrate velocity and estimation to use resolve_unit_field — 2026-03-26

## Context

`metrics.units` / `resolve_unit_field()` is the correct mechanism for resolving
the story-points field per project. It was already implemented and `sprint_health`
uses it. But `velocity` and `estimation` still use the hardcoded heuristic from
`STORY_POINTS_FIELD_CANDIDATES = ["customfield_10036", "customfield_10016", "story_points"]`.

This means the unit binding configured in the admin UI has NO effect on velocity
and estimation calculations.

## Goal

When `metrics.units` has a binding for `unit_code=story_points` (global or
project-specific), velocity and estimation must use that configured `source_field_id`
instead of the hardcoded heuristic. Fallback to heuristic if no binding is configured
(backward-compatible).

---

## Files to modify

### 1. `pipelines/calculations/velocity.py`

Add `sp_field_key_ids_override: list[str] | None = None` parameter to two functions:

#### `extract_story_points()`

Current signature:
```python
def extract_story_points(
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
) -> pl.DataFrame:
```

New signature:
```python
def extract_story_points(
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    sp_field_key_ids_override: list[str] | None = None,
) -> pl.DataFrame:
```

Inside the function, replace the `sp_fields = field_keys_df.filter(...)` heuristic block
with:
```python
if sp_field_key_ids_override:
    sp_field_ids = sp_field_key_ids_override
else:
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    if sp_fields.is_empty():
        return (
            issues_df.select(["id"])
            .rename({"id": "issue_id"})
            .with_columns(pl.lit(0.0).alias("story_points"))
        )
    sp_field_ids = sp_fields.select("id").to_series().to_list()
```
Then continue the rest of the function using `sp_field_ids` (as it already does after line 440).

Note: also remove the now-redundant `if sp_fields.is_empty():` check that appears after
the filter in the original code since it is now handled in the else branch.

#### `determine_story_points_at_date()`

Current signature:
```python
def determine_story_points_at_date(
    scope_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
    current_sp_df: pl.DataFrame,
    changelog_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    date_col: str = "start_date",
) -> pl.DataFrame:
```

New signature:
```python
def determine_story_points_at_date(
    scope_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
    current_sp_df: pl.DataFrame,
    changelog_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    date_col: str = "start_date",
    sp_field_key_ids_override: list[str] | None = None,
) -> pl.DataFrame:
```

Inside the function, replace the `sp_fields = field_keys_df.filter(...)` heuristic block
(approximately lines 330-343) with:
```python
if sp_field_key_ids_override:
    sp_field_ids = sp_field_key_ids_override
else:
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    if sp_fields.is_empty() or changelog_df.is_empty():
        return scope_df.join(current_sp_df, on="issue_id", how="left").select(
            ["issue_id", "sprint_id", "story_points"]
        )
    sp_field_ids = sp_fields["id"].to_list()
```

#### `calculate_velocity_facts()`

Add `sp_field_key_ids_override: list[str] | None = None` parameter (at the end of
the signature, after `allow_current_status_fallback: bool = True`).

Thread this parameter through to both function calls inside `calculate_velocity_facts`:
```python
current_story_points_df = extract_story_points(
    issues_df, field_values_df, field_keys_df,
    sp_field_key_ids_override=sp_field_key_ids_override,
)
```
and wherever `determine_story_points_at_date` is called (there are two calls):
```python
commitment_with_sp = determine_story_points_at_date(
    ...,
    sp_field_key_ids_override=sp_field_key_ids_override,
)
```
```python
completed_with_sp = determine_story_points_at_date(
    ...,
    sp_field_key_ids_override=sp_field_key_ids_override,
)
```

---

### 2. `pipelines/assets/metrics/velocity.py`

Add import at the top (alongside existing imports from `metric_registry`):
```python
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
    resolve_unit_field,  # ADD THIS
)
```

After the `field_keys_df = read_table(...)` call and before the
`velocity_wide = velocity_logic.calculate_velocity_facts(...)` call, add:

```python
# Resolve story_points field keys via metrics.units, per project.
# Falls back to heuristic inside calculate_velocity_facts if no binding found.
sp_field_key_override: list[str] = []
for p_id in project_ids:
    unit_info = resolve_unit_field(engine, p_id, "story_points")
    if unit_info and unit_info.get("source_field_id"):
        fk_id = str(unit_info["source_field_id"])
        if fk_id not in sp_field_key_override:
            sp_field_key_override.append(fk_id)

context.log.info(
    "story_points field key override from metrics.units: %s",
    sp_field_key_override or "none (using heuristic)",
)
```

Then pass `sp_field_key_ids_override=sp_field_key_override or None` to
`velocity_logic.calculate_velocity_facts(...)`:
```python
velocity_wide = velocity_logic.calculate_velocity_facts(
    sprints_df=sprints_df,
    sprint_issues_df=sprint_issues_df,
    sprint_changelog_df=sprint_changelog_df,
    issues_df=issues_df,
    field_values_df=field_values_df,
    field_keys_df=field_keys_df,
    status_changelog_df=status_changelog_df,
    boards_df=boards_df,
    board_columns_df=board_columns_df,
    field_value_changelog_df=field_value_changelog_df,
    issue_statuses_df=issue_statuses_df,
    done_status_ids=done_status_ids or None,
    allow_current_status_fallback=False,
    sp_field_key_ids_override=sp_field_key_override or None,  # ADD THIS
)
```

Note: there may be a second call to `velocity_logic.calculate_velocity_facts()`
(e.g., for sliced calculations). Find ALL calls and add the parameter to each.

---

### 3. `pipelines/assets/metrics/estimation.py`

Add import:
```python
from pipelines.utils.metric_registry import (
    ...,
    resolve_unit_field,  # ADD THIS
)
```

Replace the hardcoded SP field detection block (approximately lines 79-91):
```python
# SP field key (heuristic)
sp_fields = field_keys_df.filter(
    (
        pl.col("external_key").is_in(
            ["customfield_10036", "customfield_10016", "story_points"]
        )
    )
    | (pl.col("name").str.to_lowercase().str.contains("story point"))
)
sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None

if not sp_field_key_id:
    return {"status": "skipped", "reason": "No Story Points field found"}
```

With:
```python
# Try metrics.units unit binding first, fall back to heuristic.
sp_field_key_id: str | None = None

# Use first project as representative for global binding lookup
_sample_pid = project_ids[0] if project_ids else None
if _sample_pid:
    unit_info = resolve_unit_field(engine, _sample_pid, "story_points")
    if unit_info and unit_info.get("source_field_id"):
        sp_field_key_id = str(unit_info["source_field_id"])
        context.log.info(
            "story_points field resolved from metrics.units: %s", sp_field_key_id
        )

if not sp_field_key_id:
    # Fallback to heuristic
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None
    if sp_field_key_id:
        context.log.info(
            "story_points field resolved via heuristic: %s", sp_field_key_id
        )

if not sp_field_key_id:
    return {"status": "skipped", "reason": "No Story Points field found"}
```

NOTE: `project_ids` must already exist at this point in the code. If it doesn't,
look for where `issues_df["project_id"].unique().to_list()` is called and use the
same expression.

---

## Tests to add

### `tests/unit/test_velocity_unit_binding.py` (NEW)

Test that `calculate_velocity_facts()` passes `sp_field_key_ids_override` through to
`extract_story_points()` and `determine_story_points_at_date()`.

Test cases:
- `test_extract_story_points_uses_override_when_provided`: pass `sp_field_key_ids_override=["known_id"]`,
  verify that fields with that ID are used and the heuristic is NOT applied.
- `test_extract_story_points_fallback_to_heuristic_when_no_override`: pass `sp_field_key_ids_override=None`,
  verify that heuristic filter is applied as before.
- `test_determine_story_points_at_date_uses_override`: same pattern for the other function.

### `tests/unit/test_estimation_unit_binding.py` (NEW)

Test that `estimation.py` asset resolves SP field from `metrics.units` when available:
- Mock `resolve_unit_field` to return a specific `source_field_id`
- Verify that field is used instead of heuristic
- Verify fallback works when `resolve_unit_field` returns None
