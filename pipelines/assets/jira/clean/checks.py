"""Asset checks for Jira clean layer data quality.

Each check targets a specific asset and surfaces silent data-quality issues
that would otherwise go undetected until a downstream consumer fails.
"""

from dagster import AssetCheckExecutionContext, AssetCheckResult, AssetKey, asset_check
from sqlalchemy import text

from pipelines.resources.database import DatabaseResource

from .issues import (
    clean_jira_issue_links,
    clean_jira_issue_status_changelog,
    clean_jira_issues,
)
from .releases import clean_jira_release_issues
from .sprints import clean_jira_sprint_issues, clean_jira_sprints
from .supplementary import clean_jira_field_values, clean_jira_worklogs

# Maximum acceptable percentage of clean issues missing vs raw issues.
# 5% allows for issues legitimately filtered out (no project match, etc.).
_MAX_ISSUE_LOSS_PCT = 5.0


@asset_check(asset=clean_jira_issues)
def check_no_orphan_issues(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure all issues have valid project_id."""
    engine = database.get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.issues i
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.projects p
                WHERE p.id = i.project_id
            )
        """))
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
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.issues
            WHERE external_key IS NULL
               OR summary IS NULL
               OR type_id IS NULL
               OR status_id IS NULL
        """))
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
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.sprints
            WHERE start_date IS NOT NULL
              AND end_date IS NOT NULL
              AND start_date > end_date
        """))
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
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.sprint_issues si
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.sprints s WHERE s.id = si.sprint_id
            )
               OR NOT EXISTS (
                   SELECT 1 FROM clean_jira.issues i WHERE i.id = si.issue_id
               )
        """))
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
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.release_issues ri
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.releases r WHERE r.id = ri.release_id
            )
               OR NOT EXISTS (
                   SELECT 1 FROM clean_jira.issues i WHERE i.id = ri.issue_id
               )
        """))
        invalid_count = result.scalar() or 0

    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"invalid_release_issues_count": invalid_count},
    )


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
        from ._utils import _table_exists

        raw_exists = _table_exists(conn, "raw_jira", "issues")

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
        from ._utils import _table_exists

        raw_exists = _table_exists(conn, "raw_jira", "sprints")

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


@asset_check(
    asset=clean_jira_sprint_issues,
    description="Ensure sprint_issues.is_active=false for all issues in closed sprints",
)
def check_closed_sprint_issues_inactive(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect sprint_issues with is_active=true that belong to a closed sprint.

    When a sprint closes, all its sprint_issues should have is_active=false.
    Any row violating this indicates the reconciliation step failed.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.sprint_issues si
            JOIN clean_jira.sprints s ON s.id = si.sprint_id
            WHERE s.status = 'closed' AND si.is_active = true
        """))
        invalid_count = result.scalar() or 0
    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"active_issues_in_closed_sprints": invalid_count},
    )


@asset_check(
    asset=clean_jira_issues,
    description="Verify all issues have valid type_id and status_id foreign keys",
)
def check_issue_fk_integrity(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect issues with broken FK to issue_types or issue_statuses.

    A broken FK here means the dimension sync ran before the main issues sync,
    or a dimension row was deleted without cascading.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.issues i
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.issue_types t WHERE t.id = i.type_id
            )
               OR NOT EXISTS (
                SELECT 1 FROM clean_jira.issue_statuses s WHERE s.id = i.status_id
            )
        """))
        invalid_count = result.scalar() or 0
    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"issues_with_broken_dimension_fk": invalid_count},
    )


@asset_check(
    asset=clean_jira_worklogs,
    description="Ensure all worklogs reference a valid issue",
)
def check_no_orphan_worklogs(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect worklogs whose issue_id does not exist in clean_jira.issues."""
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.worklogs w
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.issues i WHERE i.id = w.issue_id
            )
        """))
        orphan_count = result.scalar() or 0
    return AssetCheckResult(
        passed=orphan_count == 0,
        metadata={"orphan_worklogs_count": orphan_count},
    )


@asset_check(
    asset=clean_jira_sprints,
    description="Ensure all sprints have a valid project_id",
)
def check_no_orphan_sprints(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect sprints with a project_id that no longer exists in clean_jira.projects."""
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.sprints s
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.projects p WHERE p.id = s.project_id
            )
        """))
        orphan_count = result.scalar() or 0
    return AssetCheckResult(
        passed=orphan_count == 0,
        metadata={"orphan_sprints_count": orphan_count},
    )


