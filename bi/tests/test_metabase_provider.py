from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bi.providers.metabase.provider import MetabaseProvider
from bi.registry import get_provider


class FakeMetabaseClient:
    def __init__(self, responses: dict[tuple[str, str], list[Any]]):
        self.responses = responses
        self.calls: list[tuple[str, str, Any]] = []
        self.wait_called = False
        self.auth_mode: tuple[str, str] | None = None

    def wait_for_health(self, max_wait_seconds: int = 300) -> None:
        self.wait_called = True

    def with_api_key(self, api_key: str) -> None:
        self.auth_mode = ("api_key", api_key)

    def with_session(self, session_id: str) -> None:
        self.auth_mode = ("session", session_id)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | list[Any] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> Any:
        key = (method, path)
        self.calls.append((method, path, json_body))
        if key not in self.responses or not self.responses[key]:
            raise AssertionError(f"Unexpected request: {key}")
        return self.responses[key].pop(0)


@pytest.fixture
def temp_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "pack"
    (pack_dir / "cards").mkdir(parents=True)
    (pack_dir / "dashboards").mkdir(parents=True)

    (pack_dir / "collections.json").write_text(
        json.dumps(
            [
                {
                    "key": "process_metrics",
                    "name": "Process Metrics",
                    "description": "Test collection",
                }
            ]
        ),
        encoding="utf-8",
    )

    (pack_dir / "cards" / "velocity.json").write_text(
        json.dumps(
            {
                "key": "velocity",
                "collection": "process_metrics",
                "name": "Velocity Test",
                "display": "table",
                "query": "SELECT 1 AS value",
            }
        ),
        encoding="utf-8",
    )

    (pack_dir / "dashboards" / "overview.json").write_text(
        json.dumps(
            {
                "key": "overview",
                "collection": "process_metrics",
                "name": "Overview",
                "layout": [
                    {
                        "card_key": "velocity",
                        "row": 0,
                        "col": 0,
                        "size_x": 8,
                        "size_y": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    return pack_dir


def test_registry_returns_metabase_provider() -> None:
    provider = get_provider("metabase")
    assert provider.name == "metabase"


def test_registry_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported BI provider"):
        get_provider("unknown")


def test_provision_pack_happy_path(
    monkeypatch: pytest.MonkeyPatch, temp_pack: Path
) -> None:
    monkeypatch.setenv("METABASE_URL", "http://metabase:3000")
    monkeypatch.setenv("MB_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("MB_ADMIN_PASSWORD", "StrongPassword123!")

    provider = MetabaseProvider()
    fake = FakeMetabaseClient(
        responses={
            ("GET", "/api/session/properties"): [{"setup-token": "setup-1"}],
            ("POST", "/api/setup"): [{"ok": True}],
            ("POST", "/api/session"): [{"id": "session-1"}],
            ("GET", "/api/database"): [[]],
            ("POST", "/api/database"): [{"id": 7}],
            ("POST", "/api/database/7/sync_schema"): [{"ok": True}],
            ("GET", "/api/collection"): [[]],
            ("POST", "/api/collection"): [{"id": 11}],
            ("GET", "/api/card"): [[]],
            ("POST", "/api/card"): [{"id": 21}],
            ("GET", "/api/dashboard"): [[]],
            ("POST", "/api/dashboard"): [{"id": 31}],
            ("GET", "/api/dashboard/31"): [{"dashcards": []}],
            ("PUT", "/api/dashboard/31"): [{"ok": True}],
        }
    )
    provider.client = fake

    provider.provision(temp_pack)

    assert fake.wait_called is True
    assert fake.auth_mode == ("session", "session-1")

    put_calls = [
        payload
        for method, path, payload in fake.calls
        if method == "PUT" and path == "/api/dashboard/31"
    ]
    assert len(put_calls) == 1
    put_payload = put_calls[0]
    assert put_payload is not None
    assert put_payload["dashcards"][0]["card_id"] == 21


def test_api_key_auth_skips_setup_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METABASE_API_KEY", "api-key-1")

    provider = MetabaseProvider()
    fake = FakeMetabaseClient(responses={})
    provider.client = fake

    provider._bootstrap_and_authenticate()

    assert fake.auth_mode == ("api_key", "api-key-1")
    assert fake.calls == []


def test_extract_list_supports_data_wrapper() -> None:
    payload = {"data": [{"id": 1, "name": "db1"}]}
    items = MetabaseProvider._extract_list(payload)
    assert items == [{"id": 1, "name": "db1"}]


def test_validate_pack_rejects_missing_card_query(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    (pack_dir / "cards").mkdir(parents=True)
    (pack_dir / "dashboards").mkdir(parents=True)

    (pack_dir / "cards" / "broken.json").write_text(
        json.dumps(
            {
                "key": "broken",
                "name": "Broken Card",
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "dashboards" / "overview.json").write_text(
        json.dumps({"name": "Overview", "layout": []}),
        encoding="utf-8",
    )

    provider = MetabaseProvider()
    with pytest.raises(ValueError, match="missing required keys"):
        provider._validate_pack(pack_dir)


def test_validate_pack_rejects_broken_layout(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    (pack_dir / "cards").mkdir(parents=True)
    (pack_dir / "dashboards").mkdir(parents=True)

    (pack_dir / "cards" / "ok.json").write_text(
        json.dumps({"key": "ok", "name": "OK Card", "query": "SELECT 1"}),
        encoding="utf-8",
    )
    (pack_dir / "dashboards" / "broken.json").write_text(
        json.dumps(
            {
                "name": "Overview",
                "layout": [{"card_key": "ok", "row": 0, "col": 0, "size_x": 8}],
            }
        ),
        encoding="utf-8",
    )

    provider = MetabaseProvider()
    with pytest.raises(ValueError, match="layout\\[0\\] missing keys"):
        provider._validate_pack(pack_dir)


def test_build_dashboard_parameters_from_filters() -> None:
    filters = [
        {
            "id": "project_key",
            "name": "Project Key",
            "slug": "project_key",
            "type": "category",
            "template_tag": "project_key",
        }
    ]
    params = MetabaseProvider._build_dashboard_parameters(filters)
    assert params == [
        {
            "id": "project_key",
            "name": "Project Key",
            "slug": "project_key",
            "type": "category",
        }
    ]


def test_build_filter_mappings_for_card_uses_template_tags() -> None:
    filters = [
        {
            "id": "project_key",
            "name": "Project Key",
            "slug": "project_key",
            "type": "category",
            "template_tag": "project_key",
        },
        {
            "id": "date_from",
            "name": "Date From",
            "slug": "date_from",
            "type": "date/single",
            "template_tag": "date_from",
        },
    ]
    mappings = MetabaseProvider._build_filter_mappings({}, 57, filters)
    assert mappings == [
        {
            "parameter_id": "project_key",
            "card_id": 57,
            "target": ["variable", ["template-tag", "project_key"]],
        },
        {
            "parameter_id": "date_from",
            "card_id": 57,
            "target": ["variable", ["template-tag", "date_from"]],
        },
    ]


def test_build_native_query_payload_infers_template_tags() -> None:
    provider = MetabaseProvider()
    payload = provider._build_native_query_payload(
        {
            "query": "SELECT * FROM metrics.v_facts WHERE 1=1 [[ AND project_key = {{project_key}} ]] [[ AND full_date >= {{date_from}} ]]",
        }
    )
    assert "template-tags" in payload
    assert payload["template-tags"]["project_key"]["type"] == "text"
    assert payload["template-tags"]["date_from"]["type"] == "date"
