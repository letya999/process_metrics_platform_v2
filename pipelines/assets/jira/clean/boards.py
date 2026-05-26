"""Clean layer assets for Jira board tables.

Covers: boards, board_columns, board_column_statuses.
"""

from typing import Any

from dagster import AssetExecutionContext, asset
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource


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
        # Serialize board column rebuild to avoid concurrent run collisions on
        # unique (board_id, position) when multiple runs overlap.
        conn.execute(
            text(
                """
            LOCK TABLE clean_jira.board_column_statuses IN EXCLUSIVE MODE;
            LOCK TABLE clean_jira.board_columns IN EXCLUSIVE MODE;
            """
            )
        )
        # Avoid transient unique conflicts on (board_id, position) when Jira column
        # positions are re-ordered: move existing rows out of the way, then apply
        # desired positions from raw snapshot.
        result = conn.execute(
            text(
                """
            WITH src_raw AS (
                SELECT DISTINCT ON (b.id, col.name)
                    b.id AS board_id,
                    col.name AS name,
                    col._dlt_list_idx::int AS raw_position
                FROM raw_jira.board_configurations__columns_config__columns col
                JOIN raw_jira.board_configurations bc ON col._dlt_parent_id = bc._dlt_id
                JOIN clean_jira.projects p ON p.external_key = bc.project_key
                JOIN clean_jira.boards b ON b.project_id = p.id AND b.external_id = bc.board_id::text
                WHERE col.name IS NOT NULL
                ORDER BY b.id, col.name, bc._dlt_id DESC
            ),
            src AS (
                SELECT
                    board_id,
                    name,
                    (row_number() OVER (PARTITION BY board_id ORDER BY raw_position, name) - 1)::int AS position
                FROM src_raw
            ),
            affected_boards AS (
                SELECT DISTINCT board_id
                FROM src
            ),
            deleted_statuses AS (
                DELETE FROM clean_jira.board_column_statuses bcs
                USING clean_jira.board_columns bc
                WHERE bcs.board_column_id = bc.id
                  AND EXISTS (
                      SELECT 1
                      FROM affected_boards ab
                      WHERE ab.board_id = bc.board_id
                  )
                RETURNING bcs.board_column_id
            ),
            deleted_columns AS (
                DELETE FROM clean_jira.board_columns bc
                WHERE EXISTS (
                    SELECT 1
                    FROM affected_boards ab
                    WHERE ab.board_id = bc.board_id
                )
                RETURNING bc.id
            ),
            upserted AS (
                INSERT INTO clean_jira.board_columns (board_id, name, position)
                SELECT s.board_id, s.name, s.position
                FROM src s
                RETURNING id
            )
            SELECT count(*)::int AS affected_count FROM upserted
        """
            )
        )
        count = int(result.scalar() or 0)
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
