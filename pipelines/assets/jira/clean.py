"""Clean Jira assets - transform raw data to normalized clean layer.

This module implements the clean layer (Silver) of the medallion architecture.
Data is transformed from raw_jira schema to clean_jira schema with normalization.
"""

from typing import Any

from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetExecutionContext,
    asset,
    asset_check,
)
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data"],
    description="Transform raw Jira issues to clean normalized format",
    compute_kind="sql",
)
def clean_jira_issues(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Transform raw Jira issues to clean_jira.issues table.

    This asset:
    - Normalizes issue data from raw layer
    - Creates/updates project, issue_type, and status dimension tables
    - Links issues to their parent issues
    - Extracts changelog into status_changes
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        # Get or create default Jira integration for syncing
        context.log.info("Getting system user and Jira integration...")
        system_integration = conn.execute(
            text("""
            SELECT ti.id FROM platform.tool_integrations ti
            JOIN platform.users u ON ti.user_id = u.id
            WHERE u.email = 'system@metrics.local'
              AND ti.integration_type_id = (
                  SELECT id FROM platform.integration_types WHERE name = 'jira_cloud'
              )
            LIMIT 1
        """)
        ).first()

        if not system_integration:
            raise RuntimeError(
                "System Jira integration not found. "
                "Please run: docker-compose exec app alembic upgrade head"
            )

        system_integration_id = system_integration[0]
        context.log.info(f"Using system integration: {system_integration_id}")

        # Use a fixed platform_project_id for grouping all Jira projects
        # This represents the logical "Jira" platform project in clean layer
        platform_project_id = "00000000-0000-0000-0000-000000000001"

        # Sync projects from raw to clean
        context.log.info("Syncing projects...")
        projects_synced = conn.execute(
            text(f"""
            INSERT INTO clean_jira.projects (
                platform_project_id,
                external_id,
                external_key,
                name,
                created_at,
                updated_at
            )
            SELECT
                '{platform_project_id}'::uuid as platform_project_id,
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
        """)
        ).fetchall()
        context.log.info(f"Synced {len(projects_synced)} projects")

        # Sync issue types
        context.log.info("Syncing issue types...")
        conn.execute(
            text("""
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
                CASE
                    WHEN r.fields__issuetype__name ILIKE '%epic%' THEN 'epic'::clean_jira.issue_hierarchy_level
                    WHEN r.fields__issuetype__name ILIKE '%subtask%' THEN 'subtask'::clean_jira.issue_hierarchy_level
                    WHEN r.fields__issuetype__name ILIKE '%story%' THEN 'story'::clean_jira.issue_hierarchy_level
                    ELSE 'task'::clean_jira.issue_hierarchy_level
                END as hierarchy_level
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__issuetype__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name
        """)
        )

        # Sync issue statuses
        context.log.info("Syncing issue statuses...")
        conn.execute(
            text("""
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
                    WHEN 'new' THEN 'to_do'::clean_jira.issue_status_category
                    WHEN 'indeterminate' THEN 'in_progress'::clean_jira.issue_status_category
                    WHEN 'done' THEN 'done'::clean_jira.issue_status_category
                    ELSE 'to_do'::clean_jira.issue_status_category
                END as category
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE r.fields__status__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category
        """)
        )

        # Sync Jira users from raw_jira.users
        context.log.info("Syncing Jira users...")
        conn.execute(
            text("""
            INSERT INTO clean_jira.jira_users (
                project_id,
                external_id,
                display_name,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                p.id as project_id,
                u.account_id as external_id,
                u.display_name,
                now() as created_at,
                now() as updated_at
            FROM raw_jira.users u
            CROSS JOIN clean_jira.projects p
            WHERE u.account_id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                updated_at = now()
        """)
        )

        # Also extract users from issue changelog authors
        context.log.info("Extracting users from changelog...")
        conn.execute(
            text("""
            INSERT INTO clean_jira.jira_users (
                project_id,
                external_id,
                display_name,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                p.id as project_id,
                (h->>'author')::jsonb->>'accountId' as external_id,
                COALESCE(
                    (h->>'author')::jsonb->>'displayName',
                    (h->>'author')::jsonb->>'accountId'
                ) as display_name,
                now() as created_at,
                now() as updated_at
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            CROSS JOIN LATERAL jsonb_array_elements(r.changelog->'histories') as h
            WHERE r.changelog IS NOT NULL
              AND (h->>'author')::jsonb->>'accountId' IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, clean_jira.jira_users.display_name),
                updated_at = now()
        """)
        )

        # Sync issues
        context.log.info("Syncing issues...")

        # Check if optional fields exist in raw_jira.issues
        columns_result = conn.execute(
            text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'raw_jira' AND table_name = 'issues'
            AND column_name IN ('rendered_fields__description', 'fields__resolutiondate')
        """)
        ).fetchall()

        column_names = {row[0] for row in columns_result}
        has_description = "rendered_fields__description" in column_names
        has_resolutiondate = "fields__resolutiondate" in column_names

        description_col = "r.rendered_fields__description" if has_description else "NULL::text"
        resolutiondate_col = "r.fields__resolutiondate" if has_resolutiondate else "NULL::text"

        issues_result = conn.execute(
            text(f"""
            INSERT INTO clean_jira.issues (
                project_id,
                external_id,
                external_key,
                summary,
                description,
                type_id,
                status_id,
                jira_created_at,
                jira_updated_at,
                jira_resolved_at,
                db_created_at,
                db_updated_at
            )
            SELECT
                p.id as project_id,
                r.id::text as external_id,
                r.key as external_key,
                r.fields__summary as summary,
                {description_col} as description,
                it.id as type_id,
                ist.id as status_id,
                r.fields__created::timestamptz as jira_created_at,
                r.fields__updated::timestamptz as jira_updated_at,
                {resolutiondate_col}::timestamptz as jira_resolved_at,
                now() as db_created_at,
                now() as db_updated_at
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issue_types it ON it.project_id = p.id
                AND it.external_id = r.fields__issuetype__id
            JOIN clean_jira.issue_statuses ist ON ist.project_id = p.id
                AND ist.external_id = r.fields__status__id
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                external_key = EXCLUDED.external_key,
                summary = EXCLUDED.summary,
                description = EXCLUDED.description,
                type_id = EXCLUDED.type_id,
                status_id = EXCLUDED.status_id,
                jira_updated_at = EXCLUDED.jira_updated_at,
                jira_resolved_at = EXCLUDED.jira_resolved_at,
                db_updated_at = now()
            RETURNING id
        """)
        )
        issues_synced = issues_result.fetchall()
        context.log.info(f"Synced {len(issues_synced)} issues")

        conn.commit()

    return {
        "status": "success",
        "projects_synced": len(projects_synced),
        "issues_synced": len(issues_synced),
    }


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data"],
    description="Transform raw Jira sprints to clean normalized format",
    compute_kind="sql",
)
def clean_jira_sprints(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Transform raw Jira sprints to clean_jira.sprints table."""
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Syncing sprints...")

        # Need to link sprints to projects via board -> project relationship
        # First, get board_id -> project_key mapping from raw_jira.sprints
        result = conn.execute(
            text("""
            INSERT INTO clean_jira.sprints (
                project_id,
                external_id,
                name,
                goal,
                status,
                start_date,
                end_date,
                complete_date,
                updated_at
            )
            SELECT DISTINCT ON (p.id, s.id::text)
                p.id as project_id,
                s.id::text as external_id,
                s.name,
                s.goal,
                CASE s.state
                    WHEN 'future' THEN 'future'::clean_jira.sprint_status
                    WHEN 'active' THEN 'active'::clean_jira.sprint_status
                    WHEN 'closed' THEN 'closed'::clean_jira.sprint_status
                    ELSE 'future'::clean_jira.sprint_status
                END as status,
                s.start_date::timestamptz as start_date,
                s.end_date::timestamptz as end_date,
                s.complete_date::timestamptz as complete_date,
                now() as updated_at
            FROM raw_jira.sprints s
            CROSS JOIN clean_jira.projects p
            WHERE s.id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                goal = EXCLUDED.goal,
                status = EXCLUDED.status,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                complete_date = EXCLUDED.complete_date,
                updated_at = now()
            RETURNING id
        """)
        )
        sprints_synced = result.fetchall()
        context.log.info(f"Synced {len(sprints_synced)} sprints")

        conn.commit()

    return {
        "status": "success",
        "sprints_synced": len(sprints_synced),
    }


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

        # Get all fields__* columns from raw_jira.issues
        columns_result = conn.execute(
            text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw_jira'
              AND table_name = 'issues'
              AND column_name LIKE 'fields__%'
              AND column_name NOT LIKE '%__%__%__%'  -- Skip deeply nested
        """)
        ).fetchall()

        field_keys_inserted = 0

        # Insert standard and custom field keys
        for (col_name,) in columns_result:
            # Extract field key from column name (e.g., fields__customfield_10001 -> customfield_10001)
            field_key = col_name.replace("fields__", "")
            is_custom = field_key.startswith("customfield_")

            # Derive human-readable name from key
            if is_custom:
                field_name = field_key  # Will be updated from metadata if available
            else:
                field_name = field_key.replace("_", " ").title()

            conn.execute(
                text("""
                INSERT INTO clean_jira.field_keys (
                    project_id,
                    external_key,
                    name,
                    is_custom,
                    created_at
                )
                SELECT DISTINCT
                    p.id as project_id,
                    :field_key as external_key,
                    :field_name as name,
                    :is_custom as is_custom,
                    now() as created_at
                FROM clean_jira.projects p
                ON CONFLICT (project_id, external_key) DO UPDATE SET
                    name = EXCLUDED.name
            """),
                {"field_key": field_key, "field_name": field_name, "is_custom": is_custom},
            )
            field_keys_inserted += 1

        context.log.info(f"Inserted {field_keys_inserted} field keys")

        # Try to get human-readable names from raw_jira.fields if it exists
        fields_table_exists = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'fields'
            )
        """)
        ).scalar()

        if fields_table_exists:
            context.log.info("Updating field names from raw_jira.fields metadata...")
            conn.execute(
                text("""
                UPDATE clean_jira.field_keys fk
                SET name = f.name
                FROM raw_jira.fields f
                WHERE fk.external_key = f.id
                  AND f.name IS NOT NULL
            """)
            )

        conn.commit()

    return {
        "status": "success",
        "field_keys_inserted": field_keys_inserted,
    }


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

        # Get all custom field columns
        columns_result = conn.execute(
            text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'raw_jira'
              AND table_name = 'issues'
              AND column_name LIKE 'fields__customfield_%'
              AND column_name NOT LIKE '%__%__%__%'
        """)
        ).fetchall()

        for (col_name,) in columns_result:
            field_key = col_name.replace("fields__", "")

            try:
                result = conn.execute(
                    text(f"""
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
                        r.{col_name}::text as value,
                        CASE
                            WHEN r.{col_name}::text ~ '^[{{\\[]' THEN r.{col_name}::text::jsonb
                            ELSE NULL
                        END as json_value,
                        now() as updated_at
                    FROM raw_jira.issues r
                    JOIN clean_jira.issues i ON i.external_id = r.id::text
                    JOIN clean_jira.field_keys fk ON fk.project_id = i.project_id
                        AND fk.external_key = :field_key
                    WHERE r.{col_name} IS NOT NULL
                    ON CONFLICT (issue_id, field_key_id) DO UPDATE SET
                        value = EXCLUDED.value,
                        json_value = EXCLUDED.json_value,
                        updated_at = now()
                    RETURNING id
                """),
                    {"field_key": field_key},
                )
                count = len(result.fetchall())
                field_values_inserted += count
            except Exception as e:
                context.log.warning(f"Failed to extract values for {field_key}: {e}")

        context.log.info(f"Inserted {field_values_inserted} field values")
        conn.commit()

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

        # Check if changelog column exists
        changelog_exists = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues'
                  AND column_name = 'changelog'
            )
        """)
        ).scalar()

        if not changelog_exists:
            context.log.warning("No changelog column found in raw_jira.issues")
            return {"status": "skipped", "reason": "no_changelog_column"}

        result = conn.execute(
            text("""
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
                to_jsonb(item->>'fromString') as old_value,
                to_jsonb(item->>'toString') as new_value,
                u.id as changed_by_id,
                (h->>'created')::timestamptz as changed_at
            FROM raw_jira.issues r
            JOIN clean_jira.issues i ON i.external_id = r.id::text
            CROSS JOIN LATERAL jsonb_array_elements(r.changelog->'histories') as h
            CROSS JOIN LATERAL jsonb_array_elements(h->'items') as item
            JOIN clean_jira.field_keys fk ON fk.project_id = i.project_id
                AND (
                    fk.external_key = item->>'fieldId'
                    OR fk.external_key = LOWER(REPLACE(item->>'field', ' ', '_'))
                )
            LEFT JOIN clean_jira.jira_users u ON u.project_id = i.project_id
                AND u.external_id = (h->'author'->>'accountId')
            WHERE r.changelog IS NOT NULL
              AND (item->>'fieldId' LIKE 'customfield_%'
                   OR item->>'field' NOT IN ('Sprint', 'Fix Version/s', 'fixVersions', 'Fix Version', 'Status'))
            ON CONFLICT (issue_id, field_key_id, changed_at) DO NOTHING
            RETURNING id
        """)
        )
        changes_count = len(result.fetchall())
        context.log.info(f"Inserted {changes_count} field value changelog entries")

        conn.commit()

    return {
        "status": "success",
        "changes_count": changes_count,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues", "clean_jira_sprints"],
    description="Extract sprint-issue relationships from changelog",
    compute_kind="sql",
)
def clean_jira_sprint_issues(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract sprint-issue relationships from changelog.

    Parses the changelog JSON to find Sprint field changes and determines
    the final state (which issues are currently in which sprints).

    Key logic:
    - 'to' value means issue was ADDED to sprint
    - 'from' value means issue was REMOVED from sprint
    - Final state is determined by the last action for each issue-sprint pair
    - Comma-separated values are split using regexp_split_to_table
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting sprint-issue relationships from changelog...")

        # Check if changelog exists
        changelog_exists = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues'
                  AND column_name = 'changelog'
            )
        """)
        ).scalar()

        if not changelog_exists:
            context.log.warning("No changelog column found")
            return {"status": "skipped", "reason": "no_changelog_column"}

        # Build sprint_issues from changelog final state
        result = conn.execute(
            text("""
            WITH changelog_events AS (
                -- Extract Sprint changes from changelog
                SELECT
                    r.id::text as issue_external_id,
                    r.fields__project__id::text as project_external_id,
                    (h->>'created')::timestamptz as changed_at,
                    item->>'to' as to_value,
                    item->>'from' as from_value,
                    (h->'author'->>'accountId') as author_id
                FROM raw_jira.issues r
                CROSS JOIN LATERAL jsonb_array_elements(r.changelog->'histories') as h
                CROSS JOIN LATERAL jsonb_array_elements(h->'items') as item
                WHERE r.changelog IS NOT NULL
                  AND item->>'field' = 'Sprint'
            ),
            -- Split comma-separated sprint IDs for 'added' actions
            added_events AS (
                SELECT
                    issue_external_id,
                    project_external_id,
                    changed_at,
                    trim(sprint_id) as sprint_external_id,
                    'added' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(COALESCE(to_value, ''), '\\s*,\\s*') as sprint_id
                WHERE to_value IS NOT NULL AND to_value != ''
            ),
            -- Split comma-separated sprint IDs for 'removed' actions
            removed_events AS (
                SELECT
                    issue_external_id,
                    project_external_id,
                    changed_at,
                    trim(sprint_id) as sprint_external_id,
                    'removed' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(COALESCE(from_value, ''), '\\s*,\\s*') as sprint_id
                WHERE from_value IS NOT NULL AND from_value != ''
            ),
            -- Union all events
            all_events AS (
                SELECT * FROM added_events
                UNION ALL
                SELECT * FROM removed_events
            ),
            -- Get the latest action for each issue-sprint pair
            latest_action AS (
                SELECT DISTINCT ON (issue_external_id, sprint_external_id)
                    issue_external_id,
                    sprint_external_id,
                    action,
                    changed_at
                FROM all_events
                WHERE sprint_external_id ~ '^[0-9]+$'  -- Only numeric sprint IDs
                ORDER BY issue_external_id, sprint_external_id, changed_at DESC
            )
            -- Insert only pairs where final action is 'added'
            INSERT INTO clean_jira.sprint_issues (
                sprint_id,
                issue_id,
                is_active
            )
            SELECT
                s.id as sprint_id,
                i.id as issue_id,
                true as is_active
            FROM latest_action la
            JOIN clean_jira.issues i ON i.external_id = la.issue_external_id
            JOIN clean_jira.sprints s ON s.project_id = i.project_id
                AND s.external_id = la.sprint_external_id
            WHERE la.action = 'added'
            ON CONFLICT (sprint_id, issue_id) DO UPDATE SET
                is_active = EXCLUDED.is_active
            RETURNING id
        """)
        )
        sprint_issues_count = len(result.fetchall())
        context.log.info(f"Inserted {sprint_issues_count} sprint-issue relationships")

        conn.commit()

    return {
        "status": "success",
        "sprint_issues_count": sprint_issues_count,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_sprint_issues"],
    description="Extract sprint-issue changelog (add/remove history)",
    compute_kind="sql",
)
def clean_jira_sprint_issues_changelog(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract full history of sprint-issue changes.

    Records every time an issue was added to or removed from a sprint.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting sprint-issue changelog...")

        result = conn.execute(
            text("""
            WITH changelog_events AS (
                SELECT
                    r.id::text as issue_external_id,
                    (h->>'created')::timestamptz as changed_at,
                    item->>'to' as to_value,
                    item->>'from' as from_value,
                    (h->'author'->>'accountId') as author_id
                FROM raw_jira.issues r
                CROSS JOIN LATERAL jsonb_array_elements(r.changelog->'histories') as h
                CROSS JOIN LATERAL jsonb_array_elements(h->'items') as item
                WHERE r.changelog IS NOT NULL
                  AND item->>'field' = 'Sprint'
            ),
            added_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(sprint_id) as sprint_external_id,
                    'added' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(COALESCE(to_value, ''), '\\s*,\\s*') as sprint_id
                WHERE to_value IS NOT NULL AND to_value != '' AND sprint_id ~ '^[0-9]+$'
            ),
            removed_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(sprint_id) as sprint_external_id,
                    'removed' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(COALESCE(from_value, ''), '\\s*,\\s*') as sprint_id
                WHERE from_value IS NOT NULL AND from_value != '' AND sprint_id ~ '^[0-9]+$'
            ),
            all_events AS (
                SELECT * FROM added_events
                UNION ALL
                SELECT * FROM removed_events
            )
            INSERT INTO clean_jira.sprint_issues_changelog (
                sprint_id,
                issue_id,
                action,
                changed_by_id,
                changed_at
            )
            SELECT
                s.id as sprint_id,
                i.id as issue_id,
                ae.action,
                u.id as changed_by_id,
                ae.changed_at
            FROM all_events ae
            JOIN clean_jira.issues i ON i.external_id = ae.issue_external_id
            JOIN clean_jira.sprints s ON s.project_id = i.project_id
                AND s.external_id = ae.sprint_external_id
            LEFT JOIN clean_jira.jira_users u ON u.project_id = i.project_id
                AND u.external_id = ae.author_id
            ON CONFLICT (sprint_id, issue_id, action, changed_at) DO NOTHING
            RETURNING id
        """)
        )
        changelog_count = len(result.fetchall())
        context.log.info(f"Inserted {changelog_count} sprint-issue changelog entries")

        conn.commit()

    return {
        "status": "success",
        "changelog_count": changelog_count,
    }


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data"],
    description="Transform raw Jira versions to clean releases",
    compute_kind="sql",
)
def clean_jira_releases(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Transform raw Jira versions to clean_jira.releases table."""
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Syncing releases from versions...")

        # Check if versions table exists
        versions_exists = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'versions'
            )
        """)
        ).scalar()

        if not versions_exists:
            context.log.warning("No versions table found in raw_jira")
            return {"status": "skipped", "reason": "no_versions_table"}

        result = conn.execute(
            text("""
            INSERT INTO clean_jira.releases (
                project_id,
                external_id,
                name,
                description,
                status,
                start_date,
                release_date,
                is_archived,
                is_released,
                created_at,
                updated_at
            )
            SELECT
                p.id as project_id,
                v.id::text as external_id,
                v.name,
                v.description,
                CASE
                    WHEN v.released = true THEN 'released'::clean_jira.release_status
                    WHEN v.archived = true THEN 'archived'::clean_jira.release_status
                    ELSE 'unreleased'::clean_jira.release_status
                END as status,
                v.start_date::date as start_date,
                v.release_date::date as release_date,
                COALESCE(v.archived, false) as is_archived,
                COALESCE(v.released, false) as is_released,
                now() as created_at,
                now() as updated_at
            FROM raw_jira.versions v
            JOIN clean_jira.projects p ON p.external_id = v.project_id::text
            WHERE v.id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                start_date = EXCLUDED.start_date,
                release_date = EXCLUDED.release_date,
                is_archived = EXCLUDED.is_archived,
                is_released = EXCLUDED.is_released,
                updated_at = now()
            RETURNING id
        """)
        )
        releases_count = len(result.fetchall())
        context.log.info(f"Synced {releases_count} releases")

        conn.commit()

    return {
        "status": "success",
        "releases_count": releases_count,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues", "clean_jira_releases"],
    description="Extract release-issue relationships from changelog",
    compute_kind="sql",
)
def clean_jira_release_issues(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract release-issue relationships from changelog.

    Similar to sprint_issues, parses Fix Version field changes from changelog.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting release-issue relationships from changelog...")

        # Check if releases exist
        releases_count = conn.execute(
            text("SELECT COUNT(*) FROM clean_jira.releases")
        ).scalar()

        if releases_count == 0:
            context.log.warning("No releases found, skipping release_issues")
            return {"status": "skipped", "reason": "no_releases"}

        result = conn.execute(
            text("""
            WITH changelog_events AS (
                SELECT
                    r.id::text as issue_external_id,
                    (h->>'created')::timestamptz as changed_at,
                    item->>'to' as to_value,
                    item->>'from' as from_value,
                    (h->'author'->>'accountId') as author_id
                FROM raw_jira.issues r
                CROSS JOIN LATERAL jsonb_array_elements(r.changelog->'histories') as h
                CROSS JOIN LATERAL jsonb_array_elements(h->'items') as item
                WHERE r.changelog IS NOT NULL
                  AND item->>'field' IN ('Fix Version/s', 'fixVersions', 'Fix Version')
            ),
            added_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(version_id) as version_external_id,
                    'added' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(COALESCE(to_value, ''), '\\s*,\\s*') as version_id
                WHERE to_value IS NOT NULL AND to_value != ''
            ),
            removed_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(version_id) as version_external_id,
                    'removed' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(COALESCE(from_value, ''), '\\s*,\\s*') as version_id
                WHERE from_value IS NOT NULL AND from_value != ''
            ),
            all_events AS (
                SELECT * FROM added_events
                UNION ALL
                SELECT * FROM removed_events
            ),
            latest_action AS (
                SELECT DISTINCT ON (issue_external_id, version_external_id)
                    issue_external_id,
                    version_external_id,
                    action,
                    changed_at
                FROM all_events
                WHERE version_external_id ~ '^[0-9]+$'
                ORDER BY issue_external_id, version_external_id, changed_at DESC
            )
            INSERT INTO clean_jira.release_issues (
                release_id,
                issue_id,
                is_active
            )
            SELECT
                rel.id as release_id,
                i.id as issue_id,
                true as is_active
            FROM latest_action la
            JOIN clean_jira.issues i ON i.external_id = la.issue_external_id
            JOIN clean_jira.releases rel ON rel.project_id = i.project_id
                AND rel.external_id = la.version_external_id
            WHERE la.action = 'added'
            ON CONFLICT (release_id, issue_id) DO UPDATE SET
                is_active = EXCLUDED.is_active
            RETURNING id
        """)
        )
        release_issues_count = len(result.fetchall())
        context.log.info(f"Inserted {release_issues_count} release-issue relationships")

        conn.commit()

    return {
        "status": "success",
        "release_issues_count": release_issues_count,
    }


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_issues"],
    description="Transform raw Jira board configurations to clean format",
    compute_kind="sql",
)
def clean_jira_boards(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Transform raw Jira board configurations to clean_jira.boards, board_columns, and board_column_statuses."""
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Syncing boards...")

        # Check if board_configurations table exists
        boards_exists = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'board_configurations'
            )
        """)
        ).scalar()

        if not boards_exists:
            context.log.warning("No board_configurations table found in raw_jira")
            return {"status": "skipped", "reason": "no_board_configurations_table"}

        # Sync boards
        boards_result = conn.execute(
            text("""
            INSERT INTO clean_jira.boards (
                project_id,
                external_id,
                name,
                created_at
            )
            SELECT
                p.id as project_id,
                bc.board_id::text as external_id,
                bc.board_name as name,
                now() as created_at
            FROM raw_jira.board_configurations bc
            JOIN clean_jira.projects p ON p.external_key = bc.project_key
            WHERE bc.board_id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name
            RETURNING id
        """)
        )
        boards_count = len(boards_result.fetchall())
        context.log.info(f"Synced {boards_count} boards")

        # Sync board columns from columns_config JSON
        context.log.info("Syncing board columns...")
        columns_result = conn.execute(
            text("""
            INSERT INTO clean_jira.board_columns (
                board_id,
                name,
                position
            )
            SELECT
                b.id as board_id,
                col->>'name' as name,
                (col_idx.ordinality)::int as position
            FROM raw_jira.board_configurations bc
            JOIN clean_jira.projects p ON p.external_key = bc.project_key
            JOIN clean_jira.boards b ON b.project_id = p.id AND b.external_id = bc.board_id::text
            CROSS JOIN LATERAL jsonb_array_elements(bc.columns_config->'columns')
                WITH ORDINALITY AS col_idx(col, ordinality)
            WHERE bc.columns_config IS NOT NULL
              AND jsonb_typeof(bc.columns_config->'columns') = 'array'
            ON CONFLICT (board_id, name) DO UPDATE SET
                position = EXCLUDED.position
            RETURNING id
        """)
        )
        columns_count = len(columns_result.fetchall())
        context.log.info(f"Synced {columns_count} board columns")

        # Sync board column statuses
        context.log.info("Syncing board column statuses...")
        statuses_result = conn.execute(
            text("""
            INSERT INTO clean_jira.board_column_statuses (
                board_column_id,
                status_id
            )
            SELECT
                bc_col.id as board_column_id,
                ist.id as status_id
            FROM raw_jira.board_configurations cfg
            JOIN clean_jira.projects p ON p.external_key = cfg.project_key
            JOIN clean_jira.boards b ON b.project_id = p.id AND b.external_id = cfg.board_id::text
            CROSS JOIN LATERAL jsonb_array_elements(cfg.columns_config->'columns')
                WITH ORDINALITY AS col_data(col, col_ord)
            JOIN clean_jira.board_columns bc_col ON bc_col.board_id = b.id
                AND bc_col.name = col_data.col->>'name'
            CROSS JOIN LATERAL jsonb_array_elements(col_data.col->'statuses') AS status_data(status)
            JOIN clean_jira.issue_statuses ist ON ist.project_id = p.id
                AND ist.external_id = status_data.status->>'id'
            WHERE cfg.columns_config IS NOT NULL
              AND jsonb_typeof(cfg.columns_config->'columns') = 'array'
            ON CONFLICT (board_column_id, status_id) DO NOTHING
            RETURNING id
        """)
        )
        statuses_count = len(statuses_result.fetchall())
        context.log.info(f"Synced {statuses_count} board column statuses")

        conn.commit()

    return {
        "status": "success",
        "boards_count": boards_count,
        "columns_count": columns_count,
        "statuses_count": statuses_count,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues"],
    description="Extract and transform status changes from issue changelogs",
    compute_kind="sql",
)
def clean_jira_status_changes(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract status changes from raw changelog data.

    Note: This is a simplified version. Full implementation would
    parse the changelog JSON from raw_jira.issues.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        # Check if changelog data exists
        context.log.info("Processing status changes from changelog...")

        # For now, we'll create a placeholder that can be extended
        # when changelog parsing is fully implemented
        conn.execute(
            text("""
            -- Placeholder: Status changes extraction would go here
            -- This requires parsing the changelog JSON array from raw issues
            SELECT 1
        """)
        )

        conn.commit()

    return {
        "status": "success",
        "message": "Status changes processing placeholder",
    }


# Asset checks for data quality


@asset_check(asset=clean_jira_issues)
def check_no_orphan_issues(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure all issues have valid project_id."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM clean_jira.issues i
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.projects p
                WHERE p.id = i.project_id
            )
        """)
        )
        orphan_count = result.scalar() or 0

    return AssetCheckResult(
        passed=orphan_count == 0,
        metadata={"orphan_count": orphan_count},
    )


