"""Clean layer assets for Jira dimension tables.

Covers: projects, issue_types, priorities, resolutions, issue_statuses, field_keys.
"""

# ruff: noqa: S608

from typing import Any

from dagster import AssetExecutionContext, asset
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource

from ._utils import _detect_sprint_field_id, _get_platform_project_id, _table_exists


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data"],
    description="Sync Jira projects to clean layer",
    compute_kind="sql",
)
def clean_jira_projects(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync projects from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        # Use a dynamic platform_project_id for grouping all Jira projects
        platform_project_id = _get_platform_project_id(conn)
        context.log.info(f"Syncing projects with platform ID {platform_project_id}...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.projects (
                platform_project_id,
                external_id,
                external_key,
                name,
                created_at,
                updated_at
            )
            SELECT
                CAST(:platform_project_id AS uuid) as platform_project_id,
                r.id::text as external_id,
                r.key as external_key,
                r.name,
                now() as created_at,
                now() as updated_at
            FROM raw_jira.projects r
            ON CONFLICT (platform_project_id, external_id)
            DO UPDATE SET
                external_key = EXCLUDED.external_key,
                name = EXCLUDED.name,
                updated_at = now()
            RETURNING id
        """
            ),
            {"platform_project_id": platform_project_id},
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_projects"],
    description="Sync Jira issue types to clean layer",
    compute_kind="sql",
)
def clean_jira_issue_types(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync issue types from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing issue types...")

        # 3.2: Check if column 'fields__issuetype__hierarchy_level' exists
        try:
            conn.execute(
                text(
                    "SELECT fields__issuetype__hierarchy_level FROM raw_jira.issues LIMIT 1"
                )
            )
            has_hierarchy_level = True
        except Exception:
            conn.rollback()  # Reset aborted transaction state
            has_hierarchy_level = False
            context.log.warning(
                "Column 'fields__issuetype__hierarchy_level' not found in raw_jira.issues, falling back to ILIKE logic"
            )

        hierarchy_mapping = """
                CASE
                    WHEN r.fields__issuetype__name ILIKE '%epic%'
                        THEN 'epic'::clean_jira.issue_hierarchy_level
                    WHEN r.fields__issuetype__name ILIKE '%subtask%'
                        THEN 'subtask'::clean_jira.issue_hierarchy_level
                    WHEN r.fields__issuetype__name ILIKE '%story%'
                        THEN 'story'::clean_jira.issue_hierarchy_level
                    ELSE 'task'::clean_jira.issue_hierarchy_level
                END
        """
        if has_hierarchy_level:
            hierarchy_mapping = """
                CASE
                    WHEN r.fields__issuetype__hierarchy_level > 0 THEN 'epic'::clean_jira.issue_hierarchy_level
                    WHEN r.fields__issuetype__hierarchy_level = 0 THEN 'story'::clean_jira.issue_hierarchy_level
                    WHEN r.fields__issuetype__hierarchy_level < 0 THEN 'subtask'::clean_jira.issue_hierarchy_level
                    ELSE 'task'::clean_jira.issue_hierarchy_level
                END
            """

        result = conn.execute(
            text(
                f"""
            INSERT INTO clean_jira.issue_types (
                project_id,
                external_id,
                name,
                hierarchy_level
            )
            SELECT DISTINCT
                p.id as project_id,
                r.fields__issuetype__id as external_id,
                r.fields__issuetype__name as name,
                {hierarchy_mapping} as hierarchy_level
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__issuetype__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                hierarchy_level = EXCLUDED.hierarchy_level
            RETURNING id
            """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_projects"],
    description="Sync Jira issue priorities to clean layer",
    compute_kind="sql",
)
def clean_jira_priorities(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync issue priorities from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing issue priorities...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.issue_priorities (
                project_id,
                external_id,
                name
            )
            SELECT DISTINCT
                p.id as project_id,
                r.fields__priority__id as external_id,
                r.fields__priority__name as name
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__priority__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_projects"],
    description="Sync Jira issue resolutions to clean layer",
    compute_kind="sql",
)
def clean_jira_resolutions(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync issue resolutions from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing issue resolutions...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.issue_resolutions (
                project_id,
                external_id,
                name,
                description
            )
            SELECT DISTINCT
                p.id as project_id,
                r.fields__resolution__id as external_id,
                r.fields__resolution__name as name,
                r.fields__resolution__description as description
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__resolution__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_projects"],
    description="Sync Jira issue statuses to clean layer",
    compute_kind="sql",
)
def clean_jira_issue_statuses(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync issue statuses from raw to clean.

    Sources:
    1. Current status on issues (fields__status__id)
    2. Historical statuses from status changelog (to/from values in history items)

    This ensures statuses that no issue currently holds (e.g. "On review") are
    still present in clean_jira.issue_statuses so board_column_statuses and
    issue_status_changelog can resolve them correctly.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing issue statuses (current + changelog history)...")

        # Check if changelog items table exists for the second source
        changelog_exists = _table_exists(
            conn, "raw_jira", "issues__changelog__histories__items"
        )

        if changelog_exists:
            # Two-step approach to avoid (project_id, name) unique constraint conflicts
            # when the changelog contains duplicate names with different external_ids.

            # Step 1: sync current statuses - has accurate category info.
            sql_current = """
            INSERT INTO clean_jira.issue_statuses (
                project_id,
                external_id,
                name,
                category
            )
            SELECT DISTINCT
                p.id as project_id,
                r.fields__status__id as external_id,
                r.fields__status__name as name,
                CASE r.fields__status__status_category__key
                    WHEN 'new'           THEN 'to_do'::clean_jira.issue_status_category
                    WHEN 'indeterminate' THEN 'in_progress'::clean_jira.issue_status_category
                    WHEN 'done'          THEN 'done'::clean_jira.issue_status_category
                    ELSE 'to_do'::clean_jira.issue_status_category
                END as category
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__status__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category
            RETURNING id
            """
            result1 = conn.execute(text(sql_current))
            count = len(result1.fetchall())

            # Step 2: sync historical statuses from changelog that are not yet in the
            # table by external_id NOR by name. Uses DISTINCT ON (project_id, name) to
            # ensure only one row per name is inserted even if the changelog has the
            # same status name with multiple IDs.
            sql_changelog = """
            WITH changelog_candidates AS (
                SELECT DISTINCT ON (p.id, hi.to_string)
                    p.id as project_id,
                    hi.to as external_id,
                    hi.to_string as name,
                    CASE
                        WHEN LOWER(hi.to_string) IN ('done', 'canceled', 'cancelled',
                                                      'closed', 'resolved')
                            OR LOWER(hi.to_string) LIKE '%cancel%'
                            THEN 'done'::clean_jira.issue_status_category
                        WHEN LOWER(hi.to_string) IN ('to do',
                                                      'open', 'backlog', 'new', 'todo')
                            OR LOWER(hi.to_string) LIKE '%to do%'
                            THEN 'to_do'::clean_jira.issue_status_category
                        ELSE 'in_progress'::clean_jira.issue_status_category
                    END as category
                FROM raw_jira.issues__changelog__histories__items hi
                JOIN raw_jira.issues__changelog__histories h ON hi._dlt_parent_id = h._dlt_id
                JOIN raw_jira.issues r ON h._dlt_root_id = r._dlt_id
                JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
                WHERE hi.field = 'status'
                  AND hi.fieldtype = 'jira'
                  AND hi.to IS NOT NULL
                  AND hi.to_string IS NOT NULL
                ORDER BY p.id, hi.to_string, hi.to  -- deterministic: lowest external_id wins
            )
            INSERT INTO clean_jira.issue_statuses (
                project_id, external_id, name, category
            )
            SELECT project_id, external_id, name, category
            FROM changelog_candidates cc
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.issue_statuses s
                WHERE s.project_id = cc.project_id
                  AND (s.external_id = cc.external_id OR s.name = cc.name)
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """
            result2 = conn.execute(text(sql_changelog))
            count += len(result2.fetchall())
            sql = None  # handled above
        else:
            context.log.warning(
                "Changelog items table not found - syncing current statuses only"
            )
            sql = """
            INSERT INTO clean_jira.issue_statuses (
                project_id,
                external_id,
                name,
                category
            )
            SELECT DISTINCT
                p.id as project_id,
                r.fields__status__id as external_id,
                r.fields__status__name as name,
                CASE r.fields__status__status_category__key
                    WHEN 'new'         THEN 'to_do'::clean_jira.issue_status_category
                    WHEN 'indeterminate' THEN 'in_progress'::clean_jira.issue_status_category
                    WHEN 'done'        THEN 'done'::clean_jira.issue_status_category
                    ELSE 'to_do'::clean_jira.issue_status_category
                END as category
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__status__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category
            RETURNING id
            """

        if sql is not None:
            result = conn.execute(text(sql))
            count = len(result.fetchall())
        conn.commit()
    context.log.info(f"Synced {count} issue statuses")
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues"],
    description="Extract field keys from raw Jira issues",
    compute_kind="sql",
)
def clean_jira_field_keys(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract all custom field keys from raw Jira issues.

    Scans all fields__* columns in raw_jira.issues to build field_keys reference table.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting field keys from issues...")

        # Get all columns from raw_jira.issues
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
        context.log.info(f"Found {len(all_columns)} columns in raw_jira.issues")

        # Get all project IDs
        project_ids = [
            row[0]
            for row in conn.execute(
                text("SELECT id FROM clean_jira.projects")
            ).fetchall()
        ]

        field_data = []
        for col_name in all_columns:
            if not col_name.startswith("fields__"):
                continue
            if col_name.count("__") >= 3:
                continue
            if col_name.endswith("__self"):
                continue

            field_key = col_name.replace("fields__", "", 1)
            is_custom = field_key.startswith("customfield_")

            if is_custom:
                field_name = field_key
            else:
                field_name = field_key.replace("_", " ").title()

            for p_id in project_ids:
                field_data.append(
                    {
                        "project_id": p_id,
                        "external_key": field_key,
                        "name": field_name,
                        "is_custom": is_custom,
                    }
                )

        if field_data:
            # Multi-row batch insert
            conn.execute(
                text(
                    """
                INSERT INTO clean_jira.field_keys (
                    project_id,
                    external_key,
                    name,
                    is_custom,
                    created_at
                )
                VALUES (:project_id, :external_key, :name, :is_custom, now())
                ON CONFLICT (project_id, external_key) DO UPDATE SET
                    name = EXCLUDED.name
                """
                ),
                field_data,
            )

        context.log.info(f"Inserted {len(field_data)} field key rows")

        # Try to get human-readable names from raw_jira.fields if it exists
        fields_table_exists = _table_exists(conn, "raw_jira", "fields")

        if fields_table_exists:
            context.log.info("Updating field names from raw_jira.fields metadata...")
            # Update names matching exact ID
            conn.execute(
                text(
                    """
                UPDATE clean_jira.field_keys fk
                SET name = f.name
                FROM raw_jira.fields f
                WHERE fk.external_key = f.id
                  AND f.name IS NOT NULL
            """
                )
            )
            # Update names for sub-fields (e.g. customfield_10001__value)
            conn.execute(
                text(
                    """
                UPDATE clean_jira.field_keys fk
                SET name = f.name || ' (' || SUBSTRING(
                    fk.external_key FROM LENGTH(f.id) + 3
                ) || ')'
                FROM raw_jira.fields f
                WHERE fk.external_key LIKE f.id || '__%'
                  AND f.name IS NOT NULL
                  AND fk.name = fk.external_key -- Only update if still using raw key
            """
                )
            )

        conn.commit()

        # Explicitly ensure 'Sprint' field key exists
        sprint_field_id = _detect_sprint_field_id(conn)
        conn.execute(
            text(
                """
            INSERT INTO clean_jira.field_keys (
                project_id,
                external_key,
                name,
                is_custom,
                created_at
            )
            SELECT DISTINCT
                p.id as project_id,
                :sprint_field_id as external_key,
                'Sprint' as name,
                true as is_custom,
                now() as created_at
            FROM clean_jira.projects p
            ON CONFLICT (project_id, external_key) DO UPDATE SET
                name = EXCLUDED.name
        """
            ),
            {"sprint_field_id": sprint_field_id},
        )
        conn.commit()

    return {
        "status": "success",
        "field_keys_inserted": len(field_data),
    }
