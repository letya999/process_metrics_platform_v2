import pytest

from services.dlt_jira_loader.app.clients.jira_client import (
    JiraClient,
    JiraHTTPError,
    resolve_from_env_or_config,
)


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, resp: FakeResp):
        self._resp = resp
        self.auth = None
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        return self._resp


def test_get_success(monkeypatch):
    resp = FakeResp(status_code=200, json_data={"ok": True})
    monkeypatch.setattr("requests.Session", lambda: FakeSession(resp))

    client = JiraClient("https://example.atlassian.net", api_token="t", email="e")
    res = client._get("/rest/api/3/some")
    assert res == {"ok": True}


def test_get_raises_on_error(monkeypatch):
    resp = FakeResp(status_code=404, json_data={"err": "not"}, text="not found")
    monkeypatch.setattr("requests.Session", lambda: FakeSession(resp))

    client = JiraClient("https://example.atlassian.net", api_token="t", email="e")
    with pytest.raises(JiraHTTPError) as exc:
        client._get("/rest/api/3/missing")
    assert "404" in str(exc.value)


def test_resolve_from_env_or_config(tmp_path, monkeypatch):
    cfg = {"k1": "value_from_cfg"}

    # prefer config value
    assert resolve_from_env_or_config(cfg, "k1", "ENV_K1") == "value_from_cfg"

    # fallback to env
    monkeypatch.delenv("ENV_K2", raising=False)
    monkeypatch.setenv("ENV_K2", "value_from_env")
    assert resolve_from_env_or_config({}, "k2", "ENV_K2") == "value_from_env"

    # missing both -> ValueError
    monkeypatch.delenv("ENV_X", raising=False)
    with pytest.raises(ValueError):
        resolve_from_env_or_config({}, "x", "ENV_X")
