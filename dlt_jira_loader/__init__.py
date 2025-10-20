"""Compatibility package that exposes `services/dlt_jira_loader` as
`dlt_jira_loader` for tests and imports.

This module adjusts its __path__ to include the real package located at
`services/dlt_jira_loader` so both `dlt_jira_loader.*` and
`services.dlt_jira_loader.*` imports work during tests.
"""
from __future__ import annotations

import os

# Insert the services package path so imports like `import dlt_jira_loader.*`
# resolve to `services/dlt_jira_loader` on disk.
_base = os.path.dirname(__file__)
_services_path = os.path.normpath(
    os.path.join(_base, "..", "services", "dlt_jira_loader")
)
if os.path.isdir(_services_path):
    __path__.insert(0, _services_path)
