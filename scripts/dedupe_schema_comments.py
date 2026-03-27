from __future__ import annotations

import re
from pathlib import Path

COMMENT_RE = re.compile(
    r"^(COMMENT ON (?:TABLE|VIEW|MATERIALIZED VIEW|COLUMN)\s+[a-zA-Z_][\w]*\.[^\s]+(?:\.[^\s]+)?\s+IS\s+'.*';)\s*$"
)


def dedupe_file(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    # Track last occurrence index by canonical target signature.
    target_to_last_idx: dict[str, int] = {}
    parsed: list[tuple[int, str, str]] = []

    for idx, line in enumerate(lines):
        m = COMMENT_RE.match(line.strip())
        if not m:
            continue
        stmt = m.group(1)
        # Canonical target key: strip trailing comment text after IS
        key = stmt.split(" IS ", 1)[0]
        parsed.append((idx, key, stmt))
        target_to_last_idx[key] = idx

    # Remove earlier duplicates, keep only last per target.
    drop_idx = {idx for idx, key, _stmt in parsed if target_to_last_idx.get(key) != idx}

    if not drop_idx:
        return

    out = [line for i, line in enumerate(lines) if i not in drop_idx]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    for name in ("clean_jira_schema.sql", "metrics_schema.sql"):
        dedupe_file(repo / "db" / "schemas" / name)
    print("deduped comments in clean_jira and metrics schemas")


if __name__ == "__main__":
    main()
