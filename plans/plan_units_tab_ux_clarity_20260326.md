# Units Tab UX Clarity Improvements — 2026-03-26

## Problem analysis

The user has a global unit binding (project_id=NULL, unit_code=story_points,
source_field_id set) and still sees "many missing" entries.

Two causes:

### CAUSE-1: Missing rows are duplicated per calc_code, not deduplicated per unit_code

The current missing check produces ONE row per (project, calc_code) combination.
If there are 5 calc_codes that all require `unit_code=story_points` and 10 projects,
this produces 50 rows — even though the user only needs to create 1 unit binding
(story_points) per project to fix everything.

The user sees 50 rows and thinks "many missing" even though the real deficit is
"1 unit binding per project".

Fix: deduplicate missing_rows by (project_id, unit_code). Instead of one row per
calc_code, produce one row per unit_code and aggregate the affected calc_codes into
a `required_by` field: "velocity, throughput, ..."

### CAUSE-2: Global binding in "Current Unit Bindings" shows blank project_id

The raw data shows `project_id: null/blank` in the dataframe. The user sees a record
with no project and thinks it might be broken or incomplete, not understanding that
blank = "applies to all projects".

Fix: add a `scope` column with human-readable values:
- `"Global (all projects)"` when project_id is None
- `"<PROJECT_KEY>"` (e.g., "ADS") when project_id is set

### CAUSE-3: Empty state for "Missing" table is not communicative

When missing_rows is empty (because global binding covers everything), the dataframe
renders as empty — no headers, no message. The user cannot tell if empty = "all good"
or empty = "display error".

Fix: when missing_rows is empty, show `st.success("✓ All required unit bindings are configured")`.

---

## Files to modify

### `streamlit_admin/app.py` — function `_tab_units_v2`

#### Change 1 (CAUSE-1): Deduplicate missing_rows by (project_id, unit_code)

Replace the current missing_rows building block:
```python
missing_rows: list[dict[str, Any]] = []
for p in projects:
    for c in required_contracts:
        key = (p["project_id"], c["unit_code"])
        if key not in unit_set and (None, c["unit_code"]) not in unit_set:
            missing_rows.append({
                "project_id": p["project_id"],
                "project_key": p["project_key"],
                "calc_code": c["calc_code"],
                "unit_code": c["unit_code"],
                "missing": "unit_binding",
            })
```

With this deduplicated version:
```python
# Build a dict keyed by (project_id, unit_code) → list of affected calc_codes
missing_by_unit: dict[tuple, dict[str, Any]] = {}
for p in projects:
    for c in required_contracts:
        key = (p["project_id"], c["unit_code"])
        if key not in unit_set and (None, c["unit_code"]) not in unit_set:
            if key not in missing_by_unit:
                missing_by_unit[key] = {
                    "project_id": p["project_id"],
                    "project_key": p["project_key"],
                    "unit_code": c["unit_code"],
                    "required_by_calcs": [],
                }
            missing_by_unit[key]["required_by_calcs"].append(c["calc_code"])

missing_rows = [
    {
        "project_key": v["project_key"],
        "unit_code": v["unit_code"],
        "required_by": ", ".join(sorted(v["required_by_calcs"])),
    }
    for v in missing_by_unit.values()
]
```

Also update the filter that follows (it currently filters by `r["project_id"]`):
```python
missing_rows = [
    r
    for r in missing_rows
    if (project_filter is None or missing_by_unit.get(
        (project_filter, r["unit_code"]), {}).get("project_id") == project_filter
        or any(v["project_id"] == project_filter and v["unit_code"] == r["unit_code"]
               for v in missing_by_unit.values()))
    and (calc_filter is None or calc_filter in (r["required_by"] or "").split(", "))
]
```

Actually the filter is simpler: since we changed missing_rows to use project_key
(not project_id), update the filter to work on the original missing_by_unit dict.

Here is the full replacement for the missing logic block:

```python
# Build deduplicated missing: one row per (project_id, unit_code)
missing_by_unit: dict[tuple, dict[str, Any]] = {}
for p in projects:
    for c in required_contracts:
        dedup_key = (p["project_id"], c["unit_code"])
        if dedup_key not in unit_set and (None, c["unit_code"]) not in unit_set:
            if dedup_key not in missing_by_unit:
                missing_by_unit[dedup_key] = {
                    "project_id": p["project_id"],
                    "project_key": p["project_key"],
                    "unit_code": c["unit_code"],
                    "required_by_calcs": [],
                }
            missing_by_unit[dedup_key]["required_by_calcs"].append(c["calc_code"])

missing_rows = [
    {
        "project_key": v["project_key"],
        "unit_code": v["unit_code"],
        "required_by": ", ".join(sorted(v["required_by_calcs"])),
    }
    for v in missing_by_unit.values()
    if (project_filter is None or v["project_id"] == project_filter)
    and (calc_filter is None or calc_filter in v["required_by_calcs"])
]
```

