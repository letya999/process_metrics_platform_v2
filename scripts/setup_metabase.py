"""Backward-compatible wrapper for BI provisioning.

Use `python -m bi.main` directly for new deployments.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bi.main import main

if __name__ == "__main__":
    main()
