-- ============================================================================
-- CLEAN_JIRA SCHEMA
-- Normalized Jira data layer for storing and managing Jira project data
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS clean_jira;

-- ----------------------------------------------------------------------------
-- ENUMS
-- ----------------------------------------------------------------------------

-- Issue hierarchy levels in Jira
CREATE TYPE clean_jira.issue_hierarchy_level AS ENUM ('epic', 'story', 'task', 'subtask');

-- Issue status categories
CREATE TYPE clean_jira.issue_status_category AS ENUM ('to_do', 'in_progress', 'done');

-- User role types in issues
CREATE TYPE clean_jira.user_role_type AS ENUM ('assignee', 'reporter', 'creator', 'watcher');

-- Sprint statuses
CREATE TYPE clean_jira.sprint_status AS ENUM ('future', 'active', 'closed');

-- Release statuses
CREATE TYPE clean_jira.release_status AS ENUM ('unreleased', 'released', 'archived');

-- ----------------------------------------------------------------------------
-- CORE ENTITIES
-- ----------------------------------------------------------------------------

-- Projects
-- Stores Jira projects with their basic information
CREATE TABLE IF NOT EXISTS clean_jira.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,           -- Jira project ID
    external_key text NOT NULL,          -- Jira project key (e.g., PROJ)
    name text NOT NULL,                  -- Project name
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE(platform_project_id, external_id),
    UNIQUE(platform_project_id, external_key)
);

COMMENT ON TABLE clean_jira.projects IS 'Jira projects with their basic information';
COMMENT ON COLUMN clean_jira.projects.external_id IS 'Jira project ID';
COMMENT ON COLUMN clean_jira.projects.external_key IS 'Jira project key (e.g., PROJ)';

-- Issue Types
-- Defines types of issues (Epic, Story, Task, Subtask, etc.)
CREATE TABLE IF NOT EXISTS clean_jira.issue_types (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                                    -- Jira issue type ID
    name text NOT NULL,                                           -- Type name (e.g., Story, Bug, Epic)
    hierarchy_level clean_jira.issue_hierarchy_level NOT NULL,   -- Hierarchy level in Jira
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

COMMENT ON TABLE clean_jira.issue_types IS 'Types of Jira issues (Epic, Story, Task, Subtask, Bug, etc.)';
COMMENT ON COLUMN clean_jira.issue_types.hierarchy_level IS 'Hierarchy level in Jira structure';

-- Issue Statuses
-- Defines possible statuses for issues
CREATE TABLE IF NOT EXISTS clean_jira.issue_statuses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                                -- Jira status ID
    name text NOT NULL,                                       -- Status name (e.g., To Do, In Progress, Done)
    category clean_jira.issue_status_category NOT NULL,      -- Status category
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

COMMENT ON TABLE clean_jira.issue_statuses IS 'Possible statuses for Jira issues';
COMMENT ON COLUMN clean_jira.issue_statuses.category IS 'Broad category of the status (to_do, in_progress, done)';

-- Issue Priorities
-- Defines possible priorities for issues
CREATE TABLE IF NOT EXISTS clean_jira.issue_priorities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                                -- Jira priority ID
    name text NOT NULL,                                       -- Priority name (e.g., High, Medium, Low)
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

COMMENT ON TABLE clean_jira.issue_priorities IS 'Possible priorities for Jira issues';

-- Issue Resolutions
-- Defines possible resolutions for issues
CREATE TABLE IF NOT EXISTS clean_jira.issue_resolutions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                                -- Jira resolution ID
    name text NOT NULL,                                       -- Resolution name (e.g., Done, Canceled)
    description text,                                         -- Resolution description
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

COMMENT ON TABLE clean_jira.issue_resolutions IS 'Possible resolutions for Jira issues';

-- ----------------------------------------------------------------------------
-- JIRA USERS
-- ----------------------------------------------------------------------------

-- Jira Users
-- Stores information about Jira users
CREATE TABLE IF NOT EXISTS clean_jira.jira_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,          -- Jira Cloud account ID
    display_name text NOT NULL,         -- User's display name
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id)
);

COMMENT ON TABLE clean_jira.jira_users IS 'Jira users associated with projects';
COMMENT ON COLUMN clean_jira.jira_users.external_id IS 'Jira Cloud account ID';

-- ----------------------------------------------------------------------------
-- ISSUES
-- ----------------------------------------------------------------------------

