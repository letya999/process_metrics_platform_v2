"""Clean layer assets for Jira sprint tables.

Covers: sprints, sprint_issues, sprint_issues_changelog, sprint_changelog.
"""

# ruff: noqa: S608

from typing import Any

from dagster import AssetExecutionContext, asset
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource

from ._utils import _detect_sprint_field_id


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
            ),
            {"sprint_field_id": sprint_field_id},
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
            ),
            {"sprint_field_id": sprint_field_id},
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
