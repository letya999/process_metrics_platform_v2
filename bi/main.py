from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bi.registry import get_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_pack_dir(provider: str, pack: str) -> Path:
    """Resolve absolute path of a pack under /bi/packs/<provider>/<pack>."""
    return Path(__file__).resolve().parent / "packs" / provider / pack


def parse_args() -> argparse.Namespace:
    """Parse CLI args for BI provider and pack selection."""
    parser = argparse.ArgumentParser(
        description="Provision BI provider content from versioned dashboard packs"
    )
    parser.add_argument(
        "--provider",
        default="metabase",
        help="BI provider name (default: metabase)",
    )
    parser.add_argument(
        "--pack",
        default="process_metrics_v1",
        help="Pack name under /bi/packs/<provider>/ (default: process_metrics_v1)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for BI provisioning."""
    args = parse_args()

    provider = get_provider(args.provider)
    pack_dir = _resolve_pack_dir(args.provider, args.pack)

    if not pack_dir.exists():
        raise FileNotFoundError(f"BI pack not found: {pack_dir}")

    logger.info(
        "Starting BI provisioning: provider=%s pack=%s", args.provider, args.pack
    )
    provider.provision(pack_dir)


if __name__ == "__main__":
    main()