-- Issues
-- Main table for Jira issues
CREATE TABLE IF NOT EXISTS clean_jira.issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                               -- Jira issue ID
    external_key text NOT NULL,                              -- Jira issue key (e.g., PROJ-123)
    summary text NOT NULL,                                   -- Issue title/summary
    description text,                                        -- Issue description
    type_id uuid NOT NULL REFERENCES clean_jira.issue_types(id),
    status_id uuid NOT NULL REFERENCES clean_jira.issue_statuses(id),
    priority_id uuid REFERENCES clean_jira.issue_priorities(id),
    parent_id uuid REFERENCES clean_jira.issues(id),         -- Parent issue (for subtasks)
    jira_created_at timestamptz NOT NULL,                    -- When issue was created in Jira
    jira_updated_at timestamptz NOT NULL,                    -- When issue was last updated in Jira
    jira_resolved_at timestamptz,                            -- When issue was resolved in Jira
    db_created_at timestamptz NOT NULL DEFAULT now(),        -- When record was created in DB
    db_updated_at timestamptz NOT NULL DEFAULT now(),        -- When record was updated in DB
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, external_key)
);

COMMENT ON TABLE clean_jira.issues IS 'Jira issues with their core information';
COMMENT ON COLUMN clean_jira.issues.external_key IS 'Jira issue key (e.g., PROJ-123)';
COMMENT ON COLUMN clean_jira.issues.parent_id IS 'Parent issue reference (for subtasks)';
COMMENT ON COLUMN clean_jira.issues.jira_created_at IS 'Timestamp when issue was created in Jira';
COMMENT ON COLUMN clean_jira.issues.jira_updated_at IS 'Timestamp when issue was last updated in Jira';
COMMENT ON COLUMN clean_jira.issues.jira_resolved_at IS 'Timestamp when issue was resolved in Jira';

-- Jira User Issue Roles
-- Tracks user roles in issues (assignee, reporter, creator, watcher)
CREATE TABLE IF NOT EXISTS clean_jira.jira_user_issue_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES clean_jira.jira_users(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    role_type clean_jira.user_role_type NOT NULL,      -- Type of role
    assigned_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, issue_id, role_type)
);

COMMENT ON TABLE clean_jira.jira_user_issue_roles IS 'User roles in issues (assignee, reporter, creator, watcher)';

-- ----------------------------------------------------------------------------
-- SPRINTS
-- ----------------------------------------------------------------------------

-- Sprints
-- Stores sprint information
CREATE TABLE IF NOT EXISTS clean_jira.sprints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                -- Jira sprint ID
    name text NOT NULL,                       -- Sprint name
    goal text,                                -- Sprint goal/objective
    status clean_jira.sprint_status NOT NULL, -- Sprint status
    start_date timestamptz,                   -- Sprint start date
    end_date timestamptz,                     -- Sprint planned end date
    complete_date timestamptz,                -- Sprint actual completion date
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id)
);

COMMENT ON TABLE clean_jira.sprints IS 'Jira sprints with their timeline and goals';
COMMENT ON COLUMN clean_jira.sprints.goal IS 'Sprint goal or objective';
COMMENT ON COLUMN clean_jira.sprints.complete_date IS 'Actual completion date of the sprint';

-- Sprint Issues
-- Links issues to sprints
CREATE TABLE IF NOT EXISTS clean_jira.sprint_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id uuid NOT NULL REFERENCES clean_jira.sprints(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    is_active boolean NOT NULL DEFAULT true,  -- Whether issue is currently in sprint
    UNIQUE(sprint_id, issue_id)
);

COMMENT ON TABLE clean_jira.sprint_issues IS 'Links issues to sprints';
COMMENT ON COLUMN clean_jira.sprint_issues.is_active IS 'Whether issue is currently active in the sprint';

-- Sprint Issues Changelog
-- Tracks when issues are added/removed from sprints
CREATE TABLE IF NOT EXISTS clean_jira.sprint_issues_changelog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id uuid NOT NULL REFERENCES clean_jira.sprints(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    action text NOT NULL CHECK (action IN ('added', 'removed')),
    changed_by_id uuid REFERENCES clean_jira.jira_users(id),
    changed_at timestamptz NOT NULL,
    UNIQUE(sprint_id, issue_id, action, changed_at)
);

