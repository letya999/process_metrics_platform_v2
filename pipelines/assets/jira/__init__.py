"""Jira assets module.

This module exports all Jira-related Dagster assets:
- raw_jira_data: Load raw data from Jira API using dlt
- clean_jira_issues: Transform raw issues to clean format
- clean_jira_sprints: Transform raw sprints to clean format
- clean_jira_status_changes: Extract status changes from changelogs
"""

from pipelines.assets.jira.clean import (
    check_issues_have_required_fields,
    check_no_orphan_issues,
    check_sprint_dates_valid,
    clean_jira_issues,
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
    "clean_jira_status_changes",
    # Asset checks
    "check_no_orphan_issues",
    "check_issues_have_required_fields",
    "check_sprint_dates_valid",
]