@asset_check(
    asset=clean_jira_field_values,
    description="Ensure all field_values reference an existing field_key",
)
def check_field_values_fk_integrity(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect field_values rows with a broken field_key_id reference.

    Indicates field_keys and field_values ran in the wrong order, or a
    field_keys row was manually deleted.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.field_values fv
            WHERE NOT EXISTS (
                SELECT 1 FROM clean_jira.field_keys fk WHERE fk.id = fv.field_key_id
            )
        """))
        invalid_count = result.scalar() or 0
    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"field_values_broken_fk_count": invalid_count},
    )


@asset_check(
    asset=clean_jira_issue_links,
    description="Detect self-referencing issue links (source == target)",
)
def check_no_self_referencing_issue_links(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure no issue link points from an issue to itself.

    Self-referencing links are invalid per Jira's data model and indicate
    a parsing error in the raw-to-clean transformation.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.relation_issue_issues
            WHERE source_issue_id = target_issue_id
        """))
        self_ref_count = result.scalar() or 0
    return AssetCheckResult(
        passed=self_ref_count == 0,
        metadata={"self_referencing_links_count": self_ref_count},
    )


@asset_check(
    asset=clean_jira_issue_status_changelog,
    description="Verify status changelog entries resolve to a known to_status_id",
)
def check_status_changelog_fk_integrity(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect status changelog rows where to_status_id is NULL or unresolvable.

    The WHERE clause in the INSERT already filters out unresolvable statuses,
    so any NULL here means a data integrity regression.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.issue_status_changelog sc
            WHERE sc.to_status_id IS NULL
               OR NOT EXISTS (
                   SELECT 1 FROM clean_jira.issue_statuses s WHERE s.id = sc.to_status_id
               )
        """))
        invalid_count = result.scalar() or 0
    return AssetCheckResult(
        passed=invalid_count == 0,
        metadata={"changelog_unresolved_to_status_count": invalid_count},
    )


@asset_check(
    asset=clean_jira_sprints,
    description="Warn when more than one sprint is active per project",
)
def check_at_most_one_active_sprint_per_project(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect projects with multiple simultaneously active sprints.

    Jira normally enforces one active sprint per board. Multiple active sprints
    indicate either a data sync issue or that the board uses parallel sprints
    (which the rest of the pipeline does not model correctly).
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM (
                SELECT project_id
                FROM clean_jira.sprints
                WHERE status = 'active'
                GROUP BY project_id
                HAVING count(*) > 1
            ) sub
        """))
        projects_with_multiple = result.scalar() or 0
    return AssetCheckResult(
        passed=projects_with_multiple == 0,
        metadata={"projects_with_multiple_active_sprints": projects_with_multiple},
    )


@asset_check(
    asset=clean_jira_issues,
    description="Detect issues where parent_id references the issue itself",
)
def check_no_self_referencing_parent(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Ensure no issue has parent_id == id, which creates an infinite hierarchy loop."""
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.issues
            WHERE parent_id IS NOT NULL AND parent_id = id
        """))
        self_ref_count = result.scalar() or 0
    return AssetCheckResult(
        passed=self_ref_count == 0,
        metadata={"self_referencing_parents_count": self_ref_count},
    )


@asset_check(
    asset=clean_jira_issues,
    description="Ensure all jira_users have a non-null external_id",
)
def check_jira_users_have_external_id(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect jira_users rows with null external_id.

    Users are populated as a side effect of clean_jira_issues. A null external_id
    breaks all downstream joins on user account IDs.
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT count(*) FROM clean_jira.jira_users WHERE external_id IS NULL
        """))
        null_count = result.scalar() or 0
    return AssetCheckResult(
        passed=null_count == 0,
        metadata={"users_with_null_external_id": null_count},
    )


@asset_check(
    asset=AssetKey("calculate_flow_efficiency"),
    description="Verify flow_efficiency_pct is not all-zero (detects missing/wrong status category config)",
)
def check_flow_efficiency_nonzero(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect case where flow_efficiency_pct is 0 for ALL issues.
    This indicates status category misconfiguration (e.g. wrong category enum values).
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        # Check fact_values for flow_efficiency metric
        result = conn.execute(text("""
            SELECT COUNT(*) as total, SUM(CASE WHEN value > 0 THEN 1 ELSE 0 END) as nonzero
            FROM metrics.fact_values fv
            JOIN metrics.calculations c ON c.id = fv.metric_id
            WHERE c.calc_code = 'flow_efficiency_pct'
        """)).fetchone()
    total = result[0] or 0
    nonzero = result[1] or 0
    if total == 0:
        return AssetCheckResult(passed=True, metadata={"status": "no_data"})
    nonzero_pct = (nonzero / total) * 100
    return AssetCheckResult(
        passed=nonzero_pct
        > 5.0,  # At least 5% of issues should have >0 flow efficiency
        metadata={
            "total_rows": total,
            "nonzero_rows": nonzero,
            "nonzero_pct": round(nonzero_pct, 2),
        },
    )