COMMENT ON TABLE clean_jira.sprint_issues_changelog IS 'History of issues being added to or removed from sprints';

-- Sprint Changelog
-- Tracks changes to sprint properties
CREATE TABLE IF NOT EXISTS clean_jira.sprint_changelog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id uuid NOT NULL REFERENCES clean_jira.sprints(id) ON DELETE CASCADE,
    field_name text NOT NULL,                 -- name, goal, start_date, end_date, status
    old_value text,
    new_value text,
    changed_by_id uuid REFERENCES clean_jira.jira_users(id),
    changed_at timestamptz NOT NULL
);

COMMENT ON TABLE clean_jira.sprint_changelog IS 'History of changes to sprint properties';
COMMENT ON COLUMN clean_jira.sprint_changelog.field_name IS 'Name of the field that changed (name, goal, start_date, end_date, status)';

-- ----------------------------------------------------------------------------
-- RELEASES (VERSIONS)
-- ----------------------------------------------------------------------------

-- Releases
-- Stores release/version information
CREATE TABLE IF NOT EXISTS clean_jira.releases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,                  -- Jira version ID
    name text NOT NULL,                         -- Release name/version
    description text,                           -- Release description
    status clean_jira.release_status NOT NULL,  -- Release status
    start_date date,                            -- Release start date
    release_date date,                          -- Planned/actual release date
    is_archived boolean NOT NULL DEFAULT false, -- Whether release is archived
    is_released boolean NOT NULL DEFAULT false, -- Whether release has been released
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id)
);

COMMENT ON TABLE clean_jira.releases IS 'Jira releases/versions with their timeline and status';
COMMENT ON COLUMN clean_jira.releases.is_archived IS 'Whether the release is archived';
COMMENT ON COLUMN clean_jira.releases.is_released IS 'Whether the release has been completed';

-- Release Issues
-- Links issues to releases
CREATE TABLE IF NOT EXISTS clean_jira.release_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL REFERENCES clean_jira.releases(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    is_active boolean NOT NULL DEFAULT true,  -- Whether issue is currently in release
    UNIQUE(release_id, issue_id)
);

COMMENT ON TABLE clean_jira.release_issues IS 'Links issues to releases/versions';
COMMENT ON COLUMN clean_jira.release_issues.is_active IS 'Whether issue is currently active in the release';

-- Release Issues Changelog
-- Tracks when issues are added/removed from releases
CREATE TABLE IF NOT EXISTS clean_jira.release_issues_changelog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL REFERENCES clean_jira.releases(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    action text NOT NULL CHECK (action IN ('added', 'removed')),
    changed_by_id uuid REFERENCES clean_jira.jira_users(id),
    changed_at timestamptz NOT NULL,
    UNIQUE(release_id, issue_id, action, changed_at)
);

COMMENT ON TABLE clean_jira.release_issues_changelog IS 'History of issues being added to or removed from releases';

-- Release Changelog
-- Tracks changes to release properties
CREATE TABLE IF NOT EXISTS clean_jira.release_changelog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL REFERENCES clean_jira.releases(id) ON DELETE CASCADE,
    field_name text NOT NULL,                 -- name, description, start_date, release_date, status
    old_value text,
    new_value text,
    changed_by_id uuid REFERENCES clean_jira.jira_users(id),
    changed_at timestamptz NOT NULL
);

COMMENT ON TABLE clean_jira.release_changelog IS 'History of changes to release properties';
COMMENT ON COLUMN clean_jira.release_changelog.field_name IS 'Name of the field that changed (name, description, start_date, release_date, status)';

-- ----------------------------------------------------------------------------
-- CUSTOM FIELDS
-- ----------------------------------------------------------------------------

-- Field Keys
-- Stores metadata about custom fields
CREATE TABLE IF NOT EXISTS clean_jira.field_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_key text NOT NULL,           -- customfield_10001
    name text NOT NULL,                   -- Field name
    is_custom boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_key),
    UNIQUE(project_id, name)
);

COMMENT ON TABLE clean_jira.field_keys IS 'Metadata for custom and standard Jira fields';
COMMENT ON COLUMN clean_jira.field_keys.external_key IS 'Jira field key (e.g., customfield_10001)';

-- Field Values
-- Stores current values of custom fields for issues
CREATE TABLE IF NOT EXISTS clean_jira.field_values (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    field_key_id uuid NOT NULL REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE,
    json_value jsonb,                     -- Structured JSON value
    value text,                           -- Simple text value
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issue_id, field_key_id)
);

