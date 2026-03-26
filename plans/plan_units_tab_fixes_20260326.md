# Units Tab Bug Fixes — 2026-03-26

## Bugs found in `_tab_units_v2` in `streamlit_admin/app.py`

---

### BUG-1 (Critical): Global (NULL project_id) unit binding not recognised in "Missing" check

**Location**: `streamlit_admin/app.py`, `_tab_units_v2`, ~line 670-683

**Current code**:
```python
unit_set = {
    (u.get("project_id"), u.get("unit_code"))
    for u in all_units
    if u.get("source_field_id")
}
for p in projects:
    for c in required_contracts:
        key = (p["project_id"], c["unit_code"])
        if key not in unit_set:
            missing_rows.append(...)
```

**Problem**: `unit_set` may contain `(None, "story_points")` (global binding).
But the per-project key is always `(uuid, "story_points")`. These never match,
so a global binding is never treated as satisfying the requirement for any project.
Result: "Missing required Unit Bindings" shows ALL projects as missing even when a
correct global binding exists.

**Fix**: change the missing check to also consider global bindings:
```python
if key not in unit_set and (None, c["unit_code"]) not in unit_set:
    missing_rows.append(...)
```

---

### BUG-2 (Medium): Project filter hides global (NULL) unit bindings

**Location**: `streamlit_admin/app.py`, `_tab_units_v2`, ~line 659

**Current code**:
```python
filtered = [u for u in all_units if (project_filter is None or u.get("project_id") == project_filter)]
```

**Problem**: When user selects a specific project from the filter, global (NULL
project_id) bindings are hidden from the "Current Unit Bindings" table. But global
bindings apply to ALL projects and are just as relevant when viewing a specific project.

**Fix**:
```python
filtered = [
    u for u in all_units
    if project_filter is None
    or u.get("project_id") == project_filter
    or u.get("project_id") is None
]
```

---

### BUG-3 (Medium): display_symbol always defaults to "SP" regardless of existing value

**Location**: `streamlit_admin/app.py`, `_tab_units_v2`, ~line 732

**Current code**:
```python
display_symbol = st.text_input("Display Symbol", value="SP", key="units_display_symbol_input")
```

**Problem**: When the user selects a unit binding that already exists in the DB, the
display_symbol shows "SP" rather than the saved value. If the user saves without
changing the symbol, they silently overwrite it.

**Fix**: Look up the existing display_symbol for the selected project_id + unit_codes
and pre-fill the text input with the existing value (or "SP" if no existing binding):

```python
# Find existing display_symbol for the first selected unit_code (they usually share the same)
existing_symbol = "SP"
if selected_calc_codes:
    first_unit_code = next(
        (calc_to_unit[c] for c in selected_calc_codes if c in calc_to_unit), None
    )
    if first_unit_code:
        existing = next(
            (
                u for u in all_units
                if u.get("unit_code") == first_unit_code
                and (
                    u.get("project_id") == project_id
                    or (project_id is None and u.get("project_id") is None)
                )
            ),
            None,
        )
        if existing:
            existing_symbol = existing.get("display_symbol", "SP")

display_symbol = st.text_input("Display Symbol", value=existing_symbol, key="units_display_symbol_input")
```

However, in Streamlit the `value` on a keyed widget is only used on first render
(widget is already registered). Use `_reset_form_state_on_edit_change` to clear
state when the selection changes so the pre-fill takes effect.

A simpler and reliable pattern is to derive a consistent `edit_key` from
(project_id, sorted unit_codes) and reset form state when it changes:

```python
edit_key = f"{project_id}|{'_'.join(sorted(selected_calc_codes))}"
_reset_form_state_on_edit_change("units_v2", edit_key, ["units_display_symbol_input"])
```

Place this call BEFORE rendering the `st.text_input` to ensure the widget state
is cleared when the edit context changes.

---

## Files to modify

### `streamlit_admin/app.py`

Apply all three fixes to `_tab_units_v2`:

1. **BUG-1 fix** — in the missing_rows check (around line 674), change:
   ```python
   if key not in unit_set:
   ```
   to:
   ```python
   if key not in unit_set and (None, c["unit_code"]) not in unit_set:
   ```

2. **BUG-2 fix** — in the filter (around line 659), change:
   ```python
   filtered = [u for u in all_units if (project_filter is None or u.get("project_id") == project_filter)]
   ```
   to:
   ```python
   filtered = [
       u for u in all_units
       if project_filter is None
       or u.get("project_id") == project_filter
       or u.get("project_id") is None
   ]
   ```

3. **BUG-3 fix** — add pre-fill logic and form state reset.
   Insert BEFORE the `st.text_input` for display_symbol:
   ```python
   # Pre-fill display_symbol from existing binding if any
   existing_symbol = "SP"
   if selected_calc_codes:
       first_unit_code = next(
           (calc_to_unit[c] for c in selected_calc_codes if c in calc_to_unit), None
       )
       if first_unit_code:
           existing_binding = next(
               (
                   u for u in all_units
                   if u.get("unit_code") == first_unit_code
                   and (
                       u.get("project_id") == project_id
                       or (project_id is None and u.get("project_id") is None)
                   )
               ),
               None,
           )
           if existing_binding:
               existing_symbol = existing_binding.get("display_symbol") or "SP"
   edit_key = f"{project_id}|{'_'.join(sorted(selected_calc_codes))}"
   _reset_form_state_on_edit_change("units_v2", edit_key, ["units_display_symbol_input"])
   ```
   Change the `st.text_input` to:
   ```python
   display_symbol = st.text_input("Display Symbol", value=existing_symbol, key="units_display_symbol_input")
   ```

---

## Tests to update/add

### `tests/unit/test_streamlit_admin_app.py`

Add tests for `_tab_units_v2`:
- `test_units_missing_global_binding_not_shown_as_missing`: when a global (NULL
  project_id) unit binding exists with source_field_id set, the "Missing required
  Unit Bindings" list must be empty for all projects covered by that binding.
- `test_units_filter_by_project_includes_global_bindings`: when project_filter is
  set to a specific project_id, global (project_id=None) bindings must appear in the
  filtered list.
- `test_units_display_symbol_prefill_from_existing`: when an existing unit binding
  with a custom display_symbol exists, the text_input must be initialised with that
  value (via _reset_form_state_on_edit_change clearing the widget key on context change).
