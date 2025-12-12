"""Clean Jira assets - transform raw data to normalized clean layer.

This module implements the clean layer (Silver) of the medallion architecture.
Data is transformed from raw_jira schema to clean_jira schema with normalization.
"""

from typing import Any

from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check
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
        # First, ensure platform project exists
        context.log.info("Ensuring platform project exists...")
        platform_project = conn.execute(
            text("""
            SELECT id FROM platform.projects
            LIMIT 1
        """)
        ).first()

        if not platform_project:
            context.log.info("No platform project found, creating default one...")
            platform_project_id = conn.execute(
                text("""
                INSERT INTO platform.projects (name, created_at, updated_at)
                VALUES ('Default Jira Project', now(), now())
                RETURNING id
            """)
            ).scalar()
        else:
            platform_project_id = platform_project[0]

        context.log.info(f"Using platform project: {platform_project_id}")

        # Sync projects from raw to clean
        context.log.info("Syncing projects...")
        projects_synced = conn.execute(
            text("""
            INSERT INTO clean_jira.projects (
                platform_project_id,
                external_id,
                external_key,
                name,
                created_at,
                updated_at
            )
            SELECT
                :platform_project_id as platform_project_id,
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
        """).bindparams(platform_project_id=platform_project_id)
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
                CASE r.fields__status__statuscategory__key
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

        # Sync Jira users
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

        # Sync issues
        context.log.info("Syncing issues...")
        issues_result = conn.execute(
            text("""
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
                r.fields__description as description,
                it.id as type_id,
                ist.id as status_id,
                r.fields__created::timestamptz as jira_created_at,
                r.fields__updated::timestamptz as jira_updated_at,
                r.fields__resolutiondate::timestamptz as jira_resolved_at,
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
            SELECT DISTINCT
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
    context: AssetExecutionContext,
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
    context: AssetExecutionContext,
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
    context: AssetExecutionContext,
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
