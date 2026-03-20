# Plan: Fix ruff linting errors after pre-commit hook failure

## Context

A commit attempt failed because pre-commit (black + ruff) flagged 8 issues in the newly added/modified files.
Black already reformatted 6 files (just re-stage them). The remaining ruff issues need code fixes.

## Ruff Errors to Fix

### 1. `pipelines/calculations/slicing_utils.py:67:1 E402` — Import not at top of file

The line `from ..utils.smart_slicer import SmartSlicer` was placed mid-file (after function definitions).
Move it to the top of the file with the other imports.

### 2. `pipelines/calculations/slicing_utils.py:93:9 F841` — `target_schema_table` assigned but never used

After the BUG #3 fix, `target_schema_table = rule.get("source_table", "clean_jira.issues")` is no longer
referenced anywhere in the loop body (the new code uses `slicer.find_target_for_column(source_table, ...)`
where `source_table` is the function parameter, not `target_schema_table`).

Remove the unused `target_schema_table` assignment entirely.

### 3. `pipelines/utils/smart_slicer.py:117:25 S608` — SQL injection via string query

The dynamic SQL in `get_slice_mapping` uses f-string to build table/column names.
Add `# noqa: S608` comment to suppress (these are internal DB schema names from SQLAlchemy inspector,
not user input — suppression is appropriate here, same pattern used elsewhere in the codebase).

### 4. `pipelines/utils/smart_slicer.py:132:17 F841` — `current_table` assigned but never used

In the `get_slice_mapping` SQL construction loop, `current_table` is assigned but never read.
Remove the assignment `current_table = source_table` (line 132, inside the path construction block).

### 5. `pipelines/utils/smart_slicer.py:155:9 F841` — `schema` assigned but never used

In `find_target_for_column`, `schema = source_table.split('.')[0]` is assigned but then
`src_schema` is extracted separately on the next lines. Remove the unused `schema` variable.

### 6. `pipelines/utils/smart_slicer.py:169:23,34 B007` — Loop variables `local_col`, `ref_col` not used

In `find_target_for_column`, the loop `for (neighbor, local_col, ref_col) in graph.get(...):`
uses only `neighbor`. Replace with `for (neighbor, _, _) in graph.get(source_table, []):`.

### 7. `pipelines/utils/smart_slicer.py:182:13 S112` — `try`-`except`-`continue` without logging

The bare `except Exception: continue` in `find_target_for_column` should log the exception.
Replace with `except Exception: self.logger.debug(...)` or add a log call before continue.

## Files to Modify

- `pipelines/calculations/slicing_utils.py` — Move import to top, remove unused `target_schema_table`
- `pipelines/utils/smart_slicer.py` — Add noqa, remove unused vars, fix loop vars, add logging

## After Fix

Re-stage all modified files:
```
git add pipelines/assets/metrics/velocity.py pipelines/calculations/aging.py pipelines/calculations/slicing_utils.py pipelines/utils/smart_slicer.py scripts/migrate_slice_rules_to_smartslicer.py scripts/seed_metric_store.py tests/unit/test_slicing_utils.py tests/unit/test_smart_slicer.py
```

Then commit:
```
git commit -m "fix: populate slice_value and slice_rule_id in fact_values ..."
```

DO NOT run tests in this plan — they were already verified as 225/225 passed.