@asset_check(asset=clean_jira_issues)
def check_issues_have_required_fields(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure all issues have required fields populated."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM clean_jira.issues
            WHERE external_key IS NULL
               OR summary IS NULL
               OR type_id IS NULL
               OR status_id IS NULL
        """)
        )
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_issues_count": invalid_count},
    )


@asset_check(asset=clean_jira_sprints)
def check_sprint_dates_valid(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure sprint dates are logically valid (start < end)."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM clean_jira.sprints
            WHERE start_date IS NOT NULL
              AND end_date IS NOT NULL
              AND start_date > end_date
        """)
        )
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_sprint_dates_count": invalid_count},
    )


@asset_check(asset=clean_jira_sprint_issues)
def check_sprint_issues_integrity(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure all sprint_issues have valid sprint and issue references."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM clean_jira.sprint_issues si
            WHERE NOT EXISTS (SELECT 1 FROM clean_jira.sprints s WHERE s.id = si.sprint_id)
               OR NOT EXISTS (SELECT 1 FROM clean_jira.issues i WHERE i.id = si.issue_id)
        """)
        )
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_sprint_issues_count": invalid_count},
    )


@asset_check(asset=clean_jira_release_issues)
def check_release_issues_integrity(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure all release_issues have valid release and issue references."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT count(*) FROM clean_jira.release_issues ri
            WHERE NOT EXISTS (SELECT 1 FROM clean_jira.releases r WHERE r.id = ri.release_id)
               OR NOT EXISTS (SELECT 1 FROM clean_jira.issues i WHERE i.id = ri.issue_id)
        """)
        )
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_release_issues_count": invalid_count},
    )