COMMENT ON TABLE clean_jira.field_values IS 'Current values of custom fields for issues';
COMMENT ON COLUMN clean_jira.field_values.json_value IS 'Structured JSON value for complex fields';
COMMENT ON COLUMN clean_jira.field_values.value IS 'Simple text representation of the value';

-- Field Value Changelog
-- Tracks changes to custom field values
CREATE TABLE IF NOT EXISTS clean_jira.field_value_changelog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    field_key_id uuid NOT NULL REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE,
    old_value jsonb,
    new_value jsonb,
    changed_by_id uuid REFERENCES clean_jira.jira_users(id),
    changed_at timestamptz NOT NULL,
    UNIQUE(issue_id, field_key_id, changed_at)
);

COMMENT ON TABLE clean_jira.field_value_changelog IS 'History of changes to custom field values';

-- ----------------------------------------------------------------------------
-- LABELS
-- ----------------------------------------------------------------------------

-- Labels
-- Stores unique labels used in Jira projects
CREATE TABLE IF NOT EXISTS clean_jira.labels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    name text NOT NULL,                   -- Label name
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, name)
);

COMMENT ON TABLE clean_jira.labels IS 'Unique labels used in Jira projects';

-- Issue Labels
-- Links issues to labels
CREATE TABLE IF NOT EXISTS clean_jira.issue_labels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    label_id uuid NOT NULL REFERENCES clean_jira.labels(id) ON DELETE CASCADE,
    UNIQUE(issue_id, label_id)
);

COMMENT ON TABLE clean_jira.issue_labels IS 'Links issues to labels';

-- ----------------------------------------------------------------------------
-- BOARDS
-- ----------------------------------------------------------------------------

-- Boards
-- Stores Jira board information
CREATE TABLE IF NOT EXISTS clean_jira.boards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,            -- Jira board ID
    name text NOT NULL,                   -- Board name
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id)
);

COMMENT ON TABLE clean_jira.boards IS 'Jira boards (Scrum, Kanban, etc.)';

-- Board Columns
-- Defines columns on boards
CREATE TABLE IF NOT EXISTS clean_jira.board_columns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    board_id uuid NOT NULL REFERENCES clean_jira.boards(id) ON DELETE CASCADE,
    name text NOT NULL,                   -- Column name (e.g., To Do, In Progress, Done)
    position int NOT NULL,                -- Column position on board
    UNIQUE(board_id, position),
    UNIQUE(board_id, name)
);

COMMENT ON TABLE clean_jira.board_columns IS 'Columns on Jira boards';
COMMENT ON COLUMN clean_jira.board_columns.position IS 'Display order of the column on the board';

-- Board Column Statuses
-- Maps issue statuses to board columns
CREATE TABLE IF NOT EXISTS clean_jira.board_column_statuses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    board_column_id uuid NOT NULL REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE,
    status_id uuid NOT NULL REFERENCES clean_jira.issue_statuses(id) ON DELETE CASCADE,
    UNIQUE(board_column_id, status_id)
);

COMMENT ON TABLE clean_jira.board_column_statuses IS 'Maps issue statuses to board columns';

-- ----------------------------------------------------------------------------
-- COMMENTS
-- ----------------------------------------------------------------------------

-- Comments
-- Stores issue comments
CREATE TABLE IF NOT EXISTS clean_jira.comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,            -- Jira comment ID
    body text NOT NULL,                   -- Comment text
    author_id uuid REFERENCES clean_jira.jira_users(id),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE(project_id, external_id)
);

COMMENT ON TABLE clean_jira.comments IS 'Comments on Jira issues';

-- Comment Issues
-- Links comments to issues
CREATE TABLE IF NOT EXISTS clean_jira.comment_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id uuid NOT NULL REFERENCES clean_jira.comments(id) ON DELETE CASCADE,
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    UNIQUE(comment_id, issue_id)
);

COMMENT ON TABLE clean_jira.comment_issues IS 'Links comments to issues';

-- ----------------------------------------------------------------------------
-- WORKLOGS
-- ----------------------------------------------------------------------------

