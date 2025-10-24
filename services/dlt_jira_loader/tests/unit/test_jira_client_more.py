import pytest

from services.dlt_jira_loader.clients.jira_client import JiraClient, JiraHTTPError


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


def make_client_with_resp(resp: FakeResp):
    import requests

    # monkeypatch by replacing Session constructor on the module
    original_session = requests.Session
    requests.Session = lambda: FakeSession(resp)
    try:
        client = JiraClient("https://example.atlassian.net", api_token="t", email="e")
    finally:
        requests.Session = original_session
    return client


def test_search_issues_returns_json():
    resp = FakeResp(200, json_data={"issues": [1, 2, 3]})
    client = make_client_with_resp(resp)
    res = client.search_issues("project=X")
    assert res["issues"] == [1, 2, 3]


def test_get_sprints_and_versions_and_comments_and_find_boards():
    resp = FakeResp(200, json_data={"values": ["a"]})
    client = make_client_with_resp(resp)

    # get_sprints should return the json
    assert client.get_sprints(1)["values"] == ["a"]

    # get_project_versions
    resp2 = FakeResp(200, json_data=[{"id": "v1"}])
    client2 = make_client_with_resp(resp2)
    assert client2.get_project_versions("PRJ")[0]["id"] == "v1"

    # get_comments
    resp3 = FakeResp(200, json_data={"comments": []})
    client3 = make_client_with_resp(resp3)
    assert isinstance(client3.get_comments("KEY-1"), dict)

    # find_boards with project_key present -> should return whatever _get returns
    resp4 = FakeResp(200, json_data={"values": []})
    client4 = make_client_with_resp(resp4)
    assert client4.find_boards(project_key="PRJ").get("values") == []


def test_wrappers_raise_on_http_error():
    resp = FakeResp(404, json_data={"error": "x"}, text="not")
    client = make_client_with_resp(resp)
    with pytest.raises(JiraHTTPError):
        client.get_sprints(1)
