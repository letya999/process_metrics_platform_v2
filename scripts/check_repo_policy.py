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
    ROOT / "docker-compose.simple.yml",
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
        if "scripts/run_validation.py" not in makefile:
            failures.append(
                "Makefile: validate target must call scripts/run_validation.py"
            )

    if failures:
        print("[POLICY] FAILED")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[POLICY] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
