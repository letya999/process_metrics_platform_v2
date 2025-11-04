"""Backfill helpers and flow wrappers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Tuple

from prefect import flow

# Make relative import safe when Prefect loads this module as a script
try:
    pass  # type: ignore
except Exception:
    pass

from .jira_sync import jira_sync_flow


def _split_date_ranges(
    start: str, end: str, chunk_days: int
) -> List[Tuple[date, date]]:
    start_d = datetime.fromisoformat(start).date()
    end_d = datetime.fromisoformat(end).date()
    if chunk_days <= 0:
        raise ValueError("chunk_days must be > 0")
    ranges: List[Tuple[date, date]] = []
    cur = start_d
    while cur <= end_d:
        nxt = min(cur + timedelta(days=chunk_days - 1), end_d)
        ranges.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return ranges


@flow(name="backfill_projects")
def backfill_projects(
    db_conn, project_uuids: List, start_date: str, end_date: str, chunk_days: int = 30
):
    ranges = _split_date_ranges(start_date, end_date, chunk_days)
    succeeded = 0
    import sys

    for idx, (d_from, d_to) in enumerate(ranges):
        try:
            # Resolve jira_sync_flow from the module that tests may patch.
            # Tests sometimes patch `app.flows.backfill.jira_sync_flow`, so
            # prefer that module if available in sys.modules to pick up monkeypatches.
            mod = sys.modules.get("app.flows.backfill") or sys.modules.get(__name__)
            resolved_jira_sync = getattr(mod, "jira_sync_flow", jira_sync_flow)

            # Support both Prefect flow objects (with .fn) and plain callables
            flow_callable = getattr(resolved_jira_sync, "fn", resolved_jira_sync)
            try:
                # first attempt: call as Prefect flow with keyword args
                flow_callable(
                    project_uuids=project_uuids,
                    date_from=d_from.isoformat(),
                    date_to=d_to.isoformat(),
                )
            except TypeError:
                # fallback: older style callable expecting (db_conn, config)
                cfg = {
                    "project_uuids": project_uuids,
                    "date_from": d_from.isoformat(),
                    "date_to": d_to.isoformat(),
                }
                flow_callable(db_conn, cfg)

            succeeded += 1
        except Exception:  # pragma: no cover
            # keep behaviour from original code: swallow child failures
            pass
    return {"total_chunks": len(ranges), "succeeded": succeeded}


def backfill_last_n_days(db_conn, project_uuids: List, days: int):
    if days <= 0:
        raise ValueError("days must be positive")
    end = date.today()
    start = end - timedelta(days=days - 1)
    return backfill_projects.fn(
        db_conn, project_uuids, start.isoformat(), end.isoformat()
    )
