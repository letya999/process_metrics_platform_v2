"""Run repository validation checks used by `make validate`."""

from __future__ import annotations

import os
import sys


def main() -> int:
    from pipelines.utils.db_config import get_active_projects_from_db

    projects = get_active_projects_from_db()

    if not projects:
        # Tolerate missing DB in CI: fall back to env var check
        projects_env = os.getenv("JIRA_PROJECTS", "")
        if projects_env:
            keys = [k.strip() for k in projects_env.split(",") if k.strip()]
            print(f"[OK] JIRA_PROJECTS env var: {keys}")
            return 0
        print(
            "[FAIL] No active projects found in platform.projects "
            "and JIRA_PROJECTS env var is not set."
        )
        return 1

    print(f"[OK] Active projects in DB: {[p.project_key for p in projects]}")
    for p in projects:
        if not p.instance_url:
            print(f"[WARN] Project {p.project_key} has no instance_url")
        if not p.api_token:
            print(f"[WARN] Project {p.project_key} has no resolvable API token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