-- Worklogs
-- Stores work logs/time entries for issues
CREATE TABLE IF NOT EXISTS clean_jira.worklogs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    external_id text NOT NULL,            -- Jira worklog ID
    author_id uuid REFERENCES clean_jira.jira_users(id),
    time_spent_seconds int NOT NULL,      -- Time spent in seconds
    started_at timestamptz NOT NULL,      -- When work started
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issue_id, external_id)
);

COMMENT ON TABLE clean_jira.worklogs IS 'Work logs/time entries for issues';

-- ----------------------------------------------------------------------------
-- ISSUE RELATIONS
-- ----------------------------------------------------------------------------

-- Relation Issue Types
-- Defines types of relationships between issues
CREATE TABLE IF NOT EXISTS clean_jira.relation_issue_types (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,            -- Jira link type ID
    name text NOT NULL,                   -- blocks, is blocked by, relates to, duplicates
    UNIQUE(project_id, external_id)
);

COMMENT ON TABLE clean_jira.relation_issue_types IS 'Types of relationships between issues (blocks, relates to, duplicates, etc.)';

-- Relation Issue Issues
-- Stores relationships between issues
CREATE TABLE IF NOT EXISTS clean_jira.relation_issue_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    relation_type_id uuid NOT NULL REFERENCES clean_jira.relation_issue_types(id) ON DELETE CASCADE,
    source_issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    target_issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(relation_type_id, source_issue_id, target_issue_id)
);

COMMENT ON TABLE clean_jira.relation_issue_issues IS 'Relationships between issues';
COMMENT ON COLUMN clean_jira.relation_issue_issues.source_issue_id IS 'The issue that is the source of the relationship';
COMMENT ON COLUMN clean_jira.relation_issue_issues.target_issue_id IS 'The issue that is the target of the relationship';

-- ----------------------------------------------------------------------------
-- BLOCKINGS
-- ----------------------------------------------------------------------------

-- Issue Comment Blockings
-- Tracks blocking issues mentioned in comments
CREATE TABLE IF NOT EXISTS clean_jira.issue_comment_blockings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    comment_id uuid NOT NULL REFERENCES clean_jira.comments(id) ON DELETE CASCADE,
    is_resolved boolean NOT NULL DEFAULT false,
    blocked_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE(issue_id, comment_id)
);

COMMENT ON TABLE clean_jira.issue_comment_blockings IS 'Tracks blocking issues mentioned in comments';
COMMENT ON COLUMN clean_jira.issue_comment_blockings.is_resolved IS 'Whether the blocking issue has been resolved';

-- ----------------------------------------------------------------------------
-- VIEWS
-- ----------------------------------------------------------------------------

-- Unique Users View
-- Provides a list of unique Jira users across all projects
CREATE OR REPLACE VIEW clean_jira.v_unique_users AS
SELECT DISTINCT ON (external_id)
    id,
    project_id,
    external_id,
    display_name,
    created_at,
    updated_at
FROM clean_jira.jira_users
ORDER BY external_id, updated_at DESC;

COMMENT ON VIEW clean_jira.v_unique_users IS 'Unique Jira users across all projects, deduplicated by external_id';

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Projects
CREATE INDEX IF NOT EXISTS idx_cj_projects_platform_project ON clean_jira.projects(platform_project_id);
CREATE INDEX IF NOT EXISTS idx_cj_projects_external_key ON clean_jira.projects(platform_project_id, external_key);

