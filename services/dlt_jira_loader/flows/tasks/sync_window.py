"""Prefect task: compute synchronization window for a project sync.

This module implements a small, well-typed helper used by the Prefect flows
to determine `date_from`/`date_to` for an individual project run.

Rules implemented (Phase 4, Task 10):
- explicit params have highest priority
- checkpoint-based window uses last_synced_at with an overlap (5 minutes)
- default window is 90 days
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from prefect import task

from services.dlt_jira_loader.models.config import JiraSyncConfig

OVERLAP_MINUTES = 5
DEFAULT_LOOKBACK_DAYS = 90


@task(name="sync_window.determine_window")
def determine_window(
    config: JiraSyncConfig,
    checkpoint: Optional[Dict] = None,
) -> Dict[str, str]:
    """Return a dict with ISO `date_from` and `date_to` for the sync.

    Args:
        config: run-level config; explicit `date_from`/`date_to` override defaults.
        checkpoint: optional dict representing last checkpoint row.
            May contain `last_synced_at`.

    Returns:
        Dict with keys `date_from`, `date_to` (ISO 8601 strings, UTC, Z suffix).
    """
    # prefer timezone-aware now; support test monkeypatch that may replace
    # the datetime module with a FakeDateTime implementing utcnow()
    try:
        now = datetime.now(timezone.utc)
    except Exception:
        now = datetime.utcnow()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

    # date_to priority: explicit config -> now
    date_to = config.date_to if getattr(config, "date_to", None) else None
    if date_to is None:
        date_to_dt = now
    else:
        # expecting ISO string from config
        date_to_dt = datetime.fromisoformat(date_to)
        if date_to_dt.tzinfo is None:
            date_to_dt = date_to_dt.replace(tzinfo=timezone.utc)

    # date_from priority: explicit config -> checkpoint.last_synced_at - overlap
    # or default lookback
    date_from = config.date_from if getattr(config, "date_from", None) else None
    if date_from:
        date_from_dt = datetime.fromisoformat(date_from)
        if date_from_dt.tzinfo is None:
            date_from_dt = date_from_dt.replace(tzinfo=timezone.utc)
    elif checkpoint and checkpoint.get("last_synced_at"):
        try:
            last = datetime.fromisoformat(checkpoint.get("last_synced_at"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception:
            last = now - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        date_from_dt = last - timedelta(minutes=OVERLAP_MINUTES)
    else:
        date_from_dt = now - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    # normalize to ISO Z
    # produce UTC Z-suffixed format used across the project
    iso_from = (
        date_from_dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    iso_to = (
        date_to_dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    return {"date_from": iso_from, "date_to": iso_to}
