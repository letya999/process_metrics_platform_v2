import os
import types

import pytest

from pipelines.assets.jira import raw


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


class _DummyLog:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("info", str(msg)))

    def warning(self, msg):
        self.messages.append(("warning", str(msg)))

    def error(self, msg):
        self.messages.append(("error", str(msg)))


class _DummyContext:
    def __init__(self, partition_key=None):
        self.log = _DummyLog()
        self.partition_key = partition_key


def test_run_jira_pipeline_sets_dlt_env_and_returns_metadata(monkeypatch):
    monkeypatch.setenv("DAGSTER_POSTGRES_HOST", "pg-host")
    monkeypatch.setenv("DAGSTER_POSTGRES_PORT", "5544")
    monkeypatch.setenv("DAGSTER_POSTGRES_DB", "pm_db")
    monkeypatch.setenv("DAGSTER_POSTGRES_USER", "pm_user")
    monkeypatch.setenv("DAGSTER_POSTGRES_PASSWORD", "pm_pwd")
    monkeypatch.setattr(raw, "jira_source", lambda **kwargs: ("fake_source", kwargs))

    class _LoadInfo:
        def __init__(self):
            self.load_packages = [types.SimpleNamespace(jobs={"issues": 12})]

        def __str__(self):
            return "loaded"

    class _Pipeline:
        pipeline_name = "jira_raw_test"
        destination = "postgres"
        dataset_name = "raw_jira"

        def run(self, source):
            self.source = source
            return _LoadInfo()

    monkeypatch.setattr(raw.dlt, "pipeline", lambda **_k: _Pipeline())

    out = raw.run_jira_pipeline(
        base_url="https://jira.local",
        email="user@local",
        api_token="token",
        projects=["ABC"],
        pipeline_name="jira_raw_test",
    )

    assert out["pipeline_name"] == "jira_raw_test"
    assert out["row_counts"] == {"issues": 12}
    assert os.environ["DESTINATION__POSTGRES__CREDENTIALS__HOST"] == "pg-host"
    assert os.environ["DESTINATION__POSTGRES__CREDENTIALS__PORT"] == "5544"
    assert os.environ["DESTINATION__POSTGRES__CREDENTIALS__DATABASE"] == "pm_db"
    assert os.environ["DESTINATION__POSTGRES__CREDENTIALS__USERNAME"] == "pm_user"
    assert os.environ["DESTINATION__POSTGRES__CREDENTIALS__PASSWORD"] == "pm_pwd"


def test_raw_jira_data_success_from_env(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.local")
    monkeypatch.setenv("JIRA_USER_EMAIL", "user@local")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_PROJECTS", "AAA, BBB")

    calls = []

    def _run_pipeline(**kwargs):
        calls.append(kwargs)
        return {"load_info": "ok", "pipeline_name": kwargs["pipeline_name"]}

    monkeypatch.setattr(raw, "run_jira_pipeline", _run_pipeline)
    fake_config = types.SimpleNamespace(
        get_config=lambda: (_ for _ in ()).throw(RuntimeError("no config")),
        get_project_keys=lambda: [],
    )
    monkeypatch.setitem(__import__("sys").modules, "config", fake_config)

    ctx = _DummyContext()
    out = _asset_fn(raw.raw_jira_data)(ctx)

    assert out["status"] == "success"
    assert out["projects_synced"] == 2
    assert calls[0]["projects"] == ["AAA"]
    assert calls[1]["projects"] == ["BBB"]


def test_raw_jira_data_raises_when_project_sync_fails(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.local")
    monkeypatch.setenv("JIRA_USER_EMAIL", "user@local")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_PROJECTS", "AAA")
    monkeypatch.setattr(
        raw,
        "run_jira_pipeline",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        _asset_fn(raw.raw_jira_data)(_DummyContext())


def test_raw_jira_project_data_branches(monkeypatch):
    if not hasattr(raw, "raw_jira_project_data"):
        pytest.skip("Partitioned raw Jira asset is unavailable in this environment")

    class _Project:
        def __init__(self, key, enabled=True):
            self.key = key
            self.enabled = enabled
            self.jira_instance = "default"

    class _Instance:
        base_url = "https://jira.local"
        email = "user@local"

        @staticmethod
        def get_api_token():
            return "token"

    class _Config:
        def __init__(self, project):
            self._project = project

        def get_project(self, _key):
            return self._project

        def get_project_instance(self, _project):
            return _Instance()

    fake_config = types.SimpleNamespace(get_config=lambda: _Config(None))
    monkeypatch.setitem(__import__("sys").modules, "config", fake_config)

    ctx_not_found = _DummyContext(partition_key="MISSING")
    out_not_found = _asset_fn(raw.raw_jira_project_data)(ctx_not_found)
    assert out_not_found["reason"].startswith("project_not_found")

    fake_config.get_config = lambda: _Config(_Project("AAA", enabled=False))
    ctx_disabled = _DummyContext(partition_key="AAA")
    out_disabled = _asset_fn(raw.raw_jira_project_data)(ctx_disabled)
    assert out_disabled["reason"] == "project_disabled"

    fake_config.get_config = lambda: _Config(_Project("AAA", enabled=True))
    monkeypatch.setattr(
        raw,
        "run_jira_pipeline",
        lambda **kwargs: {"status": "ok", "pipeline_name": kwargs["pipeline_name"]},
    )
    ctx_success = _DummyContext(partition_key="AAA")
    out_success = _asset_fn(raw.raw_jira_project_data)(ctx_success)
    assert out_success["status"] == "ok"
    assert out_success["pipeline_name"] == "jira_raw_AAA"


def test_raw_jira_project_data_fallback_env_missing_credentials(monkeypatch):
    if not hasattr(raw, "raw_jira_project_data"):
        pytest.skip("Partitioned raw Jira asset is unavailable in this environment")

    fake_config = types.SimpleNamespace(
        get_config=lambda: (_ for _ in ()).throw(RuntimeError("no config"))
    )
    monkeypatch.setitem(__import__("sys").modules, "config", fake_config)
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    out = _asset_fn(raw.raw_jira_project_data)(_DummyContext(partition_key="AAA"))
    assert out == {"status": "error", "reason": "credentials_not_configured"}


def test_raw_jira_project_data_fallback_env_pipeline_failure(monkeypatch):
    if not hasattr(raw, "raw_jira_project_data"):
        pytest.skip("Partitioned raw Jira asset is unavailable in this environment")

    fake_config = types.SimpleNamespace(
        get_config=lambda: (_ for _ in ()).throw(RuntimeError("no config"))
    )
    monkeypatch.setitem(__import__("sys").modules, "config", fake_config)
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.local")
    monkeypatch.setenv("JIRA_USER_EMAIL", "user@local")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setattr(
        raw,
        "run_jira_pipeline",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("fail")),
    )

    with pytest.raises(RuntimeError, match="fail"):
        _asset_fn(raw.raw_jira_project_data)(_DummyContext(partition_key="AAA"))
