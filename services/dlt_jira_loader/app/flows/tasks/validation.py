"""Validation tasks for load results."""
from __future__ import annotations

from typing import Any, Dict

from prefect import task


@task
def validate_load(load_info: Dict[str, Any]) -> Dict[str, Any]:
    """Validate basic invariants of a DLT load result-like mapping.

    Expected input example:
        {"rows_loaded_by_resource": {"issues": 10, "boards": 1}}
    """
    status = "ok"
    warnings = []

    resources = (
        load_info.get("rows_loaded_by_resource")
        if isinstance(load_info, dict)
        else None
    )
    if resources is None:
        warnings.append("no resources present in load_info")
        return {"status": status, "warnings": warnings}

    # resources present but empty dict -> total==0
    total = sum(int(v or 0) for v in resources.values())
    if total == 0:
        warnings.append("total rows loaded is zero")

    return {"status": status, "warnings": warnings}
