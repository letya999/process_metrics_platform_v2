"""Clean layer assets for Jira supplementary data.

Covers: worklogs, comments, field_values, field_value_changelog.
"""

# ruff: noqa: S608

import json
from typing import Any

from dagster import AssetExecutionContext, asset
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource

from ._utils import _detect_sprint_field_id, _table_exists


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_issues"],
    description="Extract worklogs from raw Jira issues",
    compute_kind="sql",
)
def clean_jira_worklogs(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync worklogs from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        # Check if worklogs table exists
        table_exists = _table_exists(
            conn, "raw_jira", "issues__fields__worklog__worklogs"
        )

        if not table_exists:
            context.log.warning(
                "Table raw_jira.issues__fields__worklog__worklogs not found"
            )
            return {"status": "skipped", "reason": "no_worklogs_table"}

        context.log.info("Syncing worklogs...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.worklogs (
                issue_id,
                external_id,
                author_id,
                time_spent_seconds,
                started_at
            )
            SELECT DISTINCT
                i.id as issue_id,
                rw.id as external_id,
                u.id as author_id,
                rw.time_spent_seconds::int,
                rw.started::timestamptz as started_at
            FROM raw_jira.issues__fields__worklog__worklogs rw
            JOIN raw_jira.issues r ON rw._dlt_parent_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            LEFT JOIN clean_jira.jira_users u ON u.project_id = p.id AND u.external_id = rw.author__account_id
            WHERE rw.id IS NOT NULL
            ON CONFLICT (issue_id, external_id) DO UPDATE SET
                author_id = EXCLUDED.author_id,
                time_spent_seconds = EXCLUDED.time_spent_seconds,
                started_at = EXCLUDED.started_at
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues"],
    description="Extract comments from raw Jira issues",
    compute_kind="sql",
)
def clean_jira_comments(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract comments to clean_jira.comments and linkage to issues."""
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting comments...")

        # Identify the table name for comments
        possible_tables = [
            "issues__rendered_fields__comment__comments",
            "issues__fields__comment__comments",
            "issues__fields__comment",
        ]

        comment_table = None
        for table in possible_tables:
            exists = _table_exists(conn, "raw_jira", table)
            if exists:
                # Also check if 'body' column exists in this table
                has_body = conn.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'raw_jira'
                              AND table_name = :table_name
                              AND column_name = 'body'
                        )
                    """
                    ),
                    {"table_name": table},
                ).scalar()
                if has_body:
                    comment_table = table
                    break

        if not comment_table:
            # Last ditch effort: try the first existing table
            for table in possible_tables:
                if _table_exists(conn, "raw_jira", table):
                    comment_table = table
                    break

        if not comment_table:
            context.log.warning(
                "No comment table found in raw_jira. Skipping comments sync."
            )
            return {"status": "skipped", "reason": "no_comment_table"}

        context.log.info(f"Using raw comment table: {comment_table}")

        # Create safe_timestamptz - M-8: Always create at start of block
        conn.execute(
            text(
                """
            CREATE OR REPLACE FUNCTION pg_temp.safe_timestamptz(val text)
            RETURNS timestamptz AS $$
            BEGIN
                BEGIN
                    RETURN val::timestamptz;
                EXCEPTION WHEN others THEN
                    BEGIN
                        RETURN to_timestamp(val, 'DD/Mon/YY HH:MI AM');
                    EXCEPTION WHEN others THEN
                        RETURN NULL;
                    END;
                END;
            END;
            $$ LANGUAGE plpgsql;
            """
            )
        )

        # Insert comments
        insert_sql_template = """
            INSERT INTO clean_jira.comments (
                project_id,
                external_id,
                body,
                author_id,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                i.project_id,
                c.id as external_id,
                COALESCE(c.body, '') as body,
                u.id as author_id,
                COALESCE(pg_temp.safe_timestamptz(c.created), now()) as created_at,
                COALESCE(pg_temp.safe_timestamptz(c.updated), now()) as updated_at
            FROM raw_jira.{table} c
            JOIN raw_jira.issues r ON c._dlt_root_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            LEFT JOIN clean_jira.jira_users u ON u.project_id = i.project_id
                AND u.external_id = c.author__account_id
            WHERE c.id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                body = EXCLUDED.body,
                author_id = EXCLUDED.author_id,
                updated_at = EXCLUDED.updated_at
            RETURNING id, external_id
            """
        insert_sql = insert_sql_template.format(table=comment_table)  # noqa: S608

        insert_query = text(insert_sql)

        result = conn.execute(insert_query)
        comments_synced = result.fetchall()
        context.log.info(f"Synced {len(comments_synced)} comments")

        # Sync comment-issue linkage
        link_query = text(
            f"""
            INSERT INTO clean_jira.comment_issues (
                comment_id,
                issue_id
            )
            SELECT
                c.id as comment_id,
                i.id as issue_id
            FROM raw_jira.{comment_table} rc
            JOIN raw_jira.issues r ON rc._dlt_root_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            JOIN clean_jira.comments c ON c.external_id = rc.id
                AND c.project_id = i.project_id
            ON CONFLICT (comment_id, issue_id) DO NOTHING
            """
        )  # noqa: S608

        conn.execute(link_query)
        context.log.info("Synced comment-issue links")

        conn.commit()

    return {"status": "success", "comments_synced": len(comments_synced)}


