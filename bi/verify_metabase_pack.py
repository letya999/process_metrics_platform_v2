from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests


def _load_pack_card_names(pack_dir: Path) -> list[str]:
    cards_dir = pack_dir / "cards"
    names: list[str] = []
    for path in sorted(cards_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        names.append(payload["name"])
    return names


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
    cards = cards_resp.json()
    card_by_name = {c["name"]: int(c["id"]) for c in cards if "name" in c and "id" in c}

    failures: list[str] = []
    for card_name in _load_pack_card_names(pack_dir):
        card_id = card_by_name.get(card_name)
        if card_id is None:
            failures.append(f"missing card in Metabase: {card_name}")
            continue

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

    if failures:
        print("PACK VALIDATION FAILED")
        for item in failures:
            print(f" - {item}")
        raise SystemExit(1)

    print("PACK VALIDATION OK")


if __name__ == "__main__":
    main()
