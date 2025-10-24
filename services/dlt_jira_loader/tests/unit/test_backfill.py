from __future__ import annotations

from uuid import uuid4

import pytest

from services.dlt_jira_loader.flows import backfill


def test_split_date_ranges_even():
    ranges = backfill._split_date_ranges("2025-01-01", "2025-03-31", 30)
    # 90 days inclusive -> 3 chunks
    assert len(ranges) == 3
    assert ranges[0][0].isoformat() == "2025-01-01"


def test_split_date_ranges_small_chunk():
    ranges = backfill._split_date_ranges("2025-01-01", "2025-01-05", 2)
    assert len(ranges) == 3
    assert ranges[0][1].isoformat() == "2025-01-02"


def test_backfill_projects_invokes_jira_sync(monkeypatch):
    calls = []

    def fake_jira_sync(db_conn, config):
        calls.append(config)

    monkeypatch.setattr(
        "services.dlt_jira_loader.flows.backfill.jira_sync_flow", fake_jira_sync
    )

    db_conn = {"pipelines": []}
    project_uuids = [uuid4(), uuid4()]

    res = backfill.backfill_projects.fn(
        db_conn, project_uuids, "2025-01-01", "2025-01-10", chunk_days=5
    )
    assert res["total_chunks"] == 2
    assert res["succeeded"] == 2
    assert len(calls) == 2


def test_backfill_last_n_days_invalid():
    with pytest.raises(ValueError):
        backfill.backfill_last_n_days(None, [], -1)
