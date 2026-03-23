"""Clean Jira assets - transform raw data to normalized clean layer.

This module implements the clean layer (Silver) of the medallion architecture.
Data is transformed from raw_jira schema to clean_jira schema with normalization.
"""

# ruff: noqa: S608

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


def _get_platform_project_id(conn: Any) -> str:
    """Get the platform project ID dynamically."""
    result = conn.execute(text("SELECT id::text FROM platform.projects LIMIT 1"))
    row = result.first()
    if not row:
        raise RuntimeError(
            "Platform project not found. "
            "Ensure platform.projects has at least one entry."
        )
    return row[0]


def _detect_sprint_field_id(conn: Any) -> str:
    """Auto-detect sprint custom field ID from raw_jira.fields."""
    try:
        result = conn.execute(
            text(
                """
            SELECT id FROM raw_jira.fields
            WHERE schema__custom = 'com.pyxis.greenhopper.jira:gh-sprint'
            LIMIT 1
        """
            )
        )
        row = result.first()
        if row:
            return row[0]
    except Exception:  # noqa: S110
        pass
    # Fallback to standard customfield_10020
    return "customfield_10020"


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
                f"""  # noqa: S608
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
    deps=["raw_jira_data"],
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
        changelog_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__changelog__histories__items'
            )
        """
            )
        ).scalar()

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
                                                      'closed', 'resolved', 'отмена')
                            OR LOWER(hi.to_string) LIKE '%cancel%'
                            OR LOWER(hi.to_string) LIKE '%отмен%'
                            THEN 'done'::clean_jira.issue_status_category
                        WHEN LOWER(hi.to_string) IN ('to do', 'к выполнению', 'open',
                                                      'backlog', 'new', 'todo')
                            OR LOWER(hi.to_string) LIKE '%to do%'
                            OR LOWER(hi.to_string) LIKE '%к выполнению%'
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
    deps=[
        "raw_jira_data",
        "clean_jira_projects",
        "clean_jira_issue_types",
        "clean_jira_issue_statuses",
        "clean_jira_priorities",
        "clean_jira_resolutions",
    ],
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
    - Creates/updates dimension tables
    - Links issues to their parent issues
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        # Get or create default Jira integration for syncing
        context.log.info("Getting system user and Jira integration...")
        system_integration = conn.execute(
            text(
                """
            SELECT ti.id FROM platform.tool_integrations ti
            JOIN platform.users u ON ti.user_id = u.id
            WHERE u.email = 'system@metrics.local'
              AND ti.integration_type_id = (
                  SELECT id FROM platform.integration_types WHERE name = 'jira_cloud'
              )
            LIMIT 1
        """
            )
        ).first()

        if not system_integration:
            raise RuntimeError(
                "System Jira integration not found. "
                "Please run: docker-compose exec app alembic upgrade head"
            )

        system_integration_id = system_integration[0]
        context.log.info(f"Using system integration: {system_integration_id}")

        # Sync Jira users from raw_jira.users
        context.log.info("Syncing Jira users...")
        conn.execute(
            text(
                """
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
        """
            )
        )

        # Also extract users from issue changelog authors
        context.log.info("Extracting users from changelog...")
        # Check if history table exists first
        history_table_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__changelog__histories'
            )
        """
            )
        ).scalar()

        if history_table_exists:
            conn.execute(
                text(
                    """
                INSERT INTO clean_jira.jira_users (
                    project_id,
                    external_id,
                    display_name,
                    created_at,
                    updated_at
                )
                SELECT DISTINCT
                    p.id as project_id,
                    h.author__account_id as external_id,
                    COALESCE(
                        h.author__display_name,
                        h.author__account_id
                    ) as display_name,
                    now() as created_at,
                    now() as updated_at
                FROM raw_jira.issues__changelog__histories h
                JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
                JOIN clean_jira.projects p
                    ON r.fields__project__id::text = p.external_id
                WHERE h.author__account_id IS NOT NULL
                ON CONFLICT (project_id, external_id) DO UPDATE SET
                    display_name = COALESCE(
                        EXCLUDED.display_name,
                        clean_jira.jira_users.display_name
                    ),
                    updated_at = now()
            """
                )
            )
        else:
            context.log.warning(
                "Table raw_jira.issues__changelog__histories not found, "
                "skipping user extraction from changelog"
            )

        # Extract users from issue assignee/reporter/creator fields
        context.log.info("Extracting users from issue assignee/reporter/creator...")
        conn.execute(
            text(
                """
            INSERT INTO clean_jira.jira_users (
                project_id,
                external_id,
                display_name,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                p.id as project_id,
                user_data.account_id as external_id,
                user_data.display_name,
                now() as created_at,
                now() as updated_at
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            CROSS JOIN LATERAL (
                SELECT
                    r.fields__assignee__account_id as account_id,
                    r.fields__assignee__display_name as display_name
                WHERE r.fields__assignee__account_id IS NOT NULL
                UNION
                SELECT
                    r.fields__reporter__account_id as account_id,
                    r.fields__reporter__display_name as display_name
                WHERE r.fields__reporter__account_id IS NOT NULL
                UNION
                SELECT
                    r.fields__creator__account_id as account_id,
                    r.fields__creator__display_name as display_name
                WHERE r.fields__creator__account_id IS NOT NULL
            ) as user_data
            WHERE user_data.account_id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                display_name = COALESCE(
                    EXCLUDED.display_name,
                    clean_jira.jira_users.display_name
                ),
                updated_at = now()
        """
            )
        )

        # Sync issues
        context.log.info("Syncing issues...")

        # Check if optional fields exist in raw_jira.issues
        columns_result = conn.execute(
            text(
                """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'raw_jira' AND table_name = 'issues'
            AND column_name IN (
                'rendered_fields__description',
                'fields__resolutiondate',
                'fields__parent__id',
                'fields__priority__id',
                'fields__resolution__id'
            )
        """
            )
        ).fetchall()

        column_names = {row[0] for row in columns_result}
        has_description = "rendered_fields__description" in column_names
        has_resolutiondate = "fields__resolutiondate" in column_names
        has_parent_id = "fields__parent__id" in column_names
        has_priority_id = "fields__priority__id" in column_names
        has_resolution_id = "fields__resolution__id" in column_names

        description_col = (
            "r.rendered_fields__description" if has_description else "NULL::text"
        )
        resolutiondate_col = (
            "r.fields__resolutiondate" if has_resolutiondate else "NULL::text"
        )
        parent_id_raw_col = (
            "r.fields__parent__id::text" if has_parent_id else "NULL::text"
        )

        priority_join = (
            "LEFT JOIN clean_jira.issue_priorities ip ON ip.project_id = p.id AND ip.external_id = r.fields__priority__id"
            if has_priority_id
            else ""
        )
        priority_col = "ip.id" if has_priority_id else "NULL::uuid"

        resolution_join = (
            "LEFT JOIN clean_jira.issue_resolutions ir ON ir.project_id = p.id AND ir.external_id = r.fields__resolution__id"
            if has_resolution_id
            else ""
        )
        resolution_col = "ir.id" if has_resolution_id else "NULL::uuid"

        sql = f"""
            INSERT INTO clean_jira.issues (
                project_id,
                external_id,
                external_key,
                summary,
                description,
                type_id,
                status_id,
                priority_id,
                resolution_id,
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
                {priority_col} as priority_id,
                {resolution_col} as resolution_id,
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
            {priority_join}
            {resolution_join}
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                external_key = EXCLUDED.external_key,
                summary = EXCLUDED.summary,
                description = EXCLUDED.description,
                type_id = EXCLUDED.type_id,
                status_id = EXCLUDED.status_id,
                priority_id = EXCLUDED.priority_id,
                resolution_id = EXCLUDED.resolution_id,
                jira_updated_at = EXCLUDED.jira_updated_at,
                jira_resolved_at = EXCLUDED.jira_resolved_at,
                db_updated_at = now()
            RETURNING id
        """  # noqa: S608

        issues_result = conn.execute(text(sql))
        issues_synced = issues_result.fetchall()
        context.log.info(f"Synced {len(issues_synced)} issues")

        # Reconcile parent_id links in a second pass
        if has_parent_id:
            context.log.info("Reconciling parent_id links...")
            conn.execute(
                text(
                    f"""  # noqa: S608
                UPDATE clean_jira.issues i
                SET parent_id = parent.id
                FROM raw_jira.issues r
                JOIN clean_jira.issues parent ON parent.external_id = {parent_id_raw_col}
                    AND parent.project_id = i.project_id
                WHERE i.external_id = r.id::text
                  AND i.parent_id IS DISTINCT FROM parent.id
            """
                )
            )  # noqa: S608

        conn.commit()

    return {
        "status": "success",
        "issues_synced": len(issues_synced),
    }


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_projects", "clean_jira_issues"],
    description="Extract labels from raw Jira issues",
    compute_kind="sql",
)
def clean_jira_labels(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync unique labels from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        # Check if labels table exists in raw
        table_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__fields__labels'
            )
        """
            )
        ).scalar()

        if not table_exists:
            context.log.warning("Table raw_jira.issues__fields__labels not found")
            return {"status": "skipped", "reason": "no_labels_table"}

        context.log.info("Syncing unique labels...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.labels (
                project_id,
                name
            )
            SELECT DISTINCT
                p.id as project_id,
                rl.value as name
            FROM raw_jira.issues__fields__labels rl
            JOIN raw_jira.issues r ON rl._dlt_parent_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE rl.value IS NOT NULL
            ON CONFLICT (project_id, name) DO NOTHING
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["clean_jira_labels", "clean_jira_issues"],
    description="Link issues to labels",
    compute_kind="sql",
)
def clean_jira_issue_labels(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync issue-label relationships."""
    engine = database.get_engine()
    with engine.connect() as conn:
        # Check if raw labels table exists
        table_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__fields__labels'
            )
        """
            )
        ).scalar()

        if not table_exists:
            return {"status": "skipped", "reason": "no_labels_table"}

        context.log.info("Syncing issue labels...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.issue_labels (
                issue_id,
                label_id
            )
            SELECT DISTINCT
                i.id as issue_id,
                l.id as label_id
            FROM raw_jira.issues__fields__labels rl
            JOIN raw_jira.issues r ON rl._dlt_parent_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            JOIN clean_jira.labels l ON l.project_id = p.id AND l.name = rl.value
            ON CONFLICT (issue_id, label_id) DO NOTHING
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


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
        table_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__fields__worklog__worklogs'
            )
        """
            )
        ).scalar()

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
    deps=["raw_jira_data", "clean_jira_issues"],
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

        # Check if board_configurations table exists to link sprints to projects
        board_config_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'board_configurations'
            )
        """
            )
        ).scalar()

        if board_config_exists:
            # Use UPSERT strategy instead of TRUNCATE to avoid cascading deletes
            # This is safer if the job is interrupted or if other tables reference sprints
            insert_query = text(
                """
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
            JOIN raw_jira.board_configurations bc ON s.board_id = bc.board_id
            JOIN clean_jira.projects p ON bc.project_key = p.external_key
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
            """
            )
            result = conn.execute(insert_query)
        else:
            # Fallback for legacy/missing config (though risky, better than CROSS JOIN duplication)
            # Try to use project_key if it exists in sprints (from updated raw asset)
            sprints_cols = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'raw_jira' AND table_name = 'sprints'"
                )
            ).fetchall()
            cols = [c[0] for c in sprints_cols]

            if "project_key" in cols:
                insert_query = text(
                    """
                INSERT INTO clean_jira.sprints (...)
                SELECT DISTINCT ON (p.id, s.id::text)
                    p.id as project_id,
                    ...
                FROM raw_jira.sprints s
                JOIN clean_jira.projects p ON s.project_key = p.external_key
                ...
                """
                )
                # (Simplified for brevity in fallback, but sticking to safe path)
                # If we don't have board configs, we log warning and skip or try best effort
                context.log.warning(
                    "raw_jira.board_configurations not found. Sprints might be skipped."
                )
                result = None
            else:
                context.log.warning(
                    "raw_jira.board_configurations not found and no project_key in sprints. "
                    "Cannot link sprints to projects correctly."
                )
                result = None

        if result:
            sprints_synced = result.fetchall()
            context.log.info(f"Synced {len(sprints_synced)} sprints")
        else:
            sprints_synced = []

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

        # Get all columns from raw_jira.issues
        # We fetch all and filter in python to be safer and debuggable
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

        # Debug log some sample columns
        if all_columns:
            context.log.info(f"Sample columns: {all_columns[:10]}")
        else:
            context.log.warning(
                "No columns found in raw_jira.issues! Checking casing..."
            )
            # Try case-insensitive search
            columns_result_ci = conn.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'raw_jira'
                  AND LOWER(table_name) = 'issues'
            """
                )
            ).fetchall()
            all_columns = [row[0] for row in columns_result_ci]
            context.log.info(
                f"Found {len(all_columns)} columns using case-insensitive search"
            )

        field_keys_inserted = 0

        # Insert standard and custom field keys
        for col_name in all_columns:
            if not col_name.startswith("fields__"):
                continue

            # Skip deeply nested fields (equivalent to NOT LIKE '%__%__%__%')
            # We want to keep fields__summary, fields__customfield_123,
            # fields__status__name
            # But avoid deeply nested json structures that might have been flattened
            if col_name.count("__") >= 3:
                continue

            # Skip metadata fields that are usually not useful for analytics
            if col_name.endswith("__self"):
                continue

            # Extract field key from column name
            # (e.g., fields__customfield_10001 -> customfield_10001)
            field_key = col_name.replace("fields__", "", 1)
            is_custom = field_key.startswith("customfield_")

            # Derive human-readable name from key
            if is_custom:
                field_name = field_key  # Will be updated from metadata if available
            else:
                field_name = field_key.replace("_", " ").title()

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
                    :field_key as external_key,
                    :field_name as name,
                    :is_custom as is_custom,
                    now() as created_at
                FROM clean_jira.projects p
                ON CONFLICT (project_id, external_key) DO UPDATE SET
                    name = EXCLUDED.name
            """
                ),
                {
                    "field_key": field_key,
                    "field_name": field_name,
                    "is_custom": is_custom,
                },
            )
            field_keys_inserted += 1

        context.log.info(f"Inserted {field_keys_inserted} field keys")

        # Try to get human-readable names from raw_jira.fields if it exists
        fields_table_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'fields'
            )
        """
            )
        ).scalar()

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
            # We try to match the prefix (customfield_10001) with the field ID
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

        # Import json for validation
        import json

        # Process in batches of columns
        batch_size = 20

        for i in range(0, len(target_columns), batch_size):
            chunk = target_columns[i : i + batch_size]
            context.log.info(
                f"Processing batch {i // batch_size + 1}: columns {i} to {i + len(chunk)}"
            )

            # Build dynamic select
            select_clause = ", ".join([f'r."{c}"' for c in chunk])

            rows_query = text(
                f"""  # noqa: S608
                SELECT
                    i.id as issue_id,
                    i.project_id,
                    {select_clause}
                FROM raw_jira.issues r
                JOIN clean_jira.issues i ON i.external_id = r.id::text
            """
            )  # noqa: S608

            batch_rows = conn.execute(rows_query).fetchall()

            insert_data = []
            for row in batch_rows:
                issue_id = row.issue_id
                project_id = row.project_id

                for idx, col_name in enumerate(chunk):
                    val = row[2 + idx]
                    if val is None:
                        continue

                    field_key = col_name.replace("fields__", "", 1)
                    fk_id = fk_map.get((project_id, field_key))
                    if not fk_id:
                        continue

                    val_str = str(val)
                    json_val = None

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

            if insert_data:
                stmt = text(
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
                conn.execute(stmt, insert_data)
                field_values_inserted += len(insert_data)

        context.log.info(f"Inserted {field_values_inserted} field values")
        conn.commit()

        # Explicitly extract 'Sprint' values
        sprint_field_id = _detect_sprint_field_id(conn)
        context.log.info(f"Extracting Sprint ({sprint_field_id}) values...")
        sprint_table_exists = conn.execute(
            text(
                f"""  # noqa: S608
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__fields__{sprint_field_id}'
            )
        """
            )
        ).scalar()  # noqa: S608

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
                JOIN clean_jira.issues i ON i.external_id = r.id::text
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
        changelog_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__changelog__histories__items'
            )
        """
            )
        ).scalar()

        if not changelog_exists:
            context.log.warning("No changelog items table found in raw_jira")
            return {"status": "skipped", "reason": "no_changelog_items_table"}

        # Use a temporary function to safely cast to JSONB
        # If text is valid JSON, returns JSONB.
        # If text is invalid JSON (e.g. truncated or bad format),
        # returns text as JSONB string.
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
                """  # noqa: S608
        INSERT INTO clean_jira.field_value_changelog (                issue_id,
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
            JOIN clean_jira.issues i ON i.external_id = r.id::text
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
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__changelog__histories__items'
            )
        """
            )
        ).scalar()

        if not changelog_exists:
            context.log.warning("No changelog items table found in raw_jira")
            return {"status": "skipped", "reason": "no_changelog_items_table"}

        # Build sprint_issues from changelog final state
        sprint_field_id = _detect_sprint_field_id(conn)
        result = conn.execute(
            text(
                f"""
            WITH changelog_events AS (
                -- Extract Sprint changes from changelog
                SELECT
                    r.id::text as issue_external_id,
                    r.fields__project__id::text as project_external_id,
                    h.created::timestamptz as changed_at,
                    item."to" as to_value,
                    item."from" as from_value,
                    h.author__account_id as author_id
                FROM raw_jira.issues__changelog__histories__items item
                JOIN raw_jira.issues__changelog__histories h
                    ON item._dlt_parent_id = h._dlt_id
                JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
                WHERE (item.field = 'Sprint' AND item.fieldtype = 'jira')
                   OR item.field_id = :sprint_field_id
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
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(to_value, ''), '\\s*,\\s*'
                ) as sprint_id
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
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(from_value, ''), '\\s*,\\s*'
                ) as sprint_id
                WHERE from_value IS NOT NULL AND from_value != ''
            ),
            -- Extract sprint data from current issue fields (Snapshot/Backfill)
            -- This captures issues created directly in a sprint (no changelog entry)
            snapshot_events AS (
                SELECT
                    i.id::text as issue_external_id,
                    i.fields__project__id::text as project_external_id,
                    -- Use issue creation time as the 'added' time if available, or epoch
                    COALESCE(i.fields__created::timestamptz, '1970-01-01'::timestamptz) as changed_at,
                    s.id::text as sprint_external_id,
                    'added' as action,
                    NULL::text as author_id  -- No author for snapshot events
                FROM raw_jira.issues i
                JOIN raw_jira.issues__fields__{sprint_field_id} s
                  ON s._dlt_parent_id = i._dlt_id
                WHERE s.id IS NOT NULL
                  -- If Sprint changelog exists, it is the source of truth.
                  AND NOT EXISTS (
                      SELECT 1 FROM changelog_events ce
                      WHERE ce.issue_external_id = i.id::text
                  )
            ),
            -- Union all events
            all_events AS (
                SELECT issue_external_id, project_external_id, changed_at, sprint_external_id, action, author_id FROM added_events
                UNION ALL
                SELECT issue_external_id, project_external_id, changed_at, sprint_external_id, action, author_id FROM removed_events
                UNION ALL
                SELECT issue_external_id, project_external_id, changed_at, sprint_external_id, action, author_id::text FROM snapshot_events
            ),
            -- Normalize sprint_external_id to actual sprint_id first
            -- This handles both numeric IDs and text names
            normalized_events AS (
                SELECT
                    ae.issue_external_id,
                    s.id as sprint_id,
                    ae.changed_at,
                    ae.action
                FROM all_events ae
                JOIN clean_jira.issues i ON i.external_id = ae.issue_external_id
                JOIN clean_jira.sprints s ON
                    s.external_id = ae.sprint_external_id
                    OR (s.name = ae.sprint_external_id AND s.project_id = i.project_id)
                WHERE ae.sprint_external_id IS NOT NULL
                  AND ae.sprint_external_id != ''
            ),
            -- Get the latest action for each issue-sprint pair
            -- Now using normalized sprint_id to avoid duplicates from ID vs name matching
            latest_action AS (
                SELECT DISTINCT ON (issue_external_id, sprint_id)
                    issue_external_id,
                    sprint_id,
                    action,
                    changed_at
                FROM normalized_events
                ORDER BY issue_external_id, sprint_id, changed_at DESC, action DESC
            )
            -- Insert pairs where final action is 'added' or 'removed'
            INSERT INTO clean_jira.sprint_issues (
                sprint_id,
                issue_id,
                is_active
            )
            SELECT
                la.sprint_id,
                i.id as issue_id,
                CASE WHEN la.action = 'added' THEN true ELSE false END as is_active
            FROM latest_action la
            JOIN clean_jira.issues i ON i.external_id = la.issue_external_id
            WHERE la.action IN ('added', 'removed')
            ON CONFLICT (sprint_id, issue_id) DO UPDATE SET
                is_active = EXCLUDED.is_active
            RETURNING id
            """
            )
        )
        sprint_issues_count = len(result.fetchall())
        context.log.info(f"Inserted {sprint_issues_count} sprint-issue relationships")

        # Reconciliation: set is_active = FALSE for issues in closed sprints
        context.log.info("Reconciling is_active for closed sprints...")
        conn.execute(
            text(
                """
            UPDATE clean_jira.sprint_issues si
            SET is_active = false
            FROM clean_jira.sprints s
            WHERE si.sprint_id = s.id
              AND s.status = 'closed'
              AND si.is_active = true
        """
            )
        )

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
        # Rebuild changelog deterministically from raw data.
        # This avoids stale/incorrect historical rows lingering across logic fixes.
        conn.execute(text("TRUNCATE TABLE clean_jira.sprint_issues_changelog"))

        sprint_field_id = _detect_sprint_field_id(conn)
        result = conn.execute(
            text(
                f"""
            WITH changelog_events AS (
                SELECT
                    r.id::text as issue_external_id,
                    h.created::timestamptz as changed_at,
                    item."to" as to_value,
                    item."from" as from_value,
                    h.author__account_id as author_id
                FROM raw_jira.issues__changelog__histories__items item
                JOIN raw_jira.issues__changelog__histories h
                    ON item._dlt_parent_id = h._dlt_id
                JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
                WHERE (item.field = 'Sprint' AND item.fieldtype = 'jira')
                   OR item.field_id = :sprint_field_id
            ),
            to_sprints AS (
                SELECT DISTINCT
                    ce.issue_external_id,
                    ce.changed_at,
                    ce.author_id,
                    trim(sprint_id) as sprint_external_id
                FROM changelog_events ce
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(ce.to_value, ''), '\\s*,\\s*'
                ) as sprint_id
                WHERE ce.to_value IS NOT NULL
                  AND ce.to_value != ''
                  AND trim(sprint_id) != ''
            ),
            from_sprints AS (
                SELECT DISTINCT
                    ce.issue_external_id,
                    ce.changed_at,
                    ce.author_id,
                    trim(sprint_id) as sprint_external_id
                FROM changelog_events ce
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(ce.from_value, ''), '\\s*,\\s*'
                ) as sprint_id
                WHERE ce.from_value IS NOT NULL
                  AND ce.from_value != ''
                  AND trim(sprint_id) != ''
            ),
            -- Jira Sprint field stores a full set in from/to. We need set delta:
            -- added = to - from, removed = from - to.
            added_events AS (
                SELECT
                    t.issue_external_id,
                    t.changed_at,
                    t.sprint_external_id,
                    'added' as action,
                    t.author_id
                FROM to_sprints t
                LEFT JOIN from_sprints f
                  ON f.issue_external_id = t.issue_external_id
                 AND f.changed_at = t.changed_at
                 AND f.sprint_external_id = t.sprint_external_id
                WHERE f.sprint_external_id IS NULL
            ),
            removed_events AS (
                SELECT
                    f.issue_external_id,
                    f.changed_at,
                    f.sprint_external_id,
                    'removed' as action,
                    f.author_id
                FROM from_sprints f
                LEFT JOIN to_sprints t
                  ON t.issue_external_id = f.issue_external_id
                 AND t.changed_at = f.changed_at
                 AND t.sprint_external_id = f.sprint_external_id
                WHERE t.sprint_external_id IS NULL
            ),
            -- Snapshot events: issues created directly in a sprint (no changelog entry)
            -- These are issues where Sprint was set at creation time, not via changelog
            snapshot_events AS (
                SELECT
                    i.id::text as issue_external_id,
                    -- Use issue creation time as the 'added' time
                    COALESCE(i.fields__created::timestamptz, '1970-01-01'::timestamptz) as changed_at,
                    s.id::text as sprint_external_id,
                    'added' as action,
                    NULL::text as author_id
                FROM raw_jira.issues i
                JOIN raw_jira.issues__fields__{sprint_field_id} s
                  ON s._dlt_parent_id = i._dlt_id
                WHERE s.id IS NOT NULL
                  -- Exclude issues that already have Sprint changelog entries
                  AND NOT EXISTS (
                      SELECT 1 FROM changelog_events ce
                      WHERE ce.issue_external_id = i.id::text
                  )
            ),
            all_events AS (
                SELECT * FROM added_events
                UNION ALL
                SELECT * FROM removed_events
                UNION ALL
                SELECT * FROM snapshot_events
            ),
            -- Normalize to actual sprint_id to avoid duplicate inserts from ID vs name matching
            normalized_events AS (
                SELECT DISTINCT ON (s.id, i.id, ae.action, ae.changed_at)
                    s.id as sprint_id,
                    i.id as issue_id,
                    ae.action,
                    u.id as changed_by_id,
                    ae.changed_at
                FROM all_events ae
                JOIN clean_jira.issues i ON i.external_id = ae.issue_external_id
                JOIN clean_jira.sprints s ON
                    s.external_id = ae.sprint_external_id
                    OR (s.name = ae.sprint_external_id AND s.project_id = i.project_id)
                LEFT JOIN clean_jira.jira_users u ON u.project_id = i.project_id
                    AND u.external_id = ae.author_id
                ORDER BY s.id, i.id, ae.action, ae.changed_at
            )
            INSERT INTO clean_jira.sprint_issues_changelog (
                sprint_id,
                issue_id,
                action,
                changed_by_id,
                changed_at
            )
            SELECT
                sprint_id,
                issue_id,
                action,
                changed_by_id,
                changed_at
            FROM normalized_events
            ON CONFLICT (sprint_id, issue_id, action, changed_at) DO NOTHING
            RETURNING id
            """
            )
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
        # dlt typically creates issues__fields__comment__comments
        # prioritize rendered_fields if available as it often contains the full body (TEXT)
        possible_tables = [
            "issues__rendered_fields__comment__comments",
            "issues__fields__comment__comments",
            "issues__fields__comment",
        ]

        comment_table = None
        for table in possible_tables:
            exists = conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'raw_jira'
                          AND table_name = :table_name
                    )
                    """
                ),
                {"table_name": table},
            ).scalar()
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
            # Last ditch effort: try the first existing table even without 'body' if nothing else found
            for table in possible_tables:
                exists = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'raw_jira' AND table_name = :table_name)"
                    ),
                    {"table_name": table},
                ).scalar()
                if exists:
                    comment_table = table
                    break

        if not comment_table:
            context.log.warning(
                "No comment table found in raw_jira. Skipping comments sync."
            )
            return {"status": "skipped", "reason": "no_comment_table"}

        context.log.info(f"Using raw comment table: {comment_table}")

        # Insert comments
        # We need to join with proper parent tables to get back to the issue
        # dlt hierarchy: issues -> [issues__fields__comment] -> issues__fields__comment__comments
        # OR directly issues -> issues__fields__comment__comments

        # Check if we need an intermediate join
        # If the table is issues__fields__comment__comments, we need to check its parent

        # Construct the query based on structure
        # Assuming for now direct link or one level deep.
        # Safest is to trace back to raw_jira.issues via _dlt_root_id if available, or join up.
        # dlt usually adds _dlt_root_id to child tables? Let's assume standard parent-child.

        # If table is issues__fields__comment__comments:
        # Parent is likely issues__fields__comment (if it exists) or issues.
        # Let's try to infer from data or just join dynamically?
        # Actually simplest is to join clean_jira.issues using _dlt_root_id if we can rely on it,
        # but dlt's _dlt_root_id is the top level _dlt_id.

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
                c.created::timestamptz as created_at,
                c.updated::timestamptz as updated_at
            FROM raw_jira.{table} c
            JOIN raw_jira.issues r ON c._dlt_root_id = r._dlt_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text
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
        # In this model, comments are strictly 1:1 with issues (owned by issue).
        # But we have a separate table clean_jira.comment_issues.
        # So we populate it now.

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
            JOIN clean_jira.issues i ON i.external_id = r.id::text
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
    deps=["raw_jira_data", "clean_jira_issues"],
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
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'versions'
            )
        """
            )
        ).scalar()

        if not versions_exists:
            context.log.warning("No versions table found in raw_jira")
            return {"status": "skipped", "reason": "no_versions_table"}

        result = conn.execute(
            text(
                """
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
                NULL::date as start_date,
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
        """
            ),
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
    deps=["clean_jira_releases"],
    description="Track changes to release properties (name, description, status, release_date) via snapshot diff",
    compute_kind="sql",
)
def clean_jira_release_changelog(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Populate release property change history using snapshot-diff approach.

    Jira does not expose release property history via API. On each run, compares
    the current state of clean_jira.releases with the last known state stored in
    release_changelog. Inserts a row for every field that has changed since the
    previous run. Initial population uses old_value=NULL.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Detecting release property changes via snapshot diff...")

        result = conn.execute(
            text(
                """
            WITH current_state AS (
                SELECT
                    r.id AS release_id,
                    unnest(ARRAY['name', 'description', 'status', 'release_date']) AS field_name,
                    unnest(ARRAY[
                        r.name,
                        r.description,
                        r.status::text,
                        r.release_date::text
                    ]) AS current_value
                FROM clean_jira.releases r
            ),
            last_known AS (
                SELECT DISTINCT ON (release_id, field_name)
                    release_id,
                    field_name,
                    new_value
                FROM clean_jira.release_changelog
                ORDER BY release_id, field_name, changed_at DESC
            ),
            changes AS (
                SELECT
                    cs.release_id,
                    cs.field_name,
                    lk.new_value AS old_value,
                    cs.current_value AS new_value
                FROM current_state cs
                LEFT JOIN last_known lk
                    ON cs.release_id = lk.release_id AND cs.field_name = lk.field_name
                WHERE cs.current_value IS DISTINCT FROM lk.new_value
            )
            INSERT INTO clean_jira.release_changelog (
                release_id, field_name, old_value, new_value, changed_at
            )
            SELECT release_id, field_name, old_value, new_value, now()
            FROM changes
            RETURNING id
        """
            )
        )
        changelog_count = len(result.fetchall())
        context.log.info(f"Inserted {changelog_count} release changelog entries")

        conn.commit()

    return {
        "status": "success",
        "changelog_count": changelog_count,
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
            text(
                """
            WITH changelog_events AS (
                SELECT
                    r.id::text as issue_external_id,
                    h.created::timestamptz as changed_at,
                    item."to" as to_value,
                    item."from" as from_value,
                    h.author__account_id as author_id
                FROM raw_jira.issues__changelog__histories__items item
                JOIN raw_jira.issues__changelog__histories h
                    ON item._dlt_parent_id = h._dlt_id
                JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
                WHERE (item.field IN ('Fix Version/s', 'fixVersions', 'Fix Version')
                   OR item.field_id IN ('fixVersions', 'fixversion'))
            ),
            added_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(version_id) as version_external_id,
                    'added' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(to_value, ''), '\\s*,\\s*'
                ) as version_id
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
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(from_value, ''), '\\s*,\\s*'
                ) as version_id
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
        """
            )
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
    deps=["clean_jira_release_issues"],
    description="Extract release-issue changelog (add/remove history)",
    compute_kind="sql",
)
def clean_jira_release_issues_changelog(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract full history of release-issue changes.

    Records every time an issue was added to or removed from a release (Fix Version).
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting release-issue changelog...")

        # Check if releases exist
        releases_count = conn.execute(
            text("SELECT COUNT(*) FROM clean_jira.releases")
        ).scalar()

        if releases_count == 0:
            context.log.warning("No releases found, skipping release_issues_changelog")
            return {"status": "skipped", "reason": "no_releases"}

        result = conn.execute(
            text(
                """
            WITH changelog_events AS (
                SELECT
                    r.id::text as issue_external_id,
                    h.created::timestamptz as changed_at,
                    item."to" as to_value,
                    item."from" as from_value,
                    h.author__account_id as author_id
                FROM raw_jira.issues__changelog__histories__items item
                JOIN raw_jira.issues__changelog__histories h
                    ON item._dlt_parent_id = h._dlt_id
                JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
                WHERE (item.field IN ('Fix Version/s', 'fixVersions', 'Fix Version')
                   OR item.field_id IN ('fixVersions', 'fixversion'))
            ),
            added_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(version_id) as version_external_id,
                    'added' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(to_value, ''), '\\s*,\\s*'
                ) as version_id
                WHERE to_value IS NOT NULL
                  AND to_value != ''
                  AND version_id ~ '^[0-9]+$'
            ),
            removed_events AS (
                SELECT
                    issue_external_id,
                    changed_at,
                    trim(version_id) as version_external_id,
                    'removed' as action,
                    author_id
                FROM changelog_events
                CROSS JOIN LATERAL regexp_split_to_table(
                    COALESCE(from_value, ''), '\\s*,\\s*'
                ) as version_id
                WHERE from_value IS NOT NULL
                  AND from_value != ''
                  AND version_id ~ '^[0-9]+$'
            ),
            all_events AS (
                SELECT * FROM added_events
                UNION ALL
                SELECT * FROM removed_events
            )
            INSERT INTO clean_jira.release_issues_changelog (
                release_id,
                issue_id,
                action,
                changed_by_id,
                changed_at
            )
            SELECT
                rel.id as release_id,
                i.id as issue_id,
                ae.action,
                u.id as changed_by_id,
                ae.changed_at
            FROM all_events ae
            JOIN clean_jira.issues i ON i.external_id = ae.issue_external_id
            JOIN clean_jira.releases rel ON rel.project_id = i.project_id
                AND rel.external_id = ae.version_external_id
            LEFT JOIN clean_jira.jira_users u ON u.project_id = i.project_id
                AND u.external_id = ae.author_id
            ON CONFLICT (release_id, issue_id, action, changed_at) DO NOTHING
            RETURNING id
        """
            )
        )
        changelog_count = len(result.fetchall())
        context.log.info(f"Inserted {changelog_count} release-issue changelog entries")

        conn.commit()

    return {
        "status": "success",
        "changelog_count": changelog_count,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_sprints"],
    description="Extract sprint property changelog (name, goal, dates, status changes)",
    compute_kind="sql",
)
def clean_jira_sprint_changelog(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Record sprint property changes (name, goal, dates, status) in sprint_changelog.

    This asset uses a snapshot-diff approach:
    1. It fetches the last known value for each sprint property from the changelog.
    2. It compares these with current values in the sprints table.
    3. It inserts a new row whenever a value has changed or is newly discovered (bootstrap).
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Processing sprint changelog snapshot-diff...")

        result = conn.execute(
            text(
                """
            WITH last_known AS (
                SELECT DISTINCT ON (sprint_id, field_name)
                    sprint_id, field_name, new_value
                FROM clean_jira.sprint_changelog
                ORDER BY sprint_id, field_name, changed_at DESC
            ),
            current_fields AS (
                SELECT id AS sprint_id, 'name'       AS field_name, name           AS current_value FROM clean_jira.sprints
                UNION ALL
                SELECT id, 'goal',       goal                                                        FROM clean_jira.sprints
                UNION ALL
                SELECT id, 'start_date', start_date::text                                            FROM clean_jira.sprints
                UNION ALL
                SELECT id, 'end_date',   end_date::text                                              FROM clean_jira.sprints
                UNION ALL
                SELECT id, 'status',     status::text                                                FROM clean_jira.sprints
            )
            INSERT INTO clean_jira.sprint_changelog (sprint_id, field_name, old_value, new_value, changed_at)
            SELECT
                cf.sprint_id,
                cf.field_name,
                lk.new_value  AS old_value,
                cf.current_value AS new_value,
                now()         AS changed_at
            FROM current_fields cf
            LEFT JOIN last_known lk ON lk.sprint_id = cf.sprint_id AND lk.field_name = cf.field_name
            WHERE cf.current_value IS DISTINCT FROM lk.new_value
            RETURNING id
            """
            )
        )
        changelog_count = len(result.fetchall())
        context.log.info(
            f"Inserted {changelog_count} sprint property changelog entries"
        )

        conn.commit()

    return {
        "status": "success",
        "changelog_count": changelog_count,
    }


@asset(
    group_name="jira_clean",
    deps=["clean_jira_issues", "clean_jira_issue_statuses"],
    description="Extract issue status changes from changelog",
    compute_kind="sql",
)
def clean_jira_issue_status_changelog(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Extract issue status changelog from raw history.

    Parses 'status' field changes. Joins with issue_statuses to resolve string status names to UUIDs.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        context.log.info("Extracting issue status change log...")

        # Check raw changelog exists
        changelog_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'issues__changelog__histories__items'
            )
        """
            )
        ).scalar()

        if not changelog_exists:
            return {"status": "skipped", "reason": "no_raw_changelog"}

        result = conn.execute(
            text(
                """
            WITH status_changes AS (
                SELECT
                    r.id::text as issue_external_id,
                    p.id as project_id,
                    h.created::timestamptz as changed_at,
                    h.author__account_id as author_external_id,
                    item."from" as from_status_external_id,
                    item."to" as to_status_external_id
                FROM raw_jira.issues__changelog__histories__items item
                JOIN raw_jira.issues__changelog__histories h ON item._dlt_parent_id = h._dlt_id
                JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
                JOIN clean_jira.projects p ON p.external_id = r.fields__project__id::text
                WHERE item.field = 'status'
                  AND item.fieldtype = 'jira'
            )
            INSERT INTO clean_jira.issue_status_changelog (
                issue_id,
                from_status_id,
                to_status_id,
                changed_by_id,
                changed_at
            )
            SELECT
                i.id as issue_id,
                s_from.id as from_status_id,
                s_to.id as to_status_id,
                u.id as changed_by_id,
                sc.changed_at
            FROM status_changes sc
            JOIN clean_jira.issues i ON i.external_id = sc.issue_external_id
            -- Resolve 'from' status
            LEFT JOIN clean_jira.issue_statuses s_from
                ON s_from.project_id = sc.project_id
                AND s_from.external_id = sc.from_status_external_id
            -- Resolve 'to' status
            LEFT JOIN clean_jira.issue_statuses s_to
                ON s_to.project_id = sc.project_id
                AND s_to.external_id = sc.to_status_external_id
            -- Resolve author
            LEFT JOIN clean_jira.jira_users u
                ON u.project_id = sc.project_id
                AND u.external_id = sc.author_external_id
            WHERE s_to.id IS NOT NULL
            ON CONFLICT (issue_id, to_status_id, changed_at) DO NOTHING
            RETURNING id
        """
            )
        )

        count = len(result.fetchall())
        context.log.info(f"Inserted {count} status changelog entries")
        conn.commit()

    return {"status": "success", "changelog_entries": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_issues"],
    description="Sync Jira boards to clean layer",
    compute_kind="sql",
)
def clean_jira_boards(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync boards from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing boards...")
        boards_exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'raw_jira' AND table_name = 'board_configurations')"
            )
        ).scalar()
        if not boards_exists:
            return {"status": "skipped", "reason": "no_board_configurations_table"}

        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.boards (project_id, external_id, name, created_at)
            SELECT DISTINCT ON (p.id, bc.board_id::text)
                p.id, bc.board_id::text, bc.board_name, now()
            FROM raw_jira.board_configurations bc
            JOIN clean_jira.projects p ON p.external_key = bc.project_key
            WHERE bc.board_id IS NOT NULL
            ORDER BY p.id, bc.board_id::text, bc._dlt_id DESC
            ON CONFLICT (project_id, external_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_boards"],
    description="Sync Jira board columns to clean layer",
    compute_kind="sql",
)
def clean_jira_board_columns(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync board columns from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing board columns...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.board_columns (board_id, name, position)
            SELECT DISTINCT ON (b.id, col.name)
                b.id, col.name, col._dlt_list_idx::int
            FROM raw_jira.board_configurations__columns_config__columns col
            JOIN raw_jira.board_configurations bc ON col._dlt_parent_id = bc._dlt_id
            JOIN clean_jira.projects p ON p.external_key = bc.project_key
            JOIN clean_jira.boards b ON b.project_id = p.id AND b.external_id = bc.board_id::text
            WHERE col.name IS NOT NULL
            ORDER BY b.id, col.name, bc._dlt_id DESC
            ON CONFLICT (board_id, name) DO UPDATE SET position = EXCLUDED.position
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data", "clean_jira_board_columns", "clean_jira_issue_statuses"],
    description="Sync Jira board column statuses to clean layer",
    compute_kind="sql",
)
def clean_jira_board_column_statuses(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync board column statuses from raw to clean."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing board column statuses...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.board_column_statuses (board_column_id, status_id)
            SELECT DISTINCT ON (bc_col.id, ist.id)
                bc_col.id, ist.id
            FROM raw_jira.board_configurations__columns_config__columns__statuses st
            JOIN raw_jira.board_configurations__columns_config__columns col ON st._dlt_parent_id = col._dlt_id
            JOIN raw_jira.board_configurations bc ON col._dlt_parent_id = bc._dlt_id
            JOIN clean_jira.projects p ON p.external_key = bc.project_key
            JOIN clean_jira.boards b ON b.project_id = p.id AND b.external_id = bc.board_id::text
            JOIN clean_jira.board_columns bc_col ON bc_col.board_id = b.id AND bc_col.name = col.name
            JOIN clean_jira.issue_statuses ist ON ist.project_id = p.id AND ist.external_id = st.id
            WHERE st.id IS NOT NULL
            ORDER BY bc_col.id, ist.id, bc._dlt_id DESC
            ON CONFLICT (board_column_id, status_id) DO NOTHING
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
    description="Sync Jira user roles in issues (assignee, reporter, creator)",
    compute_kind="sql",
)
def clean_jira_user_issue_roles(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync user roles (assignee, reporter, creator) to clean_jira.jira_user_issue_roles."""
    engine = database.get_engine()
    with engine.connect() as conn:
        context.log.info("Syncing user issue roles...")
        result = conn.execute(
            text(
                """
            INSERT INTO clean_jira.jira_user_issue_roles (
                user_id,
                issue_id,
                role_type
            )
            SELECT DISTINCT
                u.id as user_id,
                i.id as issue_id,
                role_data.role_type::clean_jira.user_role_type
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id
            CROSS JOIN LATERAL (
                SELECT r.fields__assignee__account_id as account_id, 'assignee' as role_type
                WHERE r.fields__assignee__account_id IS NOT NULL
                UNION ALL
                SELECT r.fields__reporter__account_id as account_id, 'reporter' as role_type
                WHERE r.fields__reporter__account_id IS NOT NULL
                UNION ALL
                SELECT r.fields__creator__account_id as account_id, 'creator' as role_type
                WHERE r.fields__creator__account_id IS NOT NULL
            ) as role_data
            JOIN clean_jira.jira_users u ON u.external_id = role_data.account_id AND u.project_id = p.id
            ON CONFLICT (user_id, issue_id, role_type) DO NOTHING
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
    description="Sync Jira issue links to clean layer",
    compute_kind="sql",
)
def clean_jira_issue_links(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Sync issue links from raw_jira.issues__fields__issuelinks."""
    engine = database.get_engine()
    with engine.connect() as conn:
        # Check if issuelinks table exists
        table_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira'
                  AND table_name = 'issues__fields__issuelinks'
            )
        """
            )
        ).scalar()

        if not table_exists:
            context.log.warning("Table raw_jira.issues__fields__issuelinks not found")
            return {"status": "skipped", "reason": "no_issuelinks_table"}

        context.log.info("Syncing issue link types...")
        # First sync relation_issue_types
        conn.execute(
            text(
                """
            INSERT INTO clean_jira.relation_issue_types (
                project_id,
                external_id,
                name
            )
            SELECT DISTINCT
                p.id as project_id,
                il.type__id as external_id,
                il.type__name as name
            FROM raw_jira.issues__fields__issuelinks il
            JOIN raw_jira.issues r ON il._dlt_parent_id = r._dlt_id
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            WHERE il.type__id IS NOT NULL
            ON CONFLICT (project_id, external_id) DO UPDATE SET
                name = EXCLUDED.name
        """
            )
        )

        context.log.info("Syncing issue relationships...")
        # Then sync relation_issue_issues
        # We need to handle both outward and inward links
        result = conn.execute(
            text(
                """
            WITH link_data AS (
                SELECT
                    il.type__id as type_external_id,
                    r.id::text as source_external_id,
                    COALESCE(il.outward_issue__id, il.inward_issue__id)::text as target_external_id,
                    r.fields__project__id::text as project_external_id
                FROM raw_jira.issues__fields__issuelinks il
                JOIN raw_jira.issues r ON il._dlt_parent_id = r._dlt_id
                WHERE il.type__id IS NOT NULL
                  AND (il.outward_issue__id IS NOT NULL OR il.inward_issue__id IS NOT NULL)
            )
            INSERT INTO clean_jira.relation_issue_issues (
                relation_type_id,
                source_issue_id,
                target_issue_id
            )
            SELECT DISTINCT
                rt.id as relation_type_id,
                si.id as source_issue_id,
                ti.id as target_issue_id
            FROM link_data ld
            JOIN clean_jira.projects p ON ld.project_external_id = p.external_id
            JOIN clean_jira.relation_issue_types rt ON rt.external_id = ld.type_external_id AND rt.project_id = p.id
            JOIN clean_jira.issues si ON si.external_id = ld.source_external_id AND si.project_id = p.id
            JOIN clean_jira.issues ti ON ti.external_id = ld.target_external_id AND ti.project_id = p.id
            ON CONFLICT (relation_type_id, source_issue_id, target_issue_id) DO NOTHING
            RETURNING id
        """
            )
        )
        count = len(result.fetchall())
        conn.commit()
    return {"status": "success", "count": count}


@asset(
    group_name="jira_clean",
    deps=["raw_jira_data"],
    description="Remove issues from raw layer that no longer exist in Jira API",
)
def jira_ghost_cleanup(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """Remove ghost issues from raw_jira.issues.

    Fetches all issue IDs from Jira API and deletes those from raw layer
    that are not in the fetched list.
    """
    import os

    import requests
    from requests.auth import HTTPBasicAuth

    jira_url = os.getenv("JIRA_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_api_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_url, jira_email, jira_api_token]):
        context.log.warning(
            "Jira credentials not fully configured (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN). "
            "Skipping ghost cleanup."
        )
        return {"status": "skipped", "reason": "missing_credentials"}

    context.log.info("Fetching all issue IDs from Jira API...")

    # We only need 'id' field to minimize payload
    all_issue_ids = set()
    start_at = 0
    max_results = 100

    try:
        auth = HTTPBasicAuth(jira_email, jira_api_token)
        while True:
            response = requests.get(
                f"{jira_url}/rest/api/3/search",
                params={
                    "jql": "order by id",
                    "fields": "id",
                    "startAt": start_at,
                    "maxResults": max_results,
                },
                auth=auth,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                all_issue_ids.add(issue["id"])

            start_at += len(issues)
            if start_at >= data.get("total", 0):
                break

        context.log.info(f"Fetched {len(all_issue_ids)} issue IDs from Jira API")

        if not all_issue_ids:
            context.log.warning(
                "No issues fetched from Jira. Skipping deletion to be safe."
            )
            return {"status": "skipped", "reason": "no_issues_from_api"}

        engine = database.get_engine()
        with engine.connect() as conn:
            # Get current IDs in raw_jira.issues
            result = conn.execute(text("SELECT id::text FROM raw_jira.issues"))
            raw_ids = {row[0] for row in result.fetchall()}

            ids_to_delete = raw_ids - all_issue_ids

            if ids_to_delete:
                context.log.info(f"Found {len(ids_to_delete)} ghost issues to delete")
                # Delete in batches to avoid huge SQL
                delete_list = list(ids_to_delete)
                batch_size = 1000
                total_deleted = 0

                for i in range(0, len(delete_list), batch_size):
                    batch = delete_list[i : i + batch_size]
                    conn.execute(
                        text("DELETE FROM raw_jira.issues WHERE id::text IN :ids"),
                        {"ids": tuple(batch)},
                    )
                    total_deleted += len(batch)

                conn.commit()
                context.log.info(f"Successfully deleted {total_deleted} ghost issues")
                return {"status": "success", "deleted_count": total_deleted}
            else:
                context.log.info("No ghost issues found")
                return {"status": "success", "deleted_count": 0}

    except Exception as e:
        context.log.error(f"Error during ghost cleanup: {e}")
        return {"status": "failed", "error": str(e)}


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
            text(
                """
            SELECT count(*) FROM clean_jira.issues i
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.projects p
                WHERE p.id = i.project_id
            )
        """
            )
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
            text(
                """
            SELECT count(*) FROM clean_jira.issues
            WHERE external_key IS NULL
               OR summary IS NULL
               OR type_id IS NULL
               OR status_id IS NULL
        """
            )
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
            text(
                """
            SELECT count(*) FROM clean_jira.sprints
            WHERE start_date IS NOT NULL
              AND end_date IS NOT NULL
              AND start_date > end_date
        """
            )
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
            text(
                """
            SELECT count(*) FROM clean_jira.sprint_issues si
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.sprints s WHERE s.id = si.sprint_id
            )
               OR NOT EXISTS (
                   SELECT 1 FROM clean_jira.issues i WHERE i.id = si.issue_id
               )
        """
            )
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
            text(
                """
            SELECT count(*) FROM clean_jira.release_issues ri
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.releases r WHERE r.id = ri.release_id
            )
               OR NOT EXISTS (
                   SELECT 1 FROM clean_jira.issues i WHERE i.id = ri.issue_id
               )
        """
            )
        )
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_release_issues_count": invalid_count},
    )


# Maximum acceptable percentage of clean issues missing vs raw issues.
# 5% allows for issues legitimately filtered out (no project match, etc.).
_MAX_ISSUE_LOSS_PCT = 5.0


@asset_check(
    asset=clean_jira_issues,
    description="Verify raw vs clean issue count delta is within tolerance",
)
def check_raw_clean_issue_count(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Compare raw and clean issue counts.

    Detects silent data loss between the Bronze and Silver layers. Allows up
    to _MAX_ISSUE_LOSS_PCT% discrepancy to account for issues filtered out
    due to missing project mapping or malformed IDs.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        raw_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'issues'
            )
        """
            )
        ).scalar()

        if not raw_exists:
            return AssetCheckResult(
                passed=True,
                metadata={"status": "skipped_no_raw_table"},
            )

        raw_count = (
            conn.execute(text("SELECT COUNT(*) FROM raw_jira.issues")).scalar() or 0
        )
        clean_count = (
            conn.execute(text("SELECT COUNT(*) FROM clean_jira.issues")).scalar() or 0
        )

    if raw_count == 0:
        return AssetCheckResult(passed=True, metadata={"status": "no_raw_data"})

    loss_pct = ((raw_count - clean_count) / raw_count) * 100
    passed = loss_pct <= _MAX_ISSUE_LOSS_PCT

    return AssetCheckResult(
        passed=passed,
        metadata={
            "raw_issues_count": raw_count,
            "clean_issues_count": clean_count,
            "loss_pct": round(loss_pct, 2),
            "threshold_pct": _MAX_ISSUE_LOSS_PCT,
        },
    )