-- Issue Types
CREATE INDEX IF NOT EXISTS idx_cj_issue_types_project ON clean_jira.issue_types(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_types_hierarchy ON clean_jira.issue_types(hierarchy_level);

-- Issue Statuses
CREATE INDEX IF NOT EXISTS idx_cj_issue_statuses_project ON clean_jira.issue_statuses(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_statuses_category ON clean_jira.issue_statuses(category);

-- Jira Users
CREATE INDEX IF NOT EXISTS idx_cj_jira_users_project ON clean_jira.jira_users(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_jira_users_external ON clean_jira.jira_users(project_id, external_id);

-- Jira User Issue Roles
CREATE INDEX IF NOT EXISTS idx_cj_user_roles_user ON clean_jira.jira_user_issue_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_cj_user_roles_issue ON clean_jira.jira_user_issue_roles(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_user_roles_type ON clean_jira.jira_user_issue_roles(role_type);

-- Issues
CREATE INDEX IF NOT EXISTS idx_cj_issues_project ON clean_jira.issues(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_type ON clean_jira.issues(type_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_status ON clean_jira.issues(status_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_parent ON clean_jira.issues(parent_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_jira_created ON clean_jira.issues(jira_created_at);
CREATE INDEX IF NOT EXISTS idx_cj_issues_jira_updated ON clean_jira.issues(jira_updated_at);
CREATE INDEX IF NOT EXISTS idx_cj_issues_jira_resolved ON clean_jira.issues(jira_resolved_at) WHERE jira_resolved_at IS NOT NULL;

-- Sprints
CREATE INDEX IF NOT EXISTS idx_cj_sprints_project ON clean_jira.sprints(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprints_status ON clean_jira.sprints(status);
CREATE INDEX IF NOT EXISTS idx_cj_sprints_dates ON clean_jira.sprints(start_date, end_date);

-- Sprint Issues
CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_sprint ON clean_jira.sprint_issues(sprint_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_issue ON clean_jira.sprint_issues(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_active ON clean_jira.sprint_issues(is_active);

-- Sprint Issues Changelog
CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_changelog_sprint ON clean_jira.sprint_issues_changelog(sprint_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_changelog_issue ON clean_jira.sprint_issues_changelog(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_changelog_changed ON clean_jira.sprint_issues_changelog(changed_at);

-- Releases
CREATE INDEX IF NOT EXISTS idx_cj_releases_project ON clean_jira.releases(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_releases_status ON clean_jira.releases(status);
CREATE INDEX IF NOT EXISTS idx_cj_releases_dates ON clean_jira.releases(start_date, release_date);

-- Release Issues
CREATE INDEX IF NOT EXISTS idx_cj_release_issues_release ON clean_jira.release_issues(release_id);
CREATE INDEX IF NOT EXISTS idx_cj_release_issues_issue ON clean_jira.release_issues(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_release_issues_active ON clean_jira.release_issues(is_active);

-- Field Keys
CREATE INDEX IF NOT EXISTS idx_cj_field_keys_project ON clean_jira.field_keys(project_id);

-- Field Values
CREATE INDEX IF NOT EXISTS idx_cj_field_values_issue ON clean_jira.field_values(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_field_values_field_key ON clean_jira.field_values(field_key_id);
CREATE INDEX IF NOT EXISTS idx_cj_field_values_value ON clean_jira.field_values(value);

-- Field Value Changelog
CREATE INDEX IF NOT EXISTS idx_cj_field_value_changelog_issue ON clean_jira.field_value_changelog(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_field_value_changelog_field_key ON clean_jira.field_value_changelog(field_key_id);
CREATE INDEX IF NOT EXISTS idx_cj_field_value_changelog_changed ON clean_jira.field_value_changelog(changed_at);

-- Boards
CREATE INDEX IF NOT EXISTS idx_cj_boards_project ON clean_jira.boards(project_id);

-- Board Columns
CREATE INDEX IF NOT EXISTS idx_cj_board_columns_board ON clean_jira.board_columns(board_id);
CREATE INDEX IF NOT EXISTS idx_cj_board_columns_position ON clean_jira.board_columns(board_id, position);

-- Comments
CREATE INDEX IF NOT EXISTS idx_cj_comments_project ON clean_jira.comments(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_comments_author ON clean_jira.comments(author_id);
CREATE INDEX IF NOT EXISTS idx_cj_comments_created ON clean_jira.comments(created_at);

-- Comment Issues
CREATE INDEX IF NOT EXISTS idx_cj_comment_issues_comment ON clean_jira.comment_issues(comment_id);
CREATE INDEX IF NOT EXISTS idx_cj_comment_issues_issue ON clean_jira.comment_issues(issue_id);

-- Relation Issue Types
CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_types_project ON clean_jira.relation_issue_types(project_id);

-- Relation Issue Issues
CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_issues_type ON clean_jira.relation_issue_issues(relation_type_id);
CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_issues_source ON clean_jira.relation_issue_issues(source_issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_issues_target ON clean_jira.relation_issue_issues(target_issue_id);

-- Issue Comment Blockings
CREATE INDEX IF NOT EXISTS idx_cj_issue_comment_blockings_issue ON clean_jira.issue_comment_blockings(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_comment_blockings_comment ON clean_jira.issue_comment_blockings(comment_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_comment_blockings_resolved ON clean_jira.issue_comment_blockings(is_resolved);
