from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from services.dlt_jira_loader.app.models.config import ProjectWithCredentials
from services.dlt_jira_loader.app.utils.db import fetch_projects_with_credentials


def _parse_last_synced_iso(iso_str: str) -> datetime:
    # expects format like '2025-01-01T00:00:00Z'
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def prioritize_never_synced(
    projects: Iterable[ProjectWithCredentials],
) -> List[ProjectWithCredentials]:
    items = list(projects)

    def key(p: ProjectWithCredentials):
        last = (p.credentials or {}).get("last_synced_at")
        if not last:
            return (0, datetime.min.replace(tzinfo=timezone.utc))
        return (1, _parse_last_synced_iso(last))

    return sorted(items, key=key)


def filter_by_age(
    projects: Iterable[ProjectWithCredentials],
    min_age_days: Optional[int] = None,
    max_age_days: Optional[int] = None,
) -> List[ProjectWithCredentials]:
    now = datetime.now(timezone.utc)
    out: List[ProjectWithCredentials] = []

    for p in projects:
        last = (p.credentials or {}).get("last_synced_at")
        if not last:
            out.append(p)
            continue

        last_dt = _parse_last_synced_iso(last)
        age_days = (now - last_dt).days

        if min_age_days is not None and age_days < min_age_days:
            continue
        if max_age_days is not None and age_days > max_age_days:
            continue

        out.append(p)

    return out


def fetch_active_projects(db_conn) -> List[ProjectWithCredentials]:
    rows = fetch_projects_with_credentials(db_conn)
    active = [r for r in rows if r.get("is_active", True)]
    return [ProjectWithCredentials(**r) for r in active]
