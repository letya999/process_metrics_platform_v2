"""Jira clean layer assets package.

Re-exports all assets, asset checks, and internal helpers so that
`from pipelines.assets.jira.clean import X` continues to work unchanged
after the module-to-package conversion.
"""

from ._utils import _detect_sprint_field_id, _get_platform_project_id
from .boards import (
    clean_jira_board_column_statuses,
    clean_jira_board_columns,
    clean_jira_boards,
)
from .checks import (
    _MAX_ISSUE_LOSS_PCT,
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
)
from .dimensions import (
    clean_jira_field_keys,
    clean_jira_issue_statuses,
    clean_jira_issue_types,
    clean_jira_priorities,
    clean_jira_projects,
    clean_jira_resolutions,
)
from .issues import (
    clean_jira_issue_labels,
    clean_jira_issue_links,
    clean_jira_issue_status_changelog,
    clean_jira_issues,
    clean_jira_labels,
    clean_jira_user_issue_roles,
)
from .maintenance import jira_ghost_cleanup
from .releases import (
    clean_jira_release_changelog,
    clean_jira_release_issues,
    clean_jira_release_issues_changelog,
    clean_jira_releases,
)
from .sprints import (
    clean_jira_sprint_changelog,
    clean_jira_sprint_issues,
    clean_jira_sprint_issues_changelog,
    clean_jira_sprints,
)
from .supplementary import (
    clean_jira_comments,
    clean_jira_field_value_changelog,
    clean_jira_field_values,
    clean_jira_worklogs,
)

__all__ = [
    # utils (private, exposed for tests)
    "_detect_sprint_field_id",
    "_get_platform_project_id",
    # dimensions
    "clean_jira_projects",
    "clean_jira_issue_types",
    "clean_jira_priorities",
    "clean_jira_resolutions",
    "clean_jira_issue_statuses",
    "clean_jira_field_keys",
    # issues
    "clean_jira_issues",
    "clean_jira_labels",
    "clean_jira_issue_labels",
    "clean_jira_user_issue_roles",
    "clean_jira_issue_links",
    "clean_jira_issue_status_changelog",
    # sprints
    "clean_jira_sprints",
    "clean_jira_sprint_issues",
    "clean_jira_sprint_issues_changelog",
    "clean_jira_sprint_changelog",
    # releases
    "clean_jira_releases",
    "clean_jira_release_changelog",
    "clean_jira_release_issues",
    "clean_jira_release_issues_changelog",
    # boards
    "clean_jira_boards",
    "clean_jira_board_columns",
    "clean_jira_board_column_statuses",
    # supplementary
    "clean_jira_worklogs",
    "clean_jira_comments",
    "clean_jira_field_values",
    "clean_jira_field_value_changelog",
    # maintenance
    "jira_ghost_cleanup",
    # checks
    "_MAX_ISSUE_LOSS_PCT",
    "check_no_orphan_issues",
    "check_issues_have_required_fields",
    "check_sprint_dates_valid",
    "check_sprint_issues_integrity",
    "check_release_issues_integrity",
    "check_raw_clean_issue_count",
    "check_raw_clean_sprint_count",
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
