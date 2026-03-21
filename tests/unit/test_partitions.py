"""Unit tests for dynamic project partition helpers."""

from unittest.mock import MagicMock

from dagster import SensorResult, SkipReason

import pipelines.partitions as partitions


def test_get_project_partition_keys_reads_env_fallback(monkeypatch):
    monkeypatch.delenv("JIRA_PROJECTS", raising=False)
    monkeypatch.setenv("JIRA_PROJECTS", " ADS , , MKT,CORE ")

    def _raise():
        raise RuntimeError("config module unavailable")

    import config

    monkeypatch.setattr(config, "get_enabled_projects", _raise)

    keys = partitions.get_project_partition_keys()
    assert keys == ["ADS", "MKT", "CORE"]


def test_sync_project_partitions_sensor_skips_when_no_projects(monkeypatch):
    monkeypatch.setattr(partitions, "get_project_partition_keys", lambda: [])
    context = _mock_context(existing_keys=[])

    events = partitions.sync_project_partitions_sensor._evaluation_fn(context)

    assert len(events) == 1
    assert isinstance(events[0], SkipReason)
    assert "No projects configured" in events[0].skip_message


def test_sync_project_partitions_sensor_adds_new_partitions(monkeypatch):
    monkeypatch.setattr(
        partitions, "get_project_partition_keys", lambda: ["ADS", "MKT"]
    )
    context = _mock_context(existing_keys=["ADS"])

    events = partitions.sync_project_partitions_sensor._evaluation_fn(context)

    assert len(events) == 1
    assert isinstance(events[0], SensorResult)
    context.instance.add_dynamic_partitions.assert_called_once()
    kwargs = context.instance.add_dynamic_partitions.call_args.kwargs
    assert kwargs["partitions_def_name"] == "jira_projects"
    assert kwargs["partition_keys"] == ["MKT"]


def test_sync_project_partitions_sensor_returns_skip_on_error(monkeypatch):
    monkeypatch.setattr(partitions, "get_project_partition_keys", lambda: ["ADS"])
    context = _mock_context(existing_keys=[])
    context.instance.get_dynamic_partitions = MagicMock(
        side_effect=RuntimeError("db down")
    )

    events = partitions.sync_project_partitions_sensor._evaluation_fn(context)

    assert len(events) == 1
    assert isinstance(events[0], SkipReason)
    assert "Error syncing partitions" in events[0].skip_message


def test_ensure_project_partitions_exist_adds_only_missing(monkeypatch):
    monkeypatch.setattr(
        partitions, "get_project_partition_keys", lambda: ["ADS", "MKT"]
    )
    context = _mock_context(existing_keys=["ADS"])

    partitions.ensure_project_partitions_exist(context)

    context.instance.add_dynamic_partitions.assert_called_once()
    kwargs = context.instance.add_dynamic_partitions.call_args.kwargs
    assert kwargs["partitions_def_name"] == "jira_projects"
    assert kwargs["partition_keys"] == ["MKT"]


def test_ensure_project_partitions_exist_handles_exception(monkeypatch):
    monkeypatch.setattr(partitions, "get_project_partition_keys", lambda: ["ADS"])
    context = _mock_context(existing_keys=[])
    context.instance.get_dynamic_partitions = MagicMock(
        side_effect=RuntimeError("broken state")
    )

    partitions.ensure_project_partitions_exist(context)

    context.log.warning.assert_called_once()


def _mock_context(existing_keys):
    instance = MagicMock()
    instance.get_dynamic_partitions.return_value = existing_keys
    log = MagicMock()
    return MagicMock(instance=instance, log=log)
