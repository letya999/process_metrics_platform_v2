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
            ("GET", "/api/database/7/metadata?include_hidden=true"): [{"tables": []}],
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
    mappings = MetabaseProvider._build_filter_mappings({}, 57, filters, set())
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
        },
        field_id_map={},
    )
    assert "template-tags" in payload
    assert payload["template-tags"]["project_key"]["type"] == "text"
    assert payload["template-tags"]["date_from"]["type"] == "date"


def test_template_tags_always_have_id_field() -> None:
    """Every template tag must have a non-blank id so Metabase can construct
    valid parameter objects when the question is accessed via direct URL."""
    provider = MetabaseProvider()
    payload = provider._build_native_query_payload(
        {
            "query": "SELECT 1 [[AND {{project_key}}]] [[AND {{date_range}}]] [[AND {{sprint_name}}]]",
            "field_filters": {
                "project_key": "metrics.v_facts.project_key",
                "date_range": "metrics.v_facts.full_date",
            },
        },
        field_id_map={
            "metrics.v_facts.project_key": 371,
            "metrics.v_facts.full_date": 375,
        },
    )
    tags = payload["template-tags"]
    for tag_name, tag_def in tags.items():
        tag_id = tag_def.get("id")
        assert tag_id, f"template tag '{tag_name}' missing id field"
        assert (
            isinstance(tag_id, str) and len(tag_id) == 8
        ), f"template tag '{tag_name}' id must be 8-char string, got {tag_id!r}"


