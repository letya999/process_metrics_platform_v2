"""Jira assets module.

This module exports all Jira-related Dagster assets:
- raw_jira_data: Load raw data from Jira API using dlt
- clean_jira_issues: Transform raw issues to clean format
- clean_jira_sprints: Transform raw sprints to clean format
- clean_jira_sprint_changelog: Track sprint property changes
- clean_jira_field_keys: Extract field keys from issues
- clean_jira_field_values: Extract current field values
- clean_jira_field_value_changelog: Extract field value change history
- clean_jira_sprint_issues: Extract sprint-issue relationships from changelog
- clean_jira_sprint_issues_changelog: Extract sprint-issue history
- clean_jira_releases: Transform raw versions to releases
- clean_jira_release_changelog: Track release property changes via snapshot diff
- clean_jira_release_issues: Extract release-issue relationships
- clean_jira_release_issues_changelog: Extract release-issue history
- clean_jira_boards: Transform board configurations
- clean_jira_issue_status_changelog: Extract issue status changes from changelog
"""

from pipelines.assets.jira.clean import (
    check_at_most_one_active_sprint_per_project,
    check_closed_sprint_issues_inactive,
    check_field_values_fk_integrity,
    check_issue_fk_integrity,
    check_issues_have_required_fields,
    check_jira_users_have_external_id,
    check_no_orphan_issues,
    check_no_orphan_sprints,
    check_no_orphan_worklogs,
    check_no_self_referencing_issue_links,
    check_no_self_referencing_parent,
    check_raw_clean_issue_count,
    check_raw_clean_sprint_count,
    check_release_issues_integrity,
    check_sprint_dates_valid,
    check_sprint_issues_integrity,
    check_status_changelog_fk_integrity,
    clean_jira_board_column_statuses,
    clean_jira_board_columns,
    clean_jira_boards,
    clean_jira_comments,
    clean_jira_field_keys,
    clean_jira_field_value_changelog,
    clean_jira_field_values,
    clean_jira_issue_labels,
    clean_jira_issue_links,
    clean_jira_issue_status_changelog,
    clean_jira_issue_statuses,
    clean_jira_issue_types,
    clean_jira_issues,
    clean_jira_labels,
    clean_jira_priorities,
    clean_jira_projects,
    clean_jira_release_changelog,
    clean_jira_release_issues,
    clean_jira_release_issues_changelog,
    clean_jira_releases,
    clean_jira_resolutions,
    clean_jira_sprint_changelog,
    clean_jira_sprint_issues,
    clean_jira_sprint_issues_changelog,
    clean_jira_sprints,
    clean_jira_user_issue_roles,
    clean_jira_worklogs,
    jira_ghost_cleanup,
)
from pipelines.assets.jira.raw import raw_jira_data

# Optional partitioned asset (may not exist if partitions not configured)
try:
    from pipelines.assets.jira.raw import raw_jira_project_data
except ImportError:
    raw_jira_project_data = None

__all__ = [
    # Raw assets
    "raw_jira_data",
    "raw_jira_project_data",  # Partitioned version (optional)
    # Clean assets
    "clean_jira_issues",
    "clean_jira_sprints",
    "clean_jira_sprint_changelog",
    "clean_jira_field_keys",
    "clean_jira_field_values",
    "clean_jira_field_value_changelog",
    "clean_jira_sprint_issues",
    "clean_jira_sprint_issues_changelog",
    "clean_jira_releases",
    "clean_jira_release_changelog",
    "clean_jira_release_issues",
    "clean_jira_release_issues_changelog",
    "clean_jira_boards",
    "clean_jira_board_columns",
    "clean_jira_board_column_statuses",
    "clean_jira_issue_status_changelog",
    "clean_jira_issue_types",
    "clean_jira_issue_statuses",
    "clean_jira_projects",
    "clean_jira_labels",
    "clean_jira_issue_labels",
    "clean_jira_worklogs",
    "clean_jira_priorities",
    "clean_jira_resolutions",
    "clean_jira_comments",
    "clean_jira_user_issue_roles",
    "clean_jira_issue_links",
    "jira_ghost_cleanup",
    # Asset checks
    "check_no_orphan_issues",
    "check_issues_have_required_fields",
    "check_sprint_dates_valid",
    "check_sprint_issues_integrity",
    "check_release_issues_integrity",
    "check_raw_clean_issue_count",
    "check_raw_clean_sprint_count",
    # New data quality checks
    "check_closed_sprint_issues_inactive",
    "check_issue_fk_integrity",
    "check_no_orphan_worklogs",
    "check_no_orphan_sprints",
    "check_field_values_fk_integrity",
    "check_no_self_referencing_issue_links",
    "check_status_changelog_fk_integrity",
    "check_at_most_one_active_sprint_per_project",
    "check_no_self_referencing_parent",
    "check_jira_users_have_external_id",
]
