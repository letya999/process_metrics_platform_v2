from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from services.dlt_jira_loader.app.models.config import ProjectWithCredentials
from services.dlt_jira_loader.app.utils import project_discovery


def _now_iso(days: int = 0) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(days=days))
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def test_prioritize_never_synced():
    p1 = ProjectWithCredentials(
        project_id=uuid4(), external_id="1", external_key="P1", credentials={}
    )
    p2 = ProjectWithCredentials(
        project_id=uuid4(),
        external_id="2",
        external_key="P2",
        credentials={"last_synced_at": _now_iso(10)},
    )
    p3 = ProjectWithCredentials(
        project_id=uuid4(),
        external_id="3",
        external_key="P3",
        credentials={"last_synced_at": _now_iso(30)},
    )

    ordered = project_discovery.prioritize_never_synced([p2, p3, p1])
    # p1 (never synced) should be first
    assert ordered[0].external_key == "P1"
    # followed by oldest last_synced (30 days), then 10 days
    assert ordered[1].external_key == "P3"
    assert ordered[2].external_key == "P2"


def test_filter_by_age_min_max():
    p_never = ProjectWithCredentials(
        project_id=uuid4(), external_id="1", external_key="NEV", credentials={}
    )
    p_old = ProjectWithCredentials(
        project_id=uuid4(),
        external_id="2",
        external_key="OLD",
        credentials={"last_synced_at": _now_iso(100)},
    )
    p_recent = ProjectWithCredentials(
        project_id=uuid4(),
        external_id="3",
        external_key="REC",
        credentials={"last_synced_at": _now_iso(2)},
    )

    projects = [p_never, p_old, p_recent]

    # min_age_days=30 -> include never and old only
    filtered = project_discovery.filter_by_age(projects, min_age_days=30)
    keys = {p.external_key for p in filtered}
    assert keys == {"NEV", "OLD"}

    # max_age_days=7 -> include never and recent only
    filtered2 = project_discovery.filter_by_age(projects, max_age_days=7)
    keys2 = {p.external_key for p in filtered2}
    assert keys2 == {"NEV", "REC"}


def test_fetch_active_projects_with_in_memory_fixture():
    # db_conn as dict with 'projects' key supported
    # by utils.db.fetch_projects_with_credentials
    sample = {
        "projects": [
            {
                "project_id": uuid4(),
                "external_id": "10",
                "external_key": "A",
                "is_active": True,
                "credentials": {},
            },
            {
                "project_id": uuid4(),
                "external_id": "11",
                "external_key": "B",
                "is_active": False,
                "credentials": {},
            },
        ]
    }

    res = project_discovery.fetch_active_projects(sample)
    assert len(res) == 1
    assert res[0].external_key == "A"
