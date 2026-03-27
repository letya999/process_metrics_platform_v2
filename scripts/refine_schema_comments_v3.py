from __future__ import annotations

import re
from pathlib import Path

TABLE_COMMENT_OVERRIDES: dict[tuple[str, str], str] = {
    (
        "clean_jira",
        "projects",
    ): "Normalized Jira projects dimension mapped to platform projects.",
    (
        "clean_jira",
        "issues",
    ): "Normalized Jira issues at issue grain used as core analytical source.",
    (
        "clean_jira",
        "issue_types",
    ): "Normalized catalog of Jira issue types per project.",
    (
        "clean_jira",
        "issue_statuses",
    ): "Normalized catalog of Jira statuses per project.",
    (
        "clean_jira",
        "issue_priorities",
    ): "Normalized catalog of Jira priorities per project.",
    (
        "clean_jira",
        "issue_resolutions",
    ): "Normalized catalog of Jira resolutions per project.",
    (
        "clean_jira",
        "jira_users",
    ): "Normalized Jira users participating in project activity.",
    (
        "clean_jira",
        "jira_user_issue_roles",
    ): "Issue-role assignments for users (assignee, reporter, creator).",
    (
        "clean_jira",
        "issue_status_changelog",
    ): "Issue status transition history used for flow metrics.",
    (
        "clean_jira",
        "sprints",
    ): "Normalized sprint dimension with timeline and state attributes.",
    ("clean_jira", "sprint_issues"): "Current issue-to-sprint membership snapshot.",
    (
        "clean_jira",
        "sprint_issues_changelog",
    ): "Historical issue-to-sprint membership changes.",
    ("clean_jira", "sprint_changelog"): "History of sprint property changes.",
    ("clean_jira", "releases"): "Normalized release/version dimension from Jira.",
    ("clean_jira", "release_issues"): "Issue-to-release membership links.",
    (
        "clean_jira",
        "release_issues_changelog",
    ): "Historical issue-to-release membership changes.",
    ("clean_jira", "release_changelog"): "History of release property changes.",
    ("clean_jira", "field_keys"): "Jira field dictionary for system and custom fields.",
    ("clean_jira", "field_values"): "Current field values by issue and field key.",
    (
        "clean_jira",
        "field_value_changelog",
    ): "History of field value changes by issue and field.",
    ("clean_jira", "labels"): "Distinct Jira labels by project.",
    ("clean_jira", "issue_labels"): "Issue-to-label bridge table.",
    ("clean_jira", "boards"): "Normalized Jira boards by project.",
    (
        "clean_jira",
        "board_columns",
    ): "Board columns used for flow and commitment interpretation.",
    (
        "clean_jira",
        "board_column_statuses",
    ): "Mapping between board columns and Jira statuses.",
    ("clean_jira", "comments"): "Normalized issue comments.",
    ("clean_jira", "comment_issues"): "Bridge between comments and issues.",
    ("clean_jira", "worklogs"): "Normalized worklog entries linked to issues.",
    (
        "clean_jira",
        "relation_issue_types",
    ): "Catalog of issue link types (blocks, relates, duplicates).",
    (
        "clean_jira",
        "relation_issue_issues",
    ): "Directed links between source and target issues.",
    (
        "clean_jira",
        "issue_comment_blockings",
    ): "Detected blocking references extracted from comments.",
    (
        "clean_jira",
        "v_unique_users",
    ): "View of unique active Jira users across normalized entities.",
    ("metrics", "definitions"): "Business metric families registry.",
    (
        "metrics",
        "calculations",
    ): "Metric calculation variants with grain and unit settings.",
    ("metrics", "grains"): "Supported aggregation grains for metric calculations.",
    ("metrics", "dim_projects"): "Project dimension used by metric fact rows.",
    ("metrics", "dim_dates"): "Date dimension keyed by integer time_id.",
    ("metrics", "fact_values"): "Generic long-format fact table storing metric values.",
    (
        "metrics",
        "slice_rules",
    ): "Segmentation rules for producing sliced metric series.",
    (
        "metrics",
        "commitment_rules",
    ): "Rules mapping board columns to commitment boundaries.",
    (
        "metrics",
        "calculation_settings",
    ): "Per-calculation settings with optional project overrides.",
    ("metrics", "units"): "Unit catalog and source-field binding configuration.",
    (
        "metrics",
        "v_facts",
    ): "Denormalized analytics view joining metric facts and dimensions.",
}


