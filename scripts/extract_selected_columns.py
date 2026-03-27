from pathlib import Path

repo = Path(__file__).resolve().parents[1] / "db" / "schemas"
selected = {
    "raw_jira": [
        "issues",
        "issues__changelog__histories",
        "issues__changelog__histories__items",
        "issues__fields__customfield_10020",
        "sprints",
    ],
    "clean_jira": [
        "projects",
        "issues",
        "issue_statuses",
        "issue_types",
        "issue_status_changelog",
        "sprints",
        "sprint_issues",
        "board_columns",
        "board_column_statuses",
        "field_keys",
        "field_values",
        "releases",
        "release_issues",
    ],
    "metrics": [
        "definitions",
        "calculations",
        "dim_projects",
        "dim_dates",
        "fact_values",
        "v_facts",
        "slice_rules",
    ],
}

for schema, targets in selected.items():
    lines = (repo / f"{schema}_schema.sql").read_text(encoding="utf-8").splitlines()
    print(f"## {schema}")
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        prefix = f"CREATE TABLE {schema}."
        if s.startswith(prefix) and s.endswith("("):
            table = s[len(prefix) :].split()[0]
            cols = []
            i += 1
            while i < len(lines):
                t = lines[i].strip()
                if t == ");":
                    break
                if t and not t.startswith("--"):
                    up = t.upper()
                    if not up.startswith(
                        (
                            "CONSTRAINT ",
                            "PRIMARY KEY",
                            "UNIQUE ",
                            "FOREIGN KEY",
                            "CHECK ",
                        )
                    ):
                        cols.append(t.split()[0].rstrip(",").strip('"'))
                i += 1
            if table in targets:
                print(f"{table}: {', '.join(cols[:18])}")
        i += 1

    if "v_facts" in targets:
        print("v_facts: view")
