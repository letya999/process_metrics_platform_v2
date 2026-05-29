"""Repository policy checks for docs and deployment manifests."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = [
    ROOT / "README.md",
    ROOT / "SECURITY.md",
]
COMPOSE_FILES = [
    ROOT / "docker-compose.yml",
    ROOT / "docker-compose.prod.yml",
]
REQUIRED_MAKE_REFERENCES = [
    "scripts/run_validation.py",
]
DISALLOWED_MAKE_REFERENCES = [
    "docker-compose.simple.yml",
    ".env.production",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    for path in DOC_FILES:
        if not path.exists():
            continue
        text = _read(path)
        if "your-org" in text:
            failures.append(f"{path.name}: placeholder 'your-org' is not allowed")

    latest_pattern = re.compile(r"image:\s*[^\s]+:latest\b")
    for path in COMPOSE_FILES:
        if not path.exists():
            continue
        text = _read(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if latest_pattern.search(line):
                failures.append(
                    f"{path.name}:{idx}: mutable ':latest' tag is not allowed"
                )

    makefile_path = ROOT / "Makefile"
    if makefile_path.exists():
        makefile = _read(makefile_path)
        for needle in REQUIRED_MAKE_REFERENCES:
            if needle not in makefile:
                failures.append(f"Makefile: missing required reference '{needle}'")
        for needle in DISALLOWED_MAKE_REFERENCES:
            if needle in makefile:
                failures.append(
                    f"Makefile: disallowed stale reference '{needle}' found"
                )

        # Ensure Makefile does not reference missing compose/env manifests.
        references = re.findall(
            r"(docker-compose[^\s'\"]+\.yml|\.env[^\s'\"]*)",
            makefile,
        )
        for ref in sorted(set(references)):
            if ref.startswith(".env") and ref in {
                ".env",
                ".env.example",
                ".env.prod",
                ".env.prod.example",
            }:
                continue
            if not (ROOT / ref).exists():
                failures.append(f"Makefile: referenced file does not exist: {ref}")

    if failures:
        print("[POLICY] FAILED")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[POLICY] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
