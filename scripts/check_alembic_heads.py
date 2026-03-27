"""Verify that Alembic has exactly one head revision."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cmd = [
        "docker",
        "compose",
        "--profile",
        "migration",
        "run",
        "--rm",
        "alembic",
        "heads",
    ]
    try:
        result = subprocess.run(  # noqa: S603 - local trusted workflow
            cmd,
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print("[ALEMBIC] FAILED to query heads")
        if exc.stdout:
            print(exc.stdout.strip())
        if exc.stderr:
            print(exc.stderr.strip())
        return exc.returncode or 1

    output = (result.stdout or "").strip()
    head_count = len(re.findall(r"\(head\)", output))
    if head_count != 1:
        print(f"[ALEMBIC] FAILED: expected 1 head, found {head_count}")
        print(output)
        return 1

    print("[ALEMBIC] OK: exactly one head")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