COLUMN_OVERRIDES: dict[tuple[str, str, str], str] = {
    (
        "metrics",
        "fact_values",
        "metric_id",
    ): "Reference to the calculation variant that produced the value.",
    ("metrics", "fact_values", "project_agg_id"): "Reference to project dimension row.",
    (
        "metrics",
        "fact_values",
        "time_id",
    ): "Reference to date dimension key (YYYYMMDD).",
    ("metrics", "fact_values", "value"): "Measured numeric value.",
    (
        "metrics",
        "fact_values",
        "entity_type",
    ): "Entity grain type (issue, sprint, day, week, release).",
    (
        "metrics",
        "fact_values",
        "entity_id",
    ): "Entity identifier within the selected grain.",
    (
        "metrics",
        "fact_values",
        "slice_rule_id",
    ): "Applied slice rule when metric is segmented.",
    ("metrics", "fact_values", "slice_value"): "Segment value produced by slice rule.",
    (
        "metrics",
        "fact_values",
        "context_json",
    ): "Optional JSON context for diagnostics and BI drill-down.",
    ("metrics", "definitions", "metric_code"): "Stable business metric code.",
    ("metrics", "calculations", "calc_code"): "Stable technical calculation code.",
    ("metrics", "calculations", "grain_id"): "Reference to metrics.grains.",
    ("metrics", "calculations", "unit_code"): "Unit code of produced values.",
    ("clean_jira", "issues", "external_key"): "Jira issue key (for example, PROJ-123).",
    ("clean_jira", "issues", "jira_created_at"): "Issue creation timestamp in Jira.",
    ("clean_jira", "issues", "jira_updated_at"): "Issue last update timestamp in Jira.",
    (
        "clean_jira",
        "issues",
        "jira_resolved_at",
    ): "Issue resolution timestamp in Jira, if resolved.",
    (
        "clean_jira",
        "issue_status_changelog",
        "changed_at",
    ): "Timestamp of status transition.",
    (
        "clean_jira",
        "sprint_issues",
        "is_active",
    ): "Whether issue is currently active in sprint snapshot.",
    (
        "clean_jira",
        "field_values",
        "value_numeric",
    ): "Numeric interpretation of field value when applicable.",
    ("clean_jira", "field_values", "value"): "Text representation of field value.",
}


def humanize(name: str) -> str:
    return name.replace("__", " ").replace("_", " ")


def column_comment(schema: str, table: str, column: str) -> str:
    key = (schema, table, column)
    if key in COLUMN_OVERRIDES:
        return COLUMN_OVERRIDES[key]

    if column == "id":
        return "Primary key UUID."
    if column.endswith("_id"):
        return f"Reference identifier for {humanize(column[:-3])}."
    if column == "created_at":
        return "Row creation timestamp."
    if column == "updated_at":
        return "Row last update timestamp."
    if column == "external_id":
        return "Identifier from source Jira system."
    if column == "external_key":
        return "Key from source Jira system."
    if column in {"name", "summary", "description"}:
        return f"{column.capitalize()} value from source or normalized entity."
    if column == "status":
        return "Normalized lifecycle status."
    if column == "category":
        return "Normalized category value."
    if column.endswith("_date") or column.endswith("_at"):
        return f"Timestamp/date value for {humanize(column)}."
    if column.startswith("is_"):
        return f"Boolean flag indicating whether {humanize(column[3:])}."
    if column.endswith("_json"):
        return f"JSON payload for {humanize(column[:-5])}."

    return f"{humanize(column).capitalize()}."


def table_comment(schema: str, table: str) -> str:
    return TABLE_COMMENT_OVERRIDES.get(
        (schema, table), f"{schema} object: {humanize(table)}."
    )


def rewrite(path: Path, schema: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    table_re = re.compile(rf"^COMMENT ON TABLE {schema}\.([a-zA-Z_][\w]*) IS ".strip())
    view_re = re.compile(
        rf"^COMMENT ON (?:VIEW|MATERIALIZED VIEW) {schema}\.([a-zA-Z_][\w]*) IS ".strip()
    )
    col_re = re.compile(
        rf"^COMMENT ON COLUMN {schema}\.([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*) IS ".strip()
    )

    out: list[str] = []
    for line in lines:
        s = line.strip()

        mt = table_re.match(s)
        if mt:
            tbl = mt.group(1)
            out.append(
                f"COMMENT ON TABLE {schema}.{tbl} IS '{table_comment(schema, tbl)}';"
            )
            continue

        mv = view_re.match(s)
        if mv:
            vw = mv.group(1)
            out.append(
                f"COMMENT ON VIEW {schema}.{vw} IS '{table_comment(schema, vw)}';"
            )
            continue

        mc = col_re.match(s)
        if mc:
            tbl, col = mc.group(1), mc.group(2)
            out.append(
                f"COMMENT ON COLUMN {schema}.{tbl}.{col} IS '{column_comment(schema, tbl, col)}';"
            )
            continue

        out.append(line)

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    rewrite(repo / "db" / "schemas" / "clean_jira_schema.sql", "clean_jira")
    rewrite(repo / "db" / "schemas" / "metrics_schema.sql", "metrics")
    print("refined comments for clean_jira and metrics")


if __name__ == "__main__":
    main()
