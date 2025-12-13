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
- clean_jira_release_issues: Extract release-issue relationships
- clean_jira_release_issues_changelog: Extract release-issue history
- clean_jira_boards: Transform board configurations
- clean_jira_status_changes: Extract status changes from changelogs
"""

from pipelines.assets.jira.clean import (
    check_issues_have_required_fields,
    check_no_orphan_issues,
    check_release_issues_integrity,
    check_sprint_dates_valid,
    check_sprint_issues_integrity,
    clean_jira_boards,
    clean_jira_field_keys,
    clean_jira_field_value_changelog,
    clean_jira_field_values,
    clean_jira_issues,
    clean_jira_release_issues,
    clean_jira_release_issues_changelog,
    clean_jira_releases,
    clean_jira_sprint_changelog,
    clean_jira_sprint_issues,
    clean_jira_sprint_issues_changelog,
    clean_jira_sprints,
    clean_jira_status_changes,
)
from pipelines.assets.jira.raw import raw_jira_data

__all__ = [
    # Raw assets
    "raw_jira_data",
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
    "clean_jira_release_issues",
    "clean_jira_release_issues_changelog",
    "clean_jira_boards",
    "clean_jira_status_changes",
    # Asset checks
    "check_no_orphan_issues",
    "check_issues_have_required_fields",
    "check_sprint_dates_valid",
    "check_sprint_issues_integrity",
    "check_release_issues_integrity",
]
