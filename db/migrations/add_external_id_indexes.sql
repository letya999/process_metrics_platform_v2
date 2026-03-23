-- Standalone external_id indexes for fast JOIN from raw layer to clean layer
-- Safe to run multiple times (IF NOT EXISTS)

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_issues_ext_id
    ON clean_jira.issues(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_sprints_ext_id
    ON clean_jira.sprints(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_releases_ext_id
    ON clean_jira.releases(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_jira_users_ext_id
    ON clean_jira.jira_users(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_sprint_changelog_sprint_id_field
    ON clean_jira.sprint_changelog(sprint_id, field_name, changed_at DESC);
