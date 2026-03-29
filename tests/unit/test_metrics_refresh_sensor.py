from datetime import datetime, timezone
from types import SimpleNamespace

from dagster import RunRequest, SkipReason

from pipelines.jobs import schedules


def _evaluate(context):
    return schedules.guarded_hourly_metrics_refresh_sensor._raw_fn(
        context
    )  # noqa: SLF001


class _FakeContext:
    def __init__(self, cursor=None, run_records=None):
        self.cursor = cursor
        self._updated_cursor = None
        self.instance = SimpleNamespace(
            get_run_records=lambda **_kwargs: run_records or []
        )

    def update_cursor(self, value):
        self.cursor = value
        self._updated_cursor = value


def _patch_now(monkeypatch, dt: datetime):
    class _FakeDateTime:
        @classmethod
        def now(cls, _tz=None):
            return dt

    monkeypatch.setattr(schedules, "datetime", _FakeDateTime)


def test_metrics_sensor_skips_outside_hour_boundary(monkeypatch):
    _patch_now(monkeypatch, datetime(2026, 3, 28, 10, 15, tzinfo=timezone.utc))
    context = _FakeContext()

    event = _evaluate(context)

    assert isinstance(event, SkipReason)


def test_metrics_sensor_skips_when_clean_or_sync_is_active(monkeypatch):
    _patch_now(monkeypatch, datetime(2026, 3, 28, 11, 0, tzinfo=timezone.utc))
    active = [
        SimpleNamespace(
            dagster_run=SimpleNamespace(job_name="jira_sync_job", run_id="run-1")
        )
    ]
    context = _FakeContext(run_records=active)

    event = _evaluate(context)

    assert isinstance(event, SkipReason)
    assert "active" in event.skip_message


def test_metrics_sensor_requests_run_when_safe(monkeypatch):
    _patch_now(monkeypatch, datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc))
    context = _FakeContext()

    event = _evaluate(context)

    assert isinstance(event, RunRequest)
    assert event.run_key == "metrics-refresh-2026-03-28T12"
    assert context._updated_cursor == "2026-03-28T12"
