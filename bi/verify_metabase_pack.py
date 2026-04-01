from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests


def _load_pack_cards(pack_dir: Path) -> dict[str, dict[str, Any]]:
    cards_dir = pack_dir / "cards"
    cards: dict[str, dict[str, Any]] = {}
    for path in sorted(cards_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cards[payload["key"]] = payload
    return cards


def _load_pack_dashboards(pack_dir: Path) -> list[dict[str, Any]]:
    dashboards_dir = pack_dir / "dashboards"
    dashboards: list[dict[str, Any]] = []
    for path in sorted(dashboards_dir.glob("*.json")):
        dashboards.append(json.loads(path.read_text(encoding="utf-8")))
    return dashboards


def _auth_headers(base_url: str) -> dict[str, str]:
    api_key = os.getenv("METABASE_API_KEY")
    if api_key:
        return {"x-api-key": api_key, "Content-Type": "application/json"}

    email = os.getenv("MB_ADMIN_EMAIL")
    password = os.getenv("MB_ADMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError("Set METABASE_API_KEY or MB_ADMIN_EMAIL/MB_ADMIN_PASSWORD")

    session = requests.post(
        f"{base_url}/api/session",
        json={"username": email, "password": password},
        timeout=20,
    )
    session.raise_for_status()
    session_id = session.json()["id"]
    return {"X-Metabase-Session": session_id, "Content-Type": "application/json"}


def _extract_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        via = payload.get("via")
        if isinstance(via, list):
            for item in via:
                if isinstance(item, dict) and item.get("status") == "failed":
                    return str(item.get("error") or "query failed")
        if payload.get("status") == "failed":
            return str(payload.get("error") or "query failed")
    return None


def _extract_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    return []


def _mapping_kind(mapping: dict[str, Any]) -> str | None:
    target = mapping.get("target")
    if isinstance(target, list) and target:
        return str(target[0])
    return None


def _mapping_tag(mapping: dict[str, Any]) -> str | None:
    target = mapping.get("target")
    if (
        isinstance(target, list)
        and len(target) >= 2
        and isinstance(target[1], list)
        and len(target[1]) >= 2
    ):
        return str(target[1][1])
    return None


def _extract_template_tags(card_payload: dict[str, Any]) -> dict[str, Any]:
    dataset_query = card_payload.get("dataset_query")
    if not isinstance(dataset_query, dict):
        return {}
    native = dataset_query.get("native")
    if isinstance(native, dict):
        tags = native.get("template-tags")
        if isinstance(tags, dict):
            return tags
    stages = dataset_query.get("stages")
    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict):
                tags = stage.get("template-tags")
                if isinstance(tags, dict):
                    return tags
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate all Metabase cards in a pack by executing them"
    )
    parser.add_argument("--provider", default="metabase")
    parser.add_argument("--pack", default="process_metrics_v1")
    parser.add_argument(
        "--url", default=os.getenv("METABASE_URL", "http://localhost:3001")
    )
    args = parser.parse_args()

    pack_dir = Path(__file__).resolve().parent / "packs" / args.provider / args.pack
    if not pack_dir.exists():
        raise FileNotFoundError(f"Pack not found: {pack_dir}")

    headers = _auth_headers(args.url)
    cards_resp = requests.get(f"{args.url}/api/card", headers=headers, timeout=20)
    cards_resp.raise_for_status()
    cards = _extract_list(cards_resp.json())
    card_by_name = {c["name"]: int(c["id"]) for c in cards if "name" in c and "id" in c}

    pack_cards = _load_pack_cards(pack_dir)
    pack_dashboards = _load_pack_dashboards(pack_dir)

    dashboards_resp = requests.get(
        f"{args.url}/api/dashboard", headers=headers, timeout=20
    )
    dashboards_resp.raise_for_status()
    dashboards = _extract_list(dashboards_resp.json())
    dashboard_id_by_name = {
        str(item["name"]): int(item["id"])
        for item in dashboards
        if "name" in item and "id" in item
    }

    failures: list[str] = []
    for card_spec in pack_cards.values():
        card_name = str(card_spec["name"])
        card_id = card_by_name.get(card_name)
        if card_id is None:
            failures.append(f"missing card in Metabase: {card_name}")
            continue

        details_resp = requests.get(
            f"{args.url}/api/card/{card_id}",
            headers=headers,
            timeout=30,
        )
        details_resp.raise_for_status()
        live_card = details_resp.json()
        template_tags = _extract_template_tags(live_card)
        field_filters = card_spec.get("field_filters", {})
        if isinstance(field_filters, dict):
            for tag in field_filters.keys():
                tag_payload = template_tags.get(tag)
                if not isinstance(tag_payload, dict):
                    failures.append(f"card '{card_name}' missing template-tag '{tag}'")
                    continue
                if tag_payload.get("type") != "dimension":
                    failures.append(
                        f"card '{card_name}' template-tag '{tag}' is '{tag_payload.get('type')}', expected 'dimension'"
                    )

        response = requests.post(
            f"{args.url}/api/card/{card_id}/query",
            headers=headers,
            timeout=60,
        )
        if response.status_code not in (200, 202):
            failures.append(f"card '{card_name}' failed HTTP {response.status_code}")
            continue

        try:
            payload = response.json()
        except ValueError:
            failures.append(f"card '{card_name}' returned non-JSON response")
            continue

        error = _extract_error(payload)
        if error:
            failures.append(f"card '{card_name}' failed: {error}")

    for dashboard_spec in pack_dashboards:
        dashboard_name = str(dashboard_spec["name"])
        dashboard_id = dashboard_id_by_name.get(dashboard_name)
        if dashboard_id is None:
            failures.append(f"missing dashboard in Metabase: {dashboard_name}")
            continue
        dashboard_resp = requests.get(
            f"{args.url}/api/dashboard/{dashboard_id}",
            headers=headers,
            timeout=30,
        )
        dashboard_resp.raise_for_status()
        live_dashboard = dashboard_resp.json()
        dashcards_by_card_id = {
            int(item["card_id"]): item
            for item in live_dashboard.get("dashcards", [])
            if isinstance(item, dict) and item.get("card_id") is not None
        }

        filters_by_id: dict[str, dict[str, Any]] = {}
        for flt in dashboard_spec.get("filters", []):
            if isinstance(flt, dict) and "id" in flt:
                filters_by_id[str(flt["id"])] = flt

        for layout_item in dashboard_spec.get("layout", []):
            if not isinstance(layout_item, dict):
                continue
            card_key = str(layout_item.get("card_key"))
            card_spec = pack_cards.get(card_key)
            if card_spec is None:
                failures.append(
                    f"dashboard '{dashboard_name}' references unknown card key '{card_key}'"
                )
                continue
            card_name = str(card_spec["name"])
            card_id = card_by_name.get(card_name)
            if card_id is None:
                failures.append(
                    f"dashboard '{dashboard_name}' references missing card '{card_name}'"
                )
                continue
            live_dashcard = dashcards_by_card_id.get(card_id)
            if live_dashcard is None:
                failures.append(
                    f"dashboard '{dashboard_name}' missing dashcard for '{card_name}'"
                )
                continue

            filter_ids = layout_item.get("filter_ids", [])
            if not isinstance(filter_ids, list):
                continue
            field_filters = card_spec.get("field_filters", {})
            if not isinstance(field_filters, dict):
                field_filters = {}

            for filter_id in filter_ids:
                parameter_id = str(filter_id)
                filter_spec = filters_by_id.get(parameter_id, {})
                template_tag = str(
                    filter_spec.get(
                        "template_tag",
                        filter_spec.get("slug", parameter_id),
                    )
                )
                expected_kind = (
                    "dimension" if template_tag in field_filters else "variable"
                )
                mappings = live_dashcard.get("parameter_mappings", [])
                selected = None
                for item in mappings:
                    if (
                        isinstance(item, dict)
                        and str(item.get("parameter_id")) == parameter_id
                    ):
                        selected = item
                        break
                if selected is None:
                    failures.append(
                        f"dashboard '{dashboard_name}' card '{card_name}' missing mapping for parameter '{parameter_id}'"
                    )
                    continue
                actual_kind = _mapping_kind(selected)
                actual_tag = _mapping_tag(selected)
                if actual_kind != expected_kind:
                    failures.append(
                        f"dashboard '{dashboard_name}' card '{card_name}' parameter '{parameter_id}' mapped as '{actual_kind}', expected '{expected_kind}'"
                    )
                if actual_tag is not None and actual_tag != template_tag:
                    failures.append(
                        f"dashboard '{dashboard_name}' card '{card_name}' parameter '{parameter_id}' mapped to template-tag '{actual_tag}', expected '{template_tag}'"
                    )

    if failures:
        print("PACK VALIDATION FAILED")
        for item in failures:
            print(f" - {item}")
        raise SystemExit(1)

    print("PACK VALIDATION OK")


if __name__ == "__main__":
    main()