def test_collect_required_field_paths_extracts_field_filters(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    cards_dir = pack_dir / "cards"
    cards_dir.mkdir(parents=True)
    (pack_dir / "dashboards").mkdir(parents=True)
    (cards_dir / "one.json").write_text(
        json.dumps(
            {
                "key": "one",
                "name": "One",
                "query": "SELECT 1",
                "field_filters": {
                    "project_key": "metrics.v_facts.project_key",
                    "issue_type": "metrics.v_facts.slice_value",
                },
            }
        ),
        encoding="utf-8",
    )
    (cards_dir / "two.json").write_text(
        json.dumps(
            {
                "key": "two",
                "name": "Two",
                "query": "SELECT 2",
            }
        ),
        encoding="utf-8",
    )

    paths = MetabaseProvider._collect_required_field_paths(pack_dir)
    assert paths == {"metrics.v_facts.project_key", "metrics.v_facts.slice_value"}


def test_build_native_query_payload_raises_when_field_filter_id_missing() -> None:
    provider = MetabaseProvider()
    with pytest.raises(
        RuntimeError, match="Field ID not found for field filter mapping"
    ):
        provider._build_native_query_payload(
            {
                "name": "Velocity",
                "query": "SELECT 1 [[AND {{project_key}}]]",
                "field_filters": {"project_key": "metrics.v_facts.project_key"},
            },
            field_id_map={},
            card_name="Velocity",
        )


# ---------------------------------------------------------------------------
# _param_id
# ---------------------------------------------------------------------------


def test_param_id_returns_8_char_hex() -> None:
    pid = MetabaseProvider._param_id("project_key")
    assert len(pid) == 8
    assert pid.isalnum()
    assert pid == pid.lower()


def test_param_id_is_deterministic() -> None:
    assert MetabaseProvider._param_id("date_range") == MetabaseProvider._param_id(
        "date_range"
    )


def test_param_id_differs_per_slug() -> None:
    assert MetabaseProvider._param_id("project_key") != MetabaseProvider._param_id(
        "date_range"
    )


# ---------------------------------------------------------------------------
# _normalize_filters
# ---------------------------------------------------------------------------


def test_normalize_filters_generates_8char_ids() -> None:
    spec = {
        "filters": [
            {
                "id": "project_key",
                "name": "Project Key",
                "slug": "project_key",
                "type": "category",
                "template_tag": "project_key",
            },
            {
                "id": "date_range",
                "name": "Date Range",
                "slug": "date_range",
                "type": "date/range",
                "template_tag": "date_range",
            },
        ]
    }
    filters = MetabaseProvider._normalize_filters(spec)
    assert len(filters) == 2
    for f in filters:
        assert len(f["id"]) == 8
        assert f["id"].isalnum()


def test_normalize_filters_id_is_deterministic() -> None:
    spec = {
        "filters": [{"id": "project_key", "slug": "project_key", "type": "category"}]
    }
    f1 = MetabaseProvider._normalize_filters(spec)
    f2 = MetabaseProvider._normalize_filters(spec)
    assert f1[0]["id"] == f2[0]["id"]


def test_normalize_filters_preserves_template_tag() -> None:
    spec = {
        "filters": [
            {
                "id": "sprint_name",
                "name": "Sprint Name",
                "slug": "sprint_name",
                "type": "category",
                "template_tag": "sprint_name",
            }
        ]
    }
    filters = MetabaseProvider._normalize_filters(spec)
    assert filters[0]["template_tag"] == "sprint_name"
    assert filters[0]["slug"] == "sprint_name"


def test_provision_dashboard_filter_ids_are_hashed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: PUT /api/dashboard must contain hashed 8-char parameter ids."""
    monkeypatch.setenv("METABASE_URL", "http://metabase:3000")
    monkeypatch.setenv("MB_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("MB_ADMIN_PASSWORD", "pass")

    pack_dir = tmp_path / "pack"
    (pack_dir / "cards").mkdir(parents=True)
    (pack_dir / "dashboards").mkdir(parents=True)

    (pack_dir / "collections.json").write_text(
        json.dumps([{"key": "main", "name": "Main"}]), encoding="utf-8"
    )
    (pack_dir / "cards" / "vel.json").write_text(
        json.dumps(
            {
                "key": "vel",
                "collection": "main",
                "name": "Velocity",
                "display": "table",
                "query": "SELECT 1 [[AND {{project_key}}]]",
                "field_filters": {"project_key": "metrics.v_facts.project_key"},
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "dashboards" / "dash.json").write_text(
        json.dumps(
            {
                "key": "dash",
                "collection": "main",
                "name": "Dash",
                "filters": [
                    {
                        "id": "project_key",
                        "name": "Project Key",
                        "slug": "project_key",
                        "type": "category",
                        "template_tag": "project_key",
                    }
                ],
                "layout": [
                    {
                        "card_key": "vel",
                        "row": 0,
                        "col": 0,
                        "size_x": 8,
                        "size_y": 4,
                        "filter_ids": ["project_key"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    expected_param_id = MetabaseProvider._param_id("project_key")
    field_id = 42

    provider = MetabaseProvider()
    fake = FakeMetabaseClient(
        responses={
            ("GET", "/api/session/properties"): [{}],
            ("POST", "/api/session"): [{"id": "sess"}],
            ("GET", "/api/database"): [[]],
            ("POST", "/api/database"): [{"id": 1}],
            ("POST", "/api/database/1/sync_schema"): [{}],
            ("GET", "/api/database/1/metadata?include_hidden=true"): [
                # first call: _wait_for_required_fields
                {
                    "tables": [
                        {
                            "schema": "metrics",
                            "name": "v_facts",
                            "fields": [{"name": "project_key", "id": field_id}],
                        }
                    ]
                },
                # second call: _upsert_cards -> _get_field_id_map
                {
                    "tables": [
                        {
                            "schema": "metrics",
                            "name": "v_facts",
                            "fields": [{"name": "project_key", "id": field_id}],
                        }
                    ]
                },
            ],
            ("GET", "/api/collection"): [[]],
            ("POST", "/api/collection"): [{"id": 10}],
            ("GET", "/api/card"): [[]],
            ("POST", "/api/card"): [{"id": 20}],
            ("GET", "/api/dashboard"): [[]],
            ("POST", "/api/dashboard"): [{"id": 30}],
            ("GET", "/api/dashboard/30"): [{"dashcards": []}],
            ("PUT", "/api/dashboard/30"): [{}],
        }
    )
    provider.client = fake

    provider.provision(pack_dir)

    put_payload = next(
        p for m, path, p in fake.calls if m == "PUT" and path == "/api/dashboard/30"
    )
    param_ids = [p["id"] for p in put_payload["parameters"]]
    assert param_ids == [
        expected_param_id
    ], f"Expected [{expected_param_id}], got {param_ids}"
    assert len(expected_param_id) == 8

    mapping_param_ids = [
        m["parameter_id"]
        for dc in put_payload["dashcards"]
        for m in dc["parameter_mappings"]
    ]
    assert mapping_param_ids == [expected_param_id]


# ---------------------------------------------------------------------------
# sprint_scope_change.json SQL
# ---------------------------------------------------------------------------

PACK_DIR = Path(__file__).parent.parent / "packs" / "metabase" / "process_metrics_v1"


def test_sprint_scope_change_has_default_6month_filter() -> None:
    card_path = PACK_DIR / "cards" / "sprint_scope_change.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert "CURRENT_DATE - INTERVAL '6 months'" in card["query"]
    assert "sprint_start_date" in card["query"]


def test_sprint_scope_change_default_filter_uses_comment_trick() -> None:
    card_path = PACK_DIR / "cards" / "sprint_scope_change.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    # The -- trick: when sprint_start_date is set, fallback is commented out
    assert (
        "{{sprint_start_date}} --" in card["query"]
        or "sprint_start_date}} -- ]]" in card["query"]
    )
