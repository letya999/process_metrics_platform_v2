"""Clean layer assets for Jira issues and related tables.

Covers: issues (with user sync side-effect), labels, issue_labels,
        user_issue_roles, issue_links, issue_status_changelog.
"""

# ruff: noqa: S608

from typing import Any

from dagster import AssetExecutionContext, asset
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource

from ._utils import _table_exists


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
        history_table_exists = _table_exists(
            conn, "raw_jira", "issues__changelog__histories"
        )

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

        # C-4: Count dropped issues due to missing dimensions
        drop_count_result = conn.execute(
            text(
                """
            SELECT COUNT(*)
            FROM raw_jira.issues r
            JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
            LEFT JOIN clean_jira.issue_types it ON it.project_id = p.id
                AND it.external_id = r.fields__issuetype__id
            LEFT JOIN clean_jira.issue_statuses ist ON ist.project_id = p.id
                AND ist.external_id = r.fields__status__id
            WHERE (it.id IS NULL OR ist.id IS NULL) AND r.id IS NOT NULL
        """
            )
        )
        drop_count = drop_count_result.scalar()
        if drop_count > 0:
            context.log.warning(
                f"{drop_count} issues dropped due to missing type_id or status_id in dimension tables"
            )

        # H-8: Check for issues with null creation date
        null_date_result = conn.execute(
            text("SELECT COUNT(*) FROM raw_jira.issues WHERE fields__created IS NULL")
        )
        null_date_count = null_date_result.scalar()
        if null_date_count > 0:
            context.log.warning(
                f"{null_date_count} issues dropped due to NULL fields__created"
            )

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
                NULLIF(trim(r.fields__created::text), '')::timestamptz as jira_created_at,
                NULLIF(trim(r.fields__updated::text), '')::timestamptz as jira_updated_at,
                NULLIF(trim({resolutiondate_col}::text), '')::timestamptz as jira_resolved_at,
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
            WHERE r.fields__created IS NOT NULL
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
                    f"""
                UPDATE clean_jira.issues i
                SET parent_id = parent.id
                FROM raw_jira.issues r
                JOIN clean_jira.issues parent ON parent.external_id = {parent_id_raw_col}
                WHERE i.external_id = r.id::text
                  AND parent.project_id = i.project_id
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
        table_exists = _table_exists(conn, "raw_jira", "issues__fields__labels")

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
        table_exists = _table_exists(conn, "raw_jira", "issues__fields__labels")

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
        table_exists = _table_exists(conn, "raw_jira", "issues__fields__issuelinks")

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
        # H-3: We need to handle both outward and inward links via UNION ALL
        result = conn.execute(
            text(
                """
            WITH link_data AS (
                -- Outward links: source -> target
                SELECT
                    il.type__id as type_external_id,
                    r.id::text as source_external_id,
                    il.outward_issue__id::text as target_external_id,
                    r.fields__project__id::text as project_external_id
                FROM raw_jira.issues__fields__issuelinks il
                JOIN raw_jira.issues r ON il._dlt_parent_id = r._dlt_id
                WHERE il.type__id IS NOT NULL AND il.outward_issue__id IS NOT NULL
                UNION ALL
                -- Inward links: source -> target (inward direction)
                SELECT
                    il.type__id as type_external_id,
                    r.id::text as source_external_id,
                    il.inward_issue__id::text as target_external_id,
                    r.fields__project__id::text as project_external_id
                FROM raw_jira.issues__fields__issuelinks il
                JOIN raw_jira.issues r ON il._dlt_parent_id = r._dlt_id
                WHERE il.type__id IS NOT NULL AND il.inward_issue__id IS NOT NULL
                  AND il.outward_issue__id IS DISTINCT FROM il.inward_issue__id  -- avoid dup when same
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
        changelog_exists = _table_exists(
            conn, "raw_jira", "issues__changelog__histories__items"
        )

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
            -- H-13: Allow updating from_status_id if Jira corrects it
            ON CONFLICT (issue_id, to_status_id, changed_at) DO UPDATE SET
                from_status_id = EXCLUDED.from_status_id
            WHERE clean_jira.issue_status_changelog.from_status_id IS DISTINCT FROM EXCLUDED.from_status_id
            RETURNING id
        """
            )
        )

        count = len(result.fetchall())
        context.log.info(f"Inserted {count} status changelog entries")
        conn.commit()

    return {"status": "success", "changelog_entries": count}
