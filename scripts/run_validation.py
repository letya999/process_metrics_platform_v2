"""Run repository validation checks used by `make validate`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from config import ConfigurationError, load_config_from_file


def _default_env() -> None:
    """Provide safe defaults so config interpolation is deterministic in local/CI runs."""
    os.environ.setdefault("JIRA_BASE_URL", "https://example.atlassian.net")
    os.environ.setdefault("JIRA_USER_EMAIL", "admin@example.com")


def main() -> int:
    _default_env()

    config_path = Path("config/projects.yaml")
    if not config_path.exists():
        config_path = Path("config/projects.example.yaml")

    try:
        config = load_config_from_file(config_path)
    except ConfigurationError as exc:
        print(f"[FAIL] Config validation failed: {exc}")
        return 1

    total_projects = len(config.projects)
    enabled_projects = len(config.get_enabled_projects())
    if total_projects == 0:
        print("[FAIL] No projects configured in config/projects.yaml")
        return 1

    print("[OK] Config schema validation passed")
    print(
        f"[OK] Projects configured: total={total_projects}, enabled={enabled_projects}"
    )
    print(f"[OK] Jira instances configured: {len(config.jira_instances)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
