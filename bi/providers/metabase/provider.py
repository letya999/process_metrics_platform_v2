from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from bi.providers.metabase.client import MetabaseClient

logger = logging.getLogger(__name__)


class MetabaseProvider:
    """Provisioner for Metabase dashboard packs."""

    name = "metabase"
    _TAG_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def __init__(self) -> None:
        self.base_url = os.getenv("METABASE_URL", "http://metabase:3000")
        self.api_key = os.getenv("METABASE_API_KEY")
        self.admin_email = os.getenv("MB_ADMIN_EMAIL", "admin@example.com")
        self.admin_password = os.getenv("MB_ADMIN_PASSWORD", "StrongPassword123!")
        self.site_name = os.getenv("MB_SITE_NAME", "Process Metrics Platform")

        self.target_db_name = os.getenv("BI_DATABASE_NAME", "Process Metrics DB")
        self.target_db_engine = os.getenv("BI_DATABASE_ENGINE", "postgres")
        self.target_db_schema = os.getenv("BI_DATABASE_SCHEMA", "metrics")
        self.target_db_ssl = os.getenv("BI_DATABASE_SSL", "false").lower() == "true"

        self.pg_host = os.getenv("POSTGRES_HOST", "postgres")
        self.pg_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.pg_db = os.getenv("POSTGRES_DB", "process_metrics")
        self.pg_user = os.getenv("POSTGRES_USER", "postgres")
        self.pg_password = os.getenv("POSTGRES_PASSWORD", "postgres")

        self.client = MetabaseClient(self.base_url)

    def provision(self, pack_dir: Path) -> None:
        """Provision collections, cards, and dashboards from a pack directory."""
        logger.info("Provisioning Metabase from pack: %s", pack_dir)
        self._validate_pack(pack_dir)
        required_field_paths = self._collect_required_field_paths(pack_dir)
        self.client.wait_for_health()

        self._bootstrap_and_authenticate()

        db_id = self._ensure_database()
        self._wait_for_required_fields(db_id, required_field_paths)
        collection_ids = self._ensure_collections(pack_dir)
        card_ids, card_field_filter_tags = self._upsert_cards(
            pack_dir, db_id, collection_ids
        )
        self._upsert_dashboards(
            pack_dir, collection_ids, card_ids, card_field_filter_tags
        )

        logger.info("Metabase provisioning finished")

    def _bootstrap_and_authenticate(self) -> None:
        """Authenticate using API key, or bootstrap/login via admin credentials."""
        if self.api_key:
            self.client.with_api_key(self.api_key)
            logger.info("Using METABASE_API_KEY for authentication")
            return

        setup_props = self.client.request("GET", "/api/session/properties")
        setup_token = setup_props.get("setup-token")

        if setup_token:
            logger.info(
                "Metabase first-run setup detected, creating admin and initial DB"
            )
            payload = {
                "token": setup_token,
                "user": {
                    "first_name": "Admin",
                    "last_name": "User",
                    "email": self.admin_email,
                    "password": self.admin_password,
                },
                "prefs": {
                    "site_name": self.site_name,
                    "allow_tracking": False,
                },
                "database": {
                    "engine": self.target_db_engine,
                    "name": self.target_db_name,
                    "details": {
                        "host": self.pg_host,
                        "port": self.pg_port,
                        "dbname": self.pg_db,
                        "user": self.pg_user,
                        "password": self.pg_password,
                        "schema": self.target_db_schema,
                        "ssl": self.target_db_ssl,
                    },
                },
            }
            self.client.request(
                "POST",
                "/api/setup",
                json_body=payload,
                expected_statuses=(200, 403),
            )

        session = self.client.request(
            "POST",
            "/api/session",
            json_body={
                "username": self.admin_email,
                "password": self.admin_password,
            },
            expected_statuses=(200,),
        )
        self.client.with_session(session["id"])
        logger.info("Authenticated with Metabase session")

    def _ensure_database(self) -> int:
        """Ensure a target analytics database exists in Metabase and return its id."""
        databases = self._extract_list(self.client.request("GET", "/api/database"))

        for db in databases:
            if db.get("name") == self.target_db_name:
                db_id = int(db["id"])
                self._sync_database(db_id)
                return db_id

        payload = {
            "name": self.target_db_name,
            "engine": self.target_db_engine,
            "details": {
                "host": self.pg_host,
                "port": self.pg_port,
                "dbname": self.pg_db,
                "user": self.pg_user,
                "password": self.pg_password,
                "schema": self.target_db_schema,
                "ssl": self.target_db_ssl,
            },
            "is_full_sync": True,
        }
        created = self.client.request(
            "POST", "/api/database", json_body=payload, expected_statuses=(200,)
        )
        db_id = int(created["id"])
        self._sync_database(db_id)
        return db_id

    def _sync_database(self, db_id: int) -> None:
        """Trigger a schema sync for a Metabase database id."""
        self.client.request(
            "POST",
            f"/api/database/{db_id}/sync_schema",
            expected_statuses=(200, 202),
        )

    @staticmethod
    def _collect_required_field_paths(pack_dir: Path) -> set[str]:
        """Collect all field filter column paths required by pack cards."""
        cards_dir = pack_dir / "cards"
        required: set[str] = set()
        if not cards_dir.exists():
            return required
        for card_path in sorted(cards_dir.glob("*.json")):
            payload = json.loads(card_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            field_filters = payload.get("field_filters", {})
            if not isinstance(field_filters, dict):
                continue
            for column_path in field_filters.values():
                if isinstance(column_path, str) and column_path.strip():
                    required.add(column_path.strip())
        return required

    def _wait_for_required_fields(
        self, db_id: int, required_field_paths: set[str]
    ) -> None:
        """Wait until all required field paths are present in Metabase metadata."""
        if not required_field_paths:
            return
        timeout_seconds = int(os.getenv("BI_FIELD_SYNC_TIMEOUT_SECONDS", "300"))
        poll_seconds = int(os.getenv("BI_FIELD_SYNC_POLL_SECONDS", "5"))
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            field_map = self._get_field_id_map(db_id)
            missing = sorted(
                path for path in required_field_paths if path not in field_map
            )
            if not missing:
                return
            logger.info(
                "Waiting for Metabase field metadata: db_id=%s missing=%s",
                db_id,
                ", ".join(missing[:8]),
            )
            time.sleep(poll_seconds)
        raise RuntimeError(
            "Timed out waiting for Metabase field metadata. "
            f"db_id={db_id}, missing paths: {sorted(required_field_paths)}"
        )

    def _ensure_collections(self, pack_dir: Path) -> dict[str, int | None]:
        """Create missing collections defined by the pack and return key->id mapping."""
        collections_by_name = {
            c["name"]: c["id"]
            for c in self._extract_list(self.client.request("GET", "/api/collection"))
        }
        collection_ids: dict[str, int | None] = {"root": None}

        collections_path = pack_dir / "collections.json"
        if not collections_path.exists():
            return collection_ids

        collections = self._load_json_list(collections_path)
        for spec in collections:
            key = spec["key"]
            name = spec["name"]
            parent_key = spec.get("parent", "root")
            parent_id = collection_ids.get(parent_key)

            existing_id = collections_by_name.get(name)
            if existing_id is not None:
                collection_ids[key] = int(existing_id)
                continue

            payload = {
                "name": name,
                "description": spec.get("description") or f"Collection for {name}",
                "parent_id": parent_id,
            }
            created = self.client.request(
                "POST", "/api/collection", json_body=payload, expected_statuses=(200,)
            )
            collection_ids[key] = int(created["id"])

        return collection_ids

    @staticmethod
    def _safe_viz_settings(viz: dict) -> dict:
        """Filter out problematic visualization settings for Metabase API."""
        # column_settings with arbitrary column name keys causes Metabase v0.58 500 error.
        # All other standard keys (graph.dimensions, graph.metrics, stackable, etc.) are safe.
        BLOCKED_KEYS = {"column_settings"}
        return {k: v for k, v in viz.items() if k not in BLOCKED_KEYS}

    def _get_field_id_map(self, db_id: int) -> dict[str, int]:
        """Return map of 'schema.table.column' -> field_id from Metabase DB metadata."""
        try:
            metadata = self.client.request(
                "GET", f"/api/database/{db_id}/metadata?include_hidden=true"
            )
        except Exception:
            logger.warning("Failed to fetch metadata for database %s", db_id)
            return {}

        field_map: dict[str, int] = {}
        for table in metadata.get("tables", []):
            schema = table.get("schema") or "public"
            tname = table.get("name", "")
            for field in table.get("fields", []):
                key = f"{schema}.{tname}.{field['name']}"
                field_map[key] = int(field["id"])
                # Also store without schema prefix for convenience
                field_map[f"{tname}.{field['name']}"] = int(field["id"])
        return field_map

    def _upsert_cards(
        self,
        pack_dir: Path,
        database_id: int,
        collection_ids: dict[str, int | None],
    ) -> tuple[dict[str, int], dict[str, set[str]]]:
        """Upsert cards by name from pack specs and return (key->card_id, key->field_filter_tags)."""
        cards_dir = pack_dir / "cards"
        card_specs = sorted(cards_dir.glob("*.json"))
        if not card_specs:
            return {}, {}

        existing_cards = self._extract_list(self.client.request("GET", "/api/card"))
        existing_by_name = {card["name"]: card for card in existing_cards}

        field_id_map = self._get_field_id_map(database_id)
        card_ids: dict[str, int] = {}
        card_field_filter_tags: dict[str, set[str]] = {}

        for path in card_specs:
            spec = self._load_json_object(path)
            name = spec["name"]
            card_key = spec["key"]
            collection_key = spec.get("collection", "root")
            collection_id = collection_ids.get(collection_key)

            native_payload = self._build_native_query_payload(
                spec,
                field_id_map,
                card_name=name,
            )
            # Collect tags that are dimensions (field filters)
            field_filter_tags = {
                tag
                for tag, tag_def in native_payload.get("template-tags", {}).items()
                if tag_def.get("type") == "dimension"
            }
            card_field_filter_tags[card_key] = field_filter_tags

            payload: dict[str, Any] = {
                "name": name,
                "description": spec.get("description") or f"Metrics for {name}",
                "display": spec.get("display", "table"),
                "collection_id": collection_id,
                "dataset_query": {
                    "database": database_id,
                    "type": "native",
                    "native": native_payload,
                },
                "visualization_settings": self._safe_viz_settings(
                    spec.get("visualization_settings", {})
                ),
            }

            if name in existing_by_name:
                existing_id = int(existing_by_name[name]["id"])
                self.client.request(
                    "PUT",
                    f"/api/card/{existing_id}",
                    json_body=payload,
                    expected_statuses=(200,),
                )
                card_ids[card_key] = existing_id
                continue

            created = self.client.request(
                "POST", "/api/card", json_body=payload, expected_statuses=(200,)
            )
            card_ids[card_key] = int(created["id"])

        return card_ids, card_field_filter_tags

    def _upsert_dashboards(
        self,
        pack_dir: Path,
        collection_ids: dict[str, int | None],
        card_ids: dict[str, int],
        card_field_filter_tags: dict[str, set[str]] | None = None,
    ) -> None:
        """Upsert dashboards and place cards according to pack layout specs."""
        dashboards_dir = pack_dir / "dashboards"
        dashboard_specs = sorted(dashboards_dir.glob("*.json"))
        if not dashboard_specs:
            return

        card_field_filter_tags = card_field_filter_tags or {}
        existing_dashboards = self._extract_list(
            self.client.request("GET", "/api/dashboard")
        )
        existing_by_name = {
            dash["name"]: int(dash["id"]) for dash in existing_dashboards
        }

        for path in dashboard_specs:
            spec = self._load_json_object(path)
            dashboard_name = spec["name"]
            collection_key = spec.get("collection", "root")
            collection_id = collection_ids.get(collection_key)
            dashboard_filters = self._normalize_filters(spec)

            dashboard_id = existing_by_name.get(dashboard_name)
            if dashboard_id is None:
                created = self.client.request(
                    "POST",
                    "/api/dashboard",
                    json_body={
                        "name": dashboard_name,
                        "description": spec.get("description")
                        or f"Metrics for {dashboard_name}",
                        "collection_id": collection_id,
                    },
                    expected_statuses=(200,),
                )
                dashboard_id = int(created["id"])

            current = self.client.request("GET", f"/api/dashboard/{dashboard_id}")
            existing_dashcards = current.get("dashcards", [])
            existing_by_card_id = {
                int(d["card_id"]): int(d["id"])
                for d in existing_dashcards
                if d.get("card_id")
            }

            dashcards_payload: list[dict[str, Any]] = []
            next_temp_dashcard_id = -1
            for item in spec.get("layout", []):
                key = item["card_key"]
                if key not in card_ids:
                    raise RuntimeError(
                        f"Dashboard '{dashboard_name}' references unknown card key '{key}'"
                    )

                card_id = card_ids[key]
                field_filter_tags = card_field_filter_tags.get(key, set())
                dashcard: dict[str, Any] = {
                    "card_id": card_id,
                    "row": item["row"],
                    "col": item["col"],
                    "size_x": item["size_x"],
                    "size_y": item["size_y"],
                    "parameter_mappings": item.get("parameter_mappings")
                    or self._build_filter_mappings(
                        item, card_id, dashboard_filters, field_filter_tags
                    ),
                    "visualization_settings": self._safe_viz_settings(
                        item.get("visualization_settings", {})
                    ),
                }
                if card_id in existing_by_card_id:
                    dashcard["id"] = existing_by_card_id[card_id]
                else:
                    dashcard["id"] = next_temp_dashcard_id
                    next_temp_dashcard_id -= 1
                dashcards_payload.append(dashcard)

            update_payload = {
                "name": dashboard_name,
                "description": spec.get("description")
                or f"Metrics for {dashboard_name}",
                "collection_id": collection_id,
                "parameters": spec.get("parameters", [])
                or self._build_dashboard_parameters(dashboard_filters),
                "dashcards": dashcards_payload,
            }

            try:
                self.client.request(
                    "PUT",
                    f"/api/dashboard/{dashboard_id}",
                    json_body=update_payload,
                    expected_statuses=(200,),
                )
            except RuntimeError:
                logger.warning(
                    "Modern dashboard upsert failed for '%s', falling back to legacy card placement API",
                    dashboard_name,
                )
                self._apply_legacy_dashboard_layout(
                    dashboard_id=dashboard_id,
                    existing_dashcards=existing_dashcards,
                    layout_spec=spec.get("layout", []),
                    card_ids=card_ids,
                )

    def _apply_legacy_dashboard_layout(
        self,
        dashboard_id: int,
        existing_dashcards: list[dict[str, Any]],
        layout_spec: list[dict[str, Any]],
        card_ids: dict[str, int],
    ) -> None:
        """Fallback layout placement flow for older Metabase dashboard APIs."""
        for dashcard in existing_dashcards:
            dashcard_id = dashcard.get("id")
            if dashcard_id is None:
                continue
            self.client.request(
                "DELETE",
                f"/api/dashboard/{dashboard_id}/cards/{dashcard_id}",
                expected_statuses=(200, 202, 204),
            )

        for item in layout_spec:
            key = item["card_key"]
            if key not in card_ids:
                raise RuntimeError(
                    f"Dashboard references unknown card key '{key}' in legacy layout path"
                )
            self.client.request(
                "POST",
                f"/api/dashboard/{dashboard_id}/cards",
                json_body={
                    "cardId": card_ids[key],
                    "row": item["row"],
                    "col": item["col"],
                    "sizeX": item["size_x"],
                    "sizeY": item["size_y"],
                },
                expected_statuses=(200,),
            )

    @staticmethod
    def _extract_list(payload: Any) -> list[dict[str, Any]]:
        """Normalize Metabase list responses: either raw list or {'data': [...]}."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]
        return []

    @staticmethod
    def _load_json_object(path: Path) -> dict[str, Any]:
        """Load JSON file and ensure top-level object."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object in {path}")
        return payload

    @staticmethod
    def _load_json_list(path: Path) -> list[dict[str, Any]]:
        """Load JSON file and ensure top-level list of objects."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise ValueError(f"Expected JSON list of objects in {path}")
        return payload

    def _validate_pack(self, pack_dir: Path) -> None:
        """Validate pack files and required schema keys before API calls."""
        cards_dir = pack_dir / "cards"
        dashboards_dir = pack_dir / "dashboards"
        if not cards_dir.exists():
            raise ValueError(f"Pack is missing cards directory: {cards_dir}")
        if not dashboards_dir.exists():
            raise ValueError(f"Pack is missing dashboards directory: {dashboards_dir}")

        required_card_keys = {"key", "name", "query"}
        for card_path in sorted(cards_dir.glob("*.json")):
            card = self._load_json_object(card_path)
            missing = required_card_keys - set(card.keys())
            if missing:
                raise ValueError(
                    f"Card spec {card_path} is missing required keys: {sorted(missing)}"
                )
            template_tags = card.get("template_tags")
            if template_tags is not None and not isinstance(template_tags, dict):
                raise ValueError(
                    f"Card spec {card_path} template_tags must be an object"
                )

        required_layout_keys = {"card_key", "row", "col", "size_x", "size_y"}
        for dashboard_path in sorted(dashboards_dir.glob("*.json")):
            dashboard = self._load_json_object(dashboard_path)
            for top in ("name", "layout"):
                if top not in dashboard:
                    raise ValueError(
                        f"Dashboard spec {dashboard_path} is missing required key: {top}"
                    )
            if not isinstance(dashboard["layout"], list):
                raise ValueError(f"Dashboard spec {dashboard_path} has non-list layout")
            for idx, item in enumerate(dashboard["layout"]):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"Dashboard spec {dashboard_path} layout[{idx}] must be an object"
                    )
                missing = required_layout_keys - set(item.keys())
                if missing:
                    raise ValueError(
                        f"Dashboard spec {dashboard_path} layout[{idx}] missing keys: {sorted(missing)}"
                    )
            filters = dashboard.get("filters", [])
            if filters and not isinstance(filters, list):
                raise ValueError(
                    f"Dashboard spec {dashboard_path} filters must be a list"
                )
            for filter_idx, filter_spec in enumerate(filters):
                if not isinstance(filter_spec, dict):
                    raise ValueError(
                        f"Dashboard spec {dashboard_path} filters[{filter_idx}] must be an object"
                    )
                missing_filter = {"id", "type"} - set(filter_spec.keys())
                if missing_filter:
                    raise ValueError(
                        f"Dashboard spec {dashboard_path} filters[{filter_idx}] missing keys: {sorted(missing_filter)}"
                    )

    @staticmethod
    def _param_id(slug: str) -> str:
        """Generate deterministic 8-char hex ID from a slug for Metabase parameter IDs.

        Metabase v0.47+ requires parameter ids to be 8-char alphanumeric strings.
        Using md5 keeps the mapping stable across re-provisions.
        """
        return hashlib.md5(slug.encode(), usedforsecurity=False).hexdigest()[:8]

    @staticmethod
    def _normalize_filters(spec: dict[str, Any]) -> list[dict[str, Any]]:
        raw = spec.get("filters", [])
        if not isinstance(raw, list):
            return []
        filters: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug") or str(item["id"])
            parameter_id = MetabaseProvider._param_id(slug)
            filters.append(
                {
                    "id": parameter_id,
                    "type": item["type"],
                    "name": item.get("name", slug),
                    "slug": slug,
                    "template_tag": item.get("template_tag", slug),
                    "default": item.get("default"),
                }
            )
        return filters

    @staticmethod
    def _build_dashboard_parameters(
        filters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parameters: list[dict[str, Any]] = []
        for item in filters:
            payload: dict[str, Any] = {
                "id": item["id"],
                "name": item["name"],
                "slug": item["slug"],
                "type": item["type"],
            }
            if item.get("default") is not None:
                payload["default"] = item["default"]
            parameters.append(payload)
        return parameters

    @staticmethod
    def _build_filter_mappings(
        layout_item: dict[str, Any],
        card_id: int,
        filters: list[dict[str, Any]],
        field_filter_tags: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not filters:
            return []
        field_filter_tags = field_filter_tags or set()
        filter_ids = layout_item.get("filter_ids")
        selected = (
            [flt for flt in filters if flt["id"] in set(filter_ids)]
            if isinstance(filter_ids, list)
            else filters
        )
        mappings: list[dict[str, Any]] = []
        for flt in selected:
            tag = flt["template_tag"]
            if tag in field_filter_tags:
                target = ["dimension", ["template-tag", tag]]
            else:
                target = ["variable", ["template-tag", tag]]
            mappings.append(
                {
                    "parameter_id": flt["id"],
                    "card_id": card_id,
                    "target": target,
                }
            )
        return mappings

    def _build_native_query_payload(
        self,
        card_spec: dict[str, Any],
        field_id_map: dict[str, int] | None = None,
        card_name: str = "<unknown>",
    ) -> dict[str, Any]:
        query = str(card_spec["query"])
        payload: dict[str, Any] = {"query": query}
        tags = sorted(set(self._TAG_PATTERN.findall(query)))
        if tags:
            payload["template-tags"] = self._build_template_tags(
                tags=tags,
                configured=card_spec.get("template_tags", {}),
                field_filters=card_spec.get("field_filters", {}),
                field_id_map=field_id_map or {},
                card_name=card_name,
            )
        return payload

    @staticmethod
    def _build_template_tags(
        tags: list[str],
        configured: dict[str, Any],
        field_filters: dict[str, str] | None = None,
        field_id_map: dict[str, int] | None = None,
        card_name: str = "<unknown>",
    ) -> dict[str, dict[str, Any]]:
        field_filters = field_filters or {}
        field_id_map = field_id_map or {}
        template_tags: dict[str, dict[str, Any]] = {}

        for tag in tags:
            cfg = configured.get(tag, {}) if isinstance(configured, dict) else {}

            # Check if this tag should be a Field Filter (dimension type)
            if tag in field_filters:
                column_path = field_filters[tag]  # e.g. "metrics.v_facts.project_key"
                field_id = field_id_map.get(column_path) or field_id_map.get(
                    column_path.split(".", 1)[-1]
                )

                # Determine widget type from tag name
                if tag.endswith("_date") or tag.startswith("date_") or "date" in tag:
                    widget_type = cfg.get("widget_type", "date/range")
                else:
                    widget_type = cfg.get("widget_type", "category")

                tag_def: dict[str, Any] = {
                    "name": tag,
                    "display-name": cfg.get(
                        "display_name", tag.replace("_", " ").title()
                    ),
                    "type": "dimension",
                    "widget-type": widget_type,
                    "required": bool(cfg.get("required", False)),
                }
                if field_id is not None:
                    tag_def["dimension"] = ["field", field_id, None]
                else:
                    raise RuntimeError(
                        "Field ID not found for field filter mapping: "
                        f"card='{card_name}', tag='{tag}', column='{column_path}'. "
                        "Run schema sync and retry provisioning."
                    )
                template_tags[tag] = tag_def
                continue

            tag_type = cfg.get("type")
            if tag_type is None:
                if (
                    tag.startswith("date_")
                    or tag.endswith("_date")
                    or ("date" in tag and tag.endswith(("_from", "_to")))
                ):
                    tag_type = "date"
                elif tag.endswith("_id"):
                    tag_type = "number"
                else:
                    tag_type = "text"
            template_tags[tag] = {
                "name": tag,
                "display-name": cfg.get("display_name", tag.replace("_", " ").title()),
                "type": tag_type,
                "required": bool(cfg.get("required", False)),
            }
        return template_tags
