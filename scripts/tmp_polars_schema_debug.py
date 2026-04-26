from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table


def main() -> None:
    db = DatabaseResource()
    engine = db.get_engine()

    sprint_issues_df = read_table(
        engine, "SELECT issue_id,sprint_id FROM clean_jira.sprint_issues LIMIT 5"
    )
    field_values_df = read_table(
        engine,
        "SELECT issue_id,field_key_id,json_value::text AS json_value FROM clean_jira.field_values LIMIT 5",
    )
    fvc_df = read_table(
        engine,
        "SELECT issue_id,field_key_id,old_value::text AS old_value,new_value::text AS new_value,changed_at FROM clean_jira.field_value_changelog LIMIT 5",
    )
    issues_df = read_table(
        engine, "SELECT id,external_key FROM clean_jira.issues LIMIT 5"
    )

    print("sprint_issues schema", sprint_issues_df.schema)
    print("field_values schema", field_values_df.schema)
    print("fvc schema", fvc_df.schema)
    print("issues schema", issues_df.schema)


if __name__ == "__main__":
    main()
