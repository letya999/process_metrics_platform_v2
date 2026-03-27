"""Run a minimal pytest smoke suite for pre-commit/pre-push quality gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tests = [
        "tests/unit/test_app_main.py",
        "tests/unit/test_definitions.py",
        "tests/unit/test_streamlit_admin_client.py",
    ]
    cmd = [sys.executable, "-m", "pytest", "-q", *tests]
    print("[SMOKE] Running:", " ".join(tests))
    return subprocess.call(cmd, cwd=root)  # noqa: S603 - local developer workflow


if __name__ == "__main__":
    raise SystemExit(main())