#### Change 2 (CAUSE-2): Add `scope` column to "Current Unit Bindings" display

Build a lookup from project_id to project_key for use in the display:
```python
project_key_by_id = {p["project_id"]: p["project_key"] for p in projects}
```

Replace the expander content:
```python
with st.expander("Current Unit Bindings", expanded=True):
    st.caption("'Global (all projects)' bindings apply to every project unless overridden by a project-specific binding.")
    display_units = [
        {
            "scope": "Global (all projects)" if u.get("project_id") is None
                     else project_key_by_id.get(u.get("project_id"), u.get("project_id")),
            "unit_code": u.get("unit_code"),
            "display_symbol": u.get("display_symbol"),
            "source_field_id": u.get("source_field_id"),
            "source_entity": u.get("source_entity"),
        }
        for u in filtered
    ]
    st.dataframe(display_units, use_container_width=True, hide_index=True)
```

#### Change 3 (CAUSE-3): Empty state for "Missing required Unit Bindings"

Replace:
```python
with st.expander("Missing required Unit Bindings", expanded=True):
    st.dataframe(missing_rows, use_container_width=True, hide_index=True)
```

With:
```python
with st.expander("Missing required Unit Bindings", expanded=True):
    if not missing_rows:
        st.success("✓ All required unit bindings are configured")
    else:
        st.dataframe(missing_rows, use_container_width=True, hide_index=True)
```

---

## Order of changes in the function

The complete updated block in `_tab_units_v2` (from after the filters to before
the create/update form) should read:

```python
# --- Display: Current Unit Bindings ---
project_key_by_id = {p["project_id"]: p["project_key"] for p in projects}
display_units = [
    {
        "scope": "Global (all projects)" if u.get("project_id") is None
                 else project_key_by_id.get(u.get("project_id"), u.get("project_id")),
        "unit_code": u.get("unit_code"),
        "display_symbol": u.get("display_symbol"),
        "source_field_id": u.get("source_field_id"),
        "source_entity": u.get("source_entity"),
    }
    for u in filtered
]
with st.expander("Current Unit Bindings", expanded=True):
    st.caption(
        "Global (all projects) bindings apply to every project unless a project-specific binding overrides them."
    )
    st.dataframe(display_units, use_container_width=True, hide_index=True)

# --- Missing check (deduplicated by unit_code) ---
unit_set = {
    (u.get("project_id"), u.get("unit_code"))
    for u in all_units
    if u.get("source_field_id")
}
missing_by_unit: dict[tuple, dict[str, Any]] = {}
for p in projects:
    for c in required_contracts:
        dedup_key = (p["project_id"], c["unit_code"])
        if dedup_key not in unit_set and (None, c["unit_code"]) not in unit_set:
            if dedup_key not in missing_by_unit:
                missing_by_unit[dedup_key] = {
                    "project_id": p["project_id"],
                    "project_key": p["project_key"],
                    "unit_code": c["unit_code"],
                    "required_by_calcs": [],
                }
            missing_by_unit[dedup_key]["required_by_calcs"].append(c["calc_code"])

missing_rows = [
    {
        "project_key": v["project_key"],
        "unit_code": v["unit_code"],
        "required_by": ", ".join(sorted(v["required_by_calcs"])),
    }
    for v in missing_by_unit.values()
    if (project_filter is None or v["project_id"] == project_filter)
    and (calc_filter is None or calc_filter in v["required_by_calcs"])
]
with st.expander("Missing required Unit Bindings", expanded=True):
    if not missing_rows:
        st.success("✓ All required unit bindings are configured")
    else:
        st.dataframe(missing_rows, use_container_width=True, hide_index=True)
```

---

## Tests to update

### `tests/unit/test_tab_units_v2.py`

Update the three existing tests to match the new data shape:

1. `test_units_missing_global_binding_not_shown_as_missing`:
   - Now checks that `missing_rows` passed to `st.dataframe` has 0 rows (or
     that `st.success` was called, not `st.dataframe` for the missing section).

2. `test_units_filter_by_project_includes_global_bindings`:
   - Check that the `display_units` list passed to `st.dataframe` contains
     an entry with `scope == "Global (all projects)"` even when project filter is set.

3. `test_units_display_symbol_prefill_from_existing`:
   - No structural change needed here (this tests the form pre-fill, not the display).

Add a new test:
4. `test_units_missing_rows_deduplicated_by_unit_code`:
   - Setup: 2 calc_codes both requiring `unit_code=story_points`, 1 project, no bindings
   - Expected: `missing_rows` has 1 entry (not 2), with `required_by` containing
     both calc_codes comma-separated.