@asset(
    group_name="jira_clean",
    deps=["clean_jira_field_keys"],
    description="Extract current field values from raw Jira issues",
    compute_kind="sql",
)
def clean_jira_field_values(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract current custom field values from raw Jira issues."""
    engine = database.get_engine()
    field_values_inserted = 0

    with engine.connect() as conn:
        context.log.info("Extracting field values from issues...")

        # Create safe_jsonb function to handle invalid JSON gracefully
        conn.execute(
            text(
                """
            CREATE OR REPLACE FUNCTION pg_temp.safe_jsonb(val text)
            RETURNS jsonb AS $$
            BEGIN
                BEGIN
                    RETURN val::jsonb;
                EXCEPTION WHEN OTHERS THEN
                    RETURN NULL;
                END;
            END;
            $$ LANGUAGE plpgsql;
        """
            )
        )

        # Get all columns first
        columns_result = conn.execute(
            text(
                """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw_jira'
              AND table_name = 'issues'
        """
            )
        ).fetchall()
        all_columns = [row[0] for row in columns_result]

        # Pre-load field keys map to avoid joins in the loop
        # Map: (project_id, external_key) -> field_key_id
        fk_rows = conn.execute(
            text("SELECT id, project_id, external_key FROM clean_jira.field_keys")
        ).fetchall()
        fk_map = {(r.project_id, r.external_key): r.id for r in fk_rows}
        context.log.info(f"Loaded {len(fk_map)} field keys for mapping")

        # Filter for relevant custom field columns
        target_columns = []
        for col_name in all_columns:
            if not col_name.startswith("fields__customfield_"):
                continue
            if col_name.count("__") >= 3:
                continue
            target_columns.append(col_name)

        context.log.info(f"Found {len(target_columns)} custom field columns to process")

        # Process in batches of columns
        batch_size = 20
        insert_stmt = text(
            """
            INSERT INTO clean_jira.field_values (
                issue_id,
                field_key_id,
                value,
                json_value,
                updated_at
            )
            VALUES (
                :issue_id,
                :field_key_id,
                :value,
                CAST(:json_value AS jsonb),
                now()
            )
            ON CONFLICT (issue_id, field_key_id) DO UPDATE SET
                value = EXCLUDED.value,
                json_value = EXCLUDED.json_value,
                updated_at = now()
        """
        )

        for i in range(0, len(target_columns), batch_size):
            chunk = target_columns[i : i + batch_size]
            context.log.info(
                f"Processing batch {i // batch_size + 1}: columns {i} to {i + len(chunk)}"
            )

            # Build dynamic select
            select_clause = ", ".join([f'r."{c}"' for c in chunk])

            rows_query = text(
                f"""
                SELECT
                    i.id as issue_id,
                    i.project_id,
                    {select_clause}
                FROM raw_jira.issues r
                JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
                JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            """
            )  # noqa: S608

            # M-1: Use streaming to avoid OOM
            result = conn.execution_options(stream_results=True).execute(rows_query)

            insert_data = []
            for row in result.yield_per(1000):
                issue_id = row.issue_id
                project_id = row.project_id

                for idx, col_name in enumerate(chunk):
                    val = row[2 + idx]

                    # M-11: Filter out None and junk values
                    if val is None:
                        continue
                    val_str = str(val)
                    if val_str in ("None", "nan", "NaN", "NULL", "null", ""):
                        continue

                    field_key = col_name.replace("fields__", "", 1)
                    fk_id = fk_map.get((project_id, field_key))
                    if not fk_id:
                        continue

                    json_val = None
                    # Basic heuristics to skip non-JSON strings
                    if (
                        val_str.startswith("0|")
                        or "|i" in val_str
                        or val_str.startswith("{pullrequest")
                    ):
                        json_val = None
                    else:
                        try:
                            json.loads(val_str)
                            json_val = val_str
                        except (ValueError, TypeError):
                            json_val = None

                    insert_data.append(
                        {
                            "issue_id": issue_id,
                            "field_key_id": fk_id,
                            "value": val_str,
                            "json_value": json_val,
                        }
                    )

                    # Batch insert to keep memory footprint low
                    if len(insert_data) >= 5000:
                        conn.execute(insert_stmt, insert_data)
                        field_values_inserted += len(insert_data)
                        insert_data = []

            if insert_data:
                conn.execute(insert_stmt, insert_data)
                field_values_inserted += len(insert_data)

        context.log.info(f"Inserted {field_values_inserted} field values")
        conn.commit()

        # Explicitly extract 'Sprint' values
        sprint_field_id = _detect_sprint_field_id(conn)
        context.log.info(f"Extracting Sprint ({sprint_field_id}) values...")
        sprint_table_exists = _table_exists(
            conn, "raw_jira", f"issues__fields__{sprint_field_id}"
        )

        if sprint_table_exists:
            result = conn.execute(
                text(
                    f"""
                INSERT INTO clean_jira.field_values (
                    issue_id,
                    field_key_id,
                    value,
                    json_value,
                    updated_at
                )
                SELECT
                    i.id as issue_id,
                    fk.id as field_key_id,
                    -- For 'value', we just store the raw aggregation
                    string_agg(s.name, ', ' ORDER BY s.start_date) as value,
                    -- For 'json_value', we store it as a JSON string containing the list
                    to_jsonb(string_agg(s.name, ', ' ORDER BY s.start_date)) as json_value,
                    now() as updated_at
                FROM raw_jira.issues__fields__{sprint_field_id} s
                JOIN raw_jira.issues r ON s._dlt_parent_id = r._dlt_id
                JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
                JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
                JOIN clean_jira.field_keys fk ON fk.project_id = i.project_id
                    AND fk.external_key = :sprint_field_id
                GROUP BY i.id, fk.id
                ON CONFLICT (issue_id, field_key_id) DO UPDATE SET
                    value = EXCLUDED.value,
                    json_value = EXCLUDED.json_value,
                    updated_at = now()
                RETURNING id
            """
                ),  # noqa: S608
                {"sprint_field_id": sprint_field_id},
            )
            sprint_values_count = len(result.fetchall())
            context.log.info(f"Inserted {sprint_values_count} Sprint field values")
            field_values_inserted += sprint_values_count
            conn.commit()
        else:
            context.log.warning(
                f"Sprint table ({sprint_field_id}) not found in raw_jira"
            )

    return {
        "status": "success",
        "field_values_inserted": field_values_inserted,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_field_keys"],
    description="Extract field value changelog from raw Jira issue history",
    compute_kind="sql",
)
def clean_jira_field_value_changelog(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract field value change history from issue changelog.

    Parses the changelog JSON from raw_jira.issues to extract all field changes,
    particularly custom fields (customfield_*).
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting field value changelog...")

        # Check if changelog table exists
        changelog_exists = _table_exists(
            conn, "raw_jira", "issues__changelog__histories__items"
        )

        if not changelog_exists:
            context.log.warning("No changelog items table found in raw_jira")
            return {"status": "skipped", "reason": "no_changelog_items_table"}

        # Use a temporary function to safely cast to JSONB
        conn.execute(
            text(
                """
            CREATE OR REPLACE FUNCTION pg_temp.safe_jsonb(val text)
            RETURNS jsonb AS $$
            BEGIN
                BEGIN
                    RETURN val::jsonb;
                EXCEPTION WHEN OTHERS THEN
                    RETURN to_jsonb(val);
                END;
            END;
            $$ LANGUAGE plpgsql;
        """
            )
        )

        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.field_value_changelog (
                issue_id,
                field_key_id,
                old_value,
                new_value,
                changed_by_id,
                changed_at
            )
            SELECT
                i.id as issue_id,
                fk.id as field_key_id,
                pg_temp.safe_jsonb(item.from_string) as old_value,
                pg_temp.safe_jsonb(item.to_string) as new_value,
                u.id as changed_by_id,
                h.created::timestamptz as changed_at
            FROM raw_jira.issues__changelog__histories__items item
            JOIN raw_jira.issues__changelog__histories h
                ON item._dlt_parent_id = h._dlt_id
            JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            JOIN clean_jira.field_keys fk ON fk.project_id = i.project_id
                AND (
                    fk.external_key = item.field_id
                    OR fk.external_key = LOWER(REPLACE(item.field, ' ', '_'))
                )
            LEFT JOIN clean_jira.jira_users u ON u.project_id = i.project_id
                AND u.external_id = h.author__account_id
            WHERE (item.field_id LIKE 'customfield_%'
                   OR item.field NOT IN (
                       'Sprint', 'Fix Version/s', 'fixVersions', 'Fix Version', 'Status'
                   ))
            ON CONFLICT (issue_id, field_key_id, changed_at) DO NOTHING
            RETURNING id
        """
            )
        )
        changes_count = len(result.fetchall())
        context.log.info(f"Inserted {changes_count} field value changelog entries")

        conn.commit()

    return {"status": "success", "changes_count": changes_count}
