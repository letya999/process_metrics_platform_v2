from __future__ import annotations

import ast
from pathlib import Path

from dagster import AssetCheckResult, AssetCheckSeverity, asset_check

from .refresh import metrics_all

REQUIRED_METADATA_KEYS = {"grain", "unit", "calculation_logic"}


def _is_metrics_asset(decorator: ast.expr) -> bool:
    if not isinstance(decorator, ast.Call):
        return False

    func = decorator.func
    if not isinstance(func, ast.Name) or func.id != "asset":
        return False

    for kw in decorator.keywords:
        if kw.arg == "group_name" and isinstance(kw.value, ast.Constant):
            return kw.value.value == "metrics"
    return False


def _extract_metadata_keys(node: ast.Dict) -> set[str]:
    keys: set[str] = set()
    for key_node in node.keys:
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            keys.add(key_node.value)
    return keys


def _validate_metrics_asset_metadata() -> list[str]:
    metrics_dir = Path(__file__).resolve().parent
    issues: list[str] = []

    for path in sorted(metrics_dir.glob("*.py")):
        if path.name in {"__init__.py", "metadata_checks.py"}:
            continue

        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue

            asset_decorator: ast.Call | None = None
            for decorator in node.decorator_list:
                if _is_metrics_asset(decorator):
                    asset_decorator = decorator
                    break

            if asset_decorator is None:
                continue

            description_ok = False
            metadata_keys: set[str] = set()

            for kw in asset_decorator.keywords:
                if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str) and kw.value.value.strip():
                        description_ok = True
                if kw.arg == "metadata" and isinstance(kw.value, ast.Dict):
                    metadata_keys = _extract_metadata_keys(kw.value)

            if not description_ok:
                issues.append(f"{path.name}:{node.name}: missing non-empty description")

            missing_keys = sorted(REQUIRED_METADATA_KEYS - metadata_keys)
            if missing_keys:
                issues.append(
                    f"{path.name}:{node.name}: missing metadata keys: {', '.join(missing_keys)}"
                )

    return issues


@asset_check(asset=metrics_all)
def metrics_metadata_contract_check() -> AssetCheckResult:
    issues = _validate_metrics_asset_metadata()
    if issues:
        details = "\n".join(issues[:25])
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="Metrics asset metadata contract failed",
            metadata={
                "issue_count": len(issues),
                "details": details,
            },
        )

    return AssetCheckResult(
        passed=True,
        severity=AssetCheckSeverity.WARN,
        description="Metrics asset metadata contract passed",
        metadata={"checked_keys": ", ".join(sorted(REQUIRED_METADATA_KEYS))},
    )
