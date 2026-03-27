from __future__ import annotations

from pathlib import Path
from typing import Protocol


class BIProvider(Protocol):
    """Provider interface for BI tools."""

    name: str

    def provision(self, pack_dir: Path) -> None:
        """Provision dashboards/cards for the provider using a pack directory."""
