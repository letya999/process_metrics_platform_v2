from datetime import datetime
from uuid import UUID

from services.dlt_jira_loader.flows.tasks import sync_window
from services.dlt_jira_loader.models.config import JiraSyncConfig


def test_determine_window_explicit_dates():
    cfg = JiraSyncConfig(
        project_uuids=[UUID("11111111-1111-1111-1111-111111111111")],
        date_from="2025-01-01T00:00:00",
        date_to="2025-01-02T00:00:00",
    )

    res = sync_window.determine_window.fn(cfg, None)

    assert res["date_from"] == "2025-01-01T00:00:00Z"
    assert res["date_to"] == "2025-01-02T00:00:00Z"


def test_determine_window_uses_checkpoint_overlap():
    cfg = JiraSyncConfig(project_uuids=[UUID("22222222-2222-2222-2222-222222222222")])
    checkpoint = {"last_synced_at": "2025-01-01T00:00:00"}

    res = sync_window.determine_window.fn(cfg, checkpoint)

    # checkpoint last_synced_at minus 5 minutes
    assert res["date_from"] == "2024-12-31T23:55:00Z"
    # date_to should be present and end with Z
    assert res["date_to"].endswith("Z")


def test_determine_window_default_lookback(monkeypatch):
    # freeze "now" to verify default lookback of 90 days
    fixed_now = datetime(2025, 10, 20, 12, 0, 0)

    class FakeDateTime:
        @staticmethod
        def utcnow():
            return fixed_now

        @staticmethod
        def fromisoformat(s: str):
            return datetime.fromisoformat(s)

    monkeypatch.setattr(sync_window, "datetime", FakeDateTime)

    cfg = JiraSyncConfig(project_uuids=[UUID("33333333-3333-3333-3333-333333333333")])
    res = sync_window.determine_window.fn(cfg, None)

    # expected from = fixed_now - 90 days
    expected_from = (
        fixed_now - sync_window.timedelta(days=sync_window.DEFAULT_LOOKBACK_DAYS)
    ).replace(microsecond=0).isoformat() + "Z"
    assert res["date_from"] == expected_from
    assert res["date_to"] == fixed_now.replace(microsecond=0).isoformat() + "Z"
