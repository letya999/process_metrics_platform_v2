"""Pytest bootstrap for `services/` tests — ensure project root is on sys.path.

This makes imports like `from services.dlt_jira_loader...` resolvable when
pytest collects tests located under `services/`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# project root is parent of the `services/` directory
ROOT = Path(__file__).resolve().parent.parent
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)
