"""Clean layer assets for Jira release (version) tables.

Covers: releases, release_changelog, release_issues, release_issues_changelog.
"""

from typing import Any

from dagster import AssetExecutionContext, asset
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource


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
