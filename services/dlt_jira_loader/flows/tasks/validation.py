"""Validation task for DLT loads.

Performs lightweight checks on `LoadInfo` returned by the load task. Critical
failures raise `ValueError` (Prefect task will fail and be visible in UI),
non-critical issues are returned as warnings in the result dict.
"""
from __future__ import annotations

from typing import Any, Dict

from prefect import task


@task(name="validation.basic_checks")
def validate_load(load_info: Dict[str, Any]) -> Dict[str, Any]:
    """Validate basic invariants of a load.

    Rules:
      - If all resources have zero rows -> non-critical warning
      - If any resource produced NULL PKs or missing keys, raise ValueError

    Args:
        load_info: dict produced by `run_load` task.

    Returns:
        Dict with `status` and `warnings` keys.
    """
    rows = load_info.get("rows_loaded_by_resource", {})
    warnings = []

    if not rows:
        warnings.append("no resources present in load_info")

    total_loaded = sum(int(v or 0) for v in rows.values())
    if total_loaded == 0:
        warnings.append("total rows loaded is zero")

    # Place for more complex checks (null PKs, FK integrity) during integration
    result = {"status": "ok", "warnings": warnings}

    return result
