"""Run ruff/black only on changed Python files."""

from __future__ import annotations

import shutil
import subprocess
import sys


def _changed_python_files() -> list[str]:
    git_bin = shutil.which("git")
    if not git_bin:
        raise RuntimeError("git executable not found in PATH")

    out = subprocess.check_output(  # noqa: S603 - local trusted developer workflow
        [
            git_bin,
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            "HEAD",
            "--",
            "*.py",
        ],
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    files = _changed_python_files()
    if not files:
        print("No changed Python files.")
        return 0

    print("Changed Python files:")
    for path in files:
        print(path)

    ruff_rc = subprocess.call(  # noqa: S603 - local trusted developer workflow
        [sys.executable, "-m", "ruff", "check", *files]
    )
    if ruff_rc != 0:
        return ruff_rc

    black_rc = subprocess.call(  # noqa: S603 - local trusted developer workflow
        [sys.executable, "-m", "black", "--check", *files]
    )
    return black_rc


if __name__ == "__main__":
    raise SystemExit(main())
