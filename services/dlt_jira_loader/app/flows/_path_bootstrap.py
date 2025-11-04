"""Bootstrap utility to make the service package importable when Prefect
loads flow scripts as standalone modules.

Usage: import this module at the top of any flow script before other imports.
It ensures the service `app` package root is inserted into `sys.path` so
absolute imports like `app.infra` and `app.flows` work regardless of how the
file was executed.
"""
from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(__file__)
# services/dlt_jira_loader/app/flows -> go up two levels to services/dlt_jira_loader/app
_SERVICE_APP_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

if _SERVICE_APP_ROOT not in sys.path:
    # Prepend to give priority over other installed packages
    sys.path.insert(0, _SERVICE_APP_ROOT)

__all__ = ["_SERVICE_APP_ROOT"]