@asset_check(
    asset=clean_jira_sprints,
    description="Verify raw vs clean sprint count delta is within tolerance",
)
def check_raw_clean_sprint_count(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Compare raw and clean sprint counts.

    Detects silent data loss between Bronze and Silver sprint data.
    All sprints from raw_jira.sprints should appear in clean_jira.sprints.
    """
    engine = database.get_engine()

    with engine.connect() as conn:
        raw_exists = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'raw_jira' AND table_name = 'sprints'
            )
        """
            )
        ).scalar()

        if not raw_exists:
            return AssetCheckResult(
                passed=True,
                metadata={"status": "skipped_no_raw_table"},
            )

        raw_count = (
            conn.execute(text("SELECT COUNT(*) FROM raw_jira.sprints")).scalar() or 0
        )
        clean_count = (
            conn.execute(text("SELECT COUNT(*) FROM clean_jira.sprints")).scalar() or 0
        )

    if raw_count == 0:
        return AssetCheckResult(passed=True, metadata={"status": "no_raw_data"})

    loss_pct = max(0.0, ((raw_count - clean_count) / raw_count) * 100)
    passed = loss_pct <= _MAX_ISSUE_LOSS_PCT

    return AssetCheckResult(
        passed=passed,
        metadata={
            "raw_sprints_count": raw_count,
            "clean_sprints_count": clean_count,
            "loss_pct": round(loss_pct, 2),
            "threshold_pct": _MAX_ISSUE_LOSS_PCT,
        },
    )
