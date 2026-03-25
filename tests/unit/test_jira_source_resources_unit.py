from pipelines.assets.jira import raw


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_jira_source_issues_jql_and_pagination(monkeypatch):
    calls = []

    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        calls.append((url, params))
        if "search/jql" in url and len(calls) == 1:
            return _Resp(
                {
                    "issues": [
                        {
                            "id": "1",
                            "fields": {"updated": "2024-03-10T12:01:00.000+0000"},
                        }
                    ],
                    "isLast": False,
                    "nextPageToken": "next-1",
                }
            )
        if "search/jql" in url and len(calls) == 2:
            return _Resp(
                {
                    "issues": [
                        {
                            "id": "2",
                            "fields": {"updated": "2024-03-10T12:02:00.000+0000"},
                        }
                    ],
                    "isLast": True,
                }
            )
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=["AAA"])
    items = list(src.with_resources("issues"))

    assert [x["id"] for x in items] == ["1", "2"]
    assert "project in (AAA)" in calls[0][1]["jql"]
    assert calls[1][1]["nextPageToken"] == "next-1"


def test_jira_source_issues_updated_filter_and_missing_next_token(monkeypatch):
    calls = []
    original_incremental = raw.dlt.sources.incremental
    monkeypatch.setattr(
        raw.dlt.sources,
        "incremental",
        lambda *_a, **_k: original_incremental(
            "fields.updated", initial_value="2024-03-10T12:00:00.000+0000"
        ),
    )

    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        calls.append((url, params))
        return _Resp(
            {
                "issues": [
                    {"id": "1", "fields": {"updated": "2024-03-10T12:01:00.000+0000"}}
                ],
                "isLast": False,
            }
        )

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=["AAA"])
    items = list(src.with_resources("issues"))

    assert len(items) == 1
    assert "updated >=" in calls[0][1]["jql"]
    assert len(calls) == 1


def test_jira_source_projects_and_users(monkeypatch):
    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        if "project/search" in url:
            start_at = params.get("startAt", 0)
            if start_at == 0:
                return _Resp(
                    {
                        "values": [
                            {"id": "1", "key": "AAA"},
                            {"id": "2", "key": "BBB"},
                        ],
                        "isLast": False,
                    }
                )
            return _Resp({"values": [{"id": "3", "key": "AAA"}], "isLast": True})
        if "user/assignable/search" in url:
            start_at = params.get("startAt", 0)
            if start_at == 0:
                return _Resp([{"accountId": "U1"}] * 100)
            return _Resp([{"accountId": "U2"}])
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=["AAA"])

    projects = list(src.with_resources("projects"))
    users = list(src.with_resources("users"))

    assert [p["key"] for p in projects] == ["AAA", "AAA"]
    assert len(users) == 101
    assert users[-1]["accountId"] == "U2"


def test_jira_source_users_breaks_on_empty_page(monkeypatch):
    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        if "user/assignable/search" in url:
            return _Resp([])
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=["AAA"])
    users = list(src.with_resources("users"))
    assert users == []


def test_jira_source_sprints_handles_http_error(monkeypatch):
    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        if "/rest/agile/1.0/board" in url and "/sprint" not in url:
            return _Resp(
                {
                    "values": [
                        {
                            "id": 10,
                            "name": "Board 10",
                            "location": {"projectKey": "AAA"},
                        },
                        {
                            "id": 20,
                            "name": "Board 20",
                            "location": {"projectKey": "BBB"},
                        },
                    ]
                }
            )
        if "/board/10/sprint" in url:
            return _Resp({"values": [{"id": 1, "name": "S1"}], "isLast": True})
        if "/board/20/sprint" in url:
            raise raw.requests.HTTPError("board without sprints")
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=None)
    sprints = list(src.with_resources("sprints"))

    assert len(sprints) == 1
    assert sprints[0]["id"] == 1
    assert sprints[0]["board_id"] == 10
    assert sprints[0]["project_key"] == "AAA"


