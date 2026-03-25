"""Project-wide constants for pipeline configuration.

Defines stable identifiers that are known ahead of time but may vary across
Jira instances. Prefer configuration (metrics.units, calculation_settings) over
these constants — use them only as last-resort fallbacks with explicit warnings.
"""

# Jira custom field IDs commonly used for sprint assignment.
# dlt generates table names like raw_jira.issues__fields__{SPRINT_FIELD_ID}.
# Override via JIRA_SPRINT_FIELD_ID env var or detect at runtime via _utils.py.
SPRINT_FIELD_ID_CANDIDATES = [
    "customfield_10020",  # Most common Jira Cloud default
    "customfield_10021",  # Some older instances
]
SPRINT_FIELD_ID_DEFAULT = "customfield_10020"

# Story points field — used as fallback when metrics.units is not seeded.
# DEPRECATED: Prefer resolve_unit_field(engine, project_id, "story_points").
STORY_POINTS_FIELD_CANDIDATES = [
    "customfield_10036",
    "customfield_10016",
    "story_points",
]
