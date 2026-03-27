from pathlib import Path


def process_file(
    path: Path, schema: str, table_base: str, col_base: str
) -> tuple[int, int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()

    existing_tbl: set[str] = set()
    existing_view: set[str] = set()
    existing_col: set[tuple[str, str]] = set()

    for line in lines:
        s = line.strip()
        if s.startswith(f"COMMENT ON TABLE {schema}.") and " IS " in s:
            name = s.split()[3].split(".", 1)[1]
            existing_tbl.add(name)
        elif (
            s.startswith(f"COMMENT ON VIEW {schema}.")
            or s.startswith(f"COMMENT ON MATERIALIZED VIEW {schema}.")
        ) and " IS " in s:
            name = s.split()[3].split(".", 1)[1]
            existing_view.add(name)
        elif s.startswith(f"COMMENT ON COLUMN {schema}.") and " IS " in s:
            parts = s.split()[3].split(".")
            if len(parts) >= 3:
                existing_col.add((parts[1], parts[2]))

    tables: list[str] = []
    views: list[str] = []
    table_cols: dict[str, list[str]] = {}

    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if (
            s.startswith("CREATE TABLE ")
            and s.endswith("(")
            and s.split()[2].startswith(f"{schema}.")
        ):
            tbl = s.split()[2].split(".", 1)[1]
            tables.append(tbl)
            cols: list[str] = []
            i += 1
            while i < len(lines):
                t = lines[i].strip()
                if t == ");":
                    break
                if t and not t.startswith("--"):
                    upper = t.upper()
                    if not upper.startswith(
                        (
                            "CONSTRAINT ",
                            "PRIMARY KEY",
                            "UNIQUE ",
                            "FOREIGN KEY",
                            "CHECK ",
                        )
                    ):
                        token = t.split()[0].rstrip(",")
                        token = token.strip('"')
                        if token and token[0].isalpha() and token not in {"ONLY"}:
                            cols.append(token)
                i += 1
            table_cols[tbl] = cols
        elif s.startswith("CREATE VIEW ") and s.split()[2].startswith(f"{schema}."):
            vw = s.split()[2].split(".", 1)[1]
            views.append(vw)
        elif s.startswith("CREATE MATERIALIZED VIEW ") and s.split()[3].startswith(
            f"{schema}."
        ):
            vw = s.split()[3].split(".", 1)[1]
            views.append(vw)
        i += 1

    additions: list[str] = []

    for tbl in tables:
        if tbl not in existing_tbl:
            additions.append(
                f"COMMENT ON TABLE {schema}.{tbl} IS '{table_base}: {tbl.replace('_', ' ')}.';"
            )
        for col in table_cols.get(tbl, []):
            if (tbl, col) not in existing_col:
                additions.append(
                    f"COMMENT ON COLUMN {schema}.{tbl}.{col} IS '{col_base}: {col.replace('_', ' ')}.';"
                )

    for vw in views:
        if vw not in existing_view:
            additions.append(
                f"COMMENT ON VIEW {schema}.{vw} IS '{table_base}: {vw.replace('_', ' ')} view.';"
            )

    if additions:
        out = (
            "\n".join(lines).rstrip()
            + "\n\n-- Auto-generated baseline comments for missing objects\n"
            + "\n".join(additions)
            + "\n"
        )
        path.write_text(out, encoding="utf-8")

    return len(tables), len(views), len(additions)


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    configs = [
        (
            repo / "db/schemas/raw_jira_schema.sql",
            "raw_jira",
            "Raw Jira object mirrored from source API",
            "Raw Jira source field",
        ),
        (
            repo / "db/schemas/clean_jira_schema.sql",
            "clean_jira",
            "Clean Jira normalized analytical object",
            "Clean Jira normalized field",
        ),
        (
            repo / "db/schemas/metrics_schema.sql",
            "metrics",
            "Metrics analytical object",
            "Metrics field",
        ),
    ]

    for path, schema, table_base, col_base in configs:
        tables, views, additions = process_file(path, schema, table_base, col_base)
        print(f"{path.name}: tables={tables} views={views} additions={additions}")


if __name__ == "__main__":
    main()
