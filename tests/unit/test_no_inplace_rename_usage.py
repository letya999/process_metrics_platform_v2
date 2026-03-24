from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_DIRS = [REPO_ROOT / "pipelines", REPO_ROOT / "app"]
DISALLOWED_KWARGS = {"in_place", "inplace"}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for base_dir in SEARCH_DIRS:
        files.extend(base_dir.rglob("*.py"))
    return files


def test_no_rename_inplace_kwargs_used() -> None:
    violations: list[str] = []

    for file_path in _iter_python_files():
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "rename":
                continue

            bad_keywords = [
                kw.arg for kw in node.keywords if kw.arg in DISALLOWED_KWARGS
            ]
            if not bad_keywords:
                continue

            rel = file_path.relative_to(REPO_ROOT)
            violations.append(
                f"{rel}:{node.lineno} uses rename(..., {', '.join(bad_keywords)}=...)"
            )

    assert not violations, "Disallowed rename kwargs found:\n" + "\n".join(violations)