def test_jira_source_sprints_project_filter_and_pagination(monkeypatch):
    sprint_calls = []

    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        if "/rest/agile/1.0/board" in url and "/sprint" not in url:
            return _Resp(
                {
                    "values": [
                        {
                            "id": 10,
                            "name": "Board 10",
                            "location": {"projectKey": "AAA"},
                        },
                        {
                            "id": 20,
                            "name": "Board 20",
                            "location": {"projectKey": "BBB"},
                        },
                    ]
                }
            )
        if "/board/10/sprint" in url:
            sprint_calls.append(params["startAt"])
            if params["startAt"] == 0:
                return _Resp({"values": [{"id": 1, "name": "S1"}], "isLast": False})
            return _Resp({"values": [{"id": 2, "name": "S2"}], "isLast": True})
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=["AAA"])
    sprints = list(src.with_resources("sprints"))

    assert [s["id"] for s in sprints] == [1, 2]
    assert sprint_calls == [0, 50]


def test_jira_source_versions_board_configs_and_fields(monkeypatch):
    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        if "project/search" in url:
            return _Resp(
                {"values": [{"id": "1", "key": "AAA"}, {"id": "2", "key": "BBB"}]}
            )
        if "/project/AAA/versions" in url:
            return _Resp([{"id": "V1", "name": "1.0"}])
        if "/project/BBB/versions" in url:
            raise raw.requests.HTTPError("no versions")
        if "/rest/agile/1.0/board" in url and "/configuration" not in url:
            return _Resp(
                {
                    "values": [
                        {
                            "id": 10,
                            "name": "B10",
                            "type": "scrum",
                            "location": {"projectKey": "AAA"},
                        },
                        {
                            "id": 20,
                            "name": "B20",
                            "type": "kanban",
                            "location": {"projectKey": "BBB"},
                        },
                    ]
                }
            )
        if "/board/10/configuration" in url:
            return _Resp(
                {
                    "columnConfig": {"x": 1},
                    "filter": {"id": "f1"},
                    "subQuery": {"query": "q"},
                }
            )
        if "/board/20/configuration" in url:
            raise raw.requests.HTTPError("forbidden")
        if "/rest/api/3/field" in url:
            return _Resp([{"id": "customfield_1", "name": "Story Points"}])
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=None)

    versions = list(src.with_resources("versions"))
    board_cfgs = list(src.with_resources("board_configurations"))
    fields = list(src.with_resources("fields"))

    assert len(versions) == 1
    assert versions[0]["project_key"] == "AAA"
    assert len(board_cfgs) == 1
    assert board_cfgs[0]["board_id"] == 10
    assert len(fields) == 1
    assert fields[0]["id"] == "customfield_1"


def test_jira_source_versions_and_board_configs_project_filter(monkeypatch):
    called = {"versions": [], "configs": []}

    def _get(url, auth=None, params=None, timeout=None, **_kwargs):
        if "project/search" in url:
            return _Resp(
                {"values": [{"id": "1", "key": "AAA"}, {"id": "2", "key": "BBB"}]}
            )
        if "/project/AAA/versions" in url:
            called["versions"].append("AAA")
            return _Resp([{"id": "V1", "name": "1.0"}])
        if "/project/BBB/versions" in url:
            called["versions"].append("BBB")
            return _Resp([{"id": "V2", "name": "2.0"}])
        if "/rest/agile/1.0/board" in url and "/configuration" not in url:
            return _Resp(
                {
                    "values": [
                        {
                            "id": 10,
                            "name": "B10",
                            "type": "scrum",
                            "location": {"projectKey": "AAA"},
                        },
                        {
                            "id": 20,
                            "name": "B20",
                            "type": "kanban",
                            "location": {"projectKey": "BBB"},
                        },
                    ]
                }
            )
        if "/board/10/configuration" in url:
            called["configs"].append(10)
            return _Resp({"columnConfig": {}})
        if "/board/20/configuration" in url:
            called["configs"].append(20)
            return _Resp({"columnConfig": {}})
        if "/rest/api/3/field" in url:
            return _Resp([])
        raise AssertionError(url)

    monkeypatch.setattr(raw.requests, "get", _get)
    src = raw.jira_source("https://jira.local", "u@x", "t", projects=["AAA"])

    versions = list(src.with_resources("versions"))
    cfgs = list(src.with_resources("board_configurations"))

    assert len(versions) == 1
    assert versions[0]["project_key"] == "AAA"
    assert called["versions"] == ["AAA"]
    assert len(cfgs) == 1
    assert called["configs"] == [10]
