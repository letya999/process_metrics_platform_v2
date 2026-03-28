"""Reset dlt incremental watermark for a Jira pipeline.

Usage:
    python scripts/reset_dlt_watermark.py --all --date 2026-03-18
    python scripts/reset_dlt_watermark.py --pipeline jira_raw_TWAD --date 2026-03-18
    python scripts/reset_dlt_watermark.py --all --date 2026-03-18 --container dagster

CRITICAL: dlt stores watermark in TWO places simultaneously:
  1. PostgreSQL: raw_jira._dlt_pipeline_state  (remote)
  2. Local file:  /home/dagster/.dlt/pipelines/<name>/state.json  (inside Docker container)

On pipeline.sync_destination(), dlt takes MAX(local, remote). If the local file
has a newer watermark, it wins — silently overriding any DB reset.
This script resets BOTH places. Use --container to specify the Docker container name.
"""

import argparse
import base64
import json
import os
import subprocess
import zlib
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

RESOURCE_KEY = "fields.updated"
RESOURCE_NAME = "issues"
SOURCE_NAME = "jira"
DLT_HOME_IN_CONTAINER = "/home/dagster/.dlt/pipelines"


def _decode_state(blob: str) -> dict:
    raw = base64.b64decode(blob)
    # dlt decompresses with plain zlib.decompress() (no wbits). wbits=47 auto-detects
    # both zlib and gzip for backward compatibility with manually created blobs.
    try:
        return json.loads(zlib.decompress(raw))
    except zlib.error:
        return json.loads(zlib.decompress(raw, 47))


def _encode_state(state: dict) -> str:
    # Must use plain zlib.compress() — dlt decompresses with zlib.decompress() (no wbits).
    # Using gzip (wbits=15+16) causes "incorrect header check" in dlt.
    compressed = zlib.compress(json.dumps(state).encode())
    return base64.b64encode(compressed).decode()


def _reset_incremental(state: dict, new_date: str) -> tuple[str, str]:
    """Mutate state dict in-place. Returns (old_value, new_value)."""
    incremental = state["sources"][SOURCE_NAME]["resources"][RESOURCE_NAME][
        "incremental"
    ]
    old_value = incremental[RESOURCE_KEY]["last_value"]
    incremental[RESOURCE_KEY]["last_value"] = f"{new_date}T00:00:00.000+0000"
    incremental[RESOURCE_KEY]["unique_hashes"] = []
    return old_value, f"{new_date}T00:00:00.000+0000"


def reset_db_watermark(engine, pipeline_name: str, new_date: str) -> None:
    """Reset watermark in PostgreSQL _dlt_pipeline_state table."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
            SELECT version, state FROM raw_jira._dlt_pipeline_state
            WHERE pipeline_name = :name
            ORDER BY version DESC LIMIT 1
            """
            ),
            {"name": pipeline_name},
        ).fetchone()

        if row is None:
            print(f"  [DB] No state found for {pipeline_name} - skipping")
            return

        current_version, blob = row
        state = _decode_state(blob)

        try:
            old_value, new_value = _reset_incremental(state, new_date)
        except KeyError as e:
            print(f"  [DB] Unexpected state structure for {pipeline_name}: {e}")
            return

        new_version = current_version + 1
        state["_state_version"] = new_version
        new_blob = _encode_state(state)

        # Use the latest load_id that actually exists in _dlt_loads.
        # Copying load_id from the previous state row is unsafe — that row may itself
        # have an invalid load_id, causing dlt to silently ignore our reset state.
        conn.execute(
            text(
                """
            INSERT INTO raw_jira._dlt_pipeline_state
                (version, engine_version, pipeline_name, created_at, version_hash,
                 state, _dlt_load_id, _dlt_id)
            SELECT :version, ps.engine_version, ps.pipeline_name, now(), 'manual-reset',
                   :state,
                   (SELECT load_id FROM raw_jira._dlt_loads ORDER BY inserted_at DESC LIMIT 1),
                   gen_random_uuid()::text
            FROM raw_jira._dlt_pipeline_state ps
            WHERE ps.pipeline_name = :name
            ORDER BY ps.version DESC LIMIT 1
            """
            ),
            {"version": new_version, "state": new_blob, "name": pipeline_name},
        )

        print(
            f"  [DB] {pipeline_name}: v{current_version} -> v{new_version} | {old_value} -> {new_value}"
        )


def reset_container_watermark(
    container: str, pipeline_name: str, new_date: str
) -> None:
    """Reset watermark in the local state file inside the Docker container.

    This is the step most commonly missed. dlt takes MAX(local, remote), so if
    the container file has a newer watermark than the DB reset, the DB reset
    is silently ignored.
    """
    state_path = f"{DLT_HOME_IN_CONTAINER}/{pipeline_name}/state.json"

    # Read current file
    result = subprocess.run(  # noqa: S603
        ["docker", "exec", container, "cat", state_path],  # noqa: S607
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"  [container:{container}] {pipeline_name} state file not found at {state_path} - skipping"
        )
        return

    state = json.loads(result.stdout)

    try:
        old_value, new_value = _reset_incremental(state, new_date)
    except KeyError as e:
        print(
            f"  [container:{container}] Unexpected state structure for {pipeline_name}: {e}"
        )
        return

    state["_state_version"] = state.get("_state_version", 0) + 1
    new_content = json.dumps(state)

    # Write back into container
    write_result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "docker",
            "exec",
            "-i",
            container,
            "bash",
            "-c",
            f"cat > {state_path}",
        ],
        input=new_content,
        text=True,
        capture_output=True,
    )
    if write_result.returncode != 0:
        print(f"  [container:{container}] Failed to write: {write_result.stderr}")
        return

    print(f"  [container:{container}] {pipeline_name}: {old_value} -> {new_value}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset dlt Jira pipeline watermark (DB + Docker container local file)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pipeline", help="Pipeline name, e.g. jira_raw_TWAD")
    group.add_argument(
        "--all", action="store_true", help="Reset all jira_raw_* pipelines"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Reset watermark to this date (YYYY-MM-DD). Pipeline re-fetches from this date.",
    )
    parser.add_argument(
        "--container",
        default="dagster",
        help="Docker container name that runs Dagster (default: dagster). "
        "Set to empty string '' to skip container reset.",
    )
    args = parser.parse_args()

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
        raise SystemExit(1) from None

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not db_url:
        print("DATABASE_URL or DB_URL environment variable not set.")
        raise SystemExit(1)

    engine = create_engine(db_url)

    if args.all:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT pipeline_name FROM raw_jira._dlt_pipeline_state "
                    "WHERE pipeline_name LIKE 'jira_raw_%'"
                )
            ).fetchall()
        pipelines = [r[0] for r in rows]
        print(f"Resetting {len(pipelines)} pipelines to {args.date}:")
    else:
        pipelines = [args.pipeline]
        print(f"Resetting {args.pipeline} to {args.date}:")

    for p in pipelines:
        reset_db_watermark(engine, p, args.date)
        if args.container:
            reset_container_watermark(args.container, p, args.date)

    print("\nDone. Re-run jira_sync_job to re-fetch data from the reset date.")


if __name__ == "__main__":
    main()
