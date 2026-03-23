-- Migration: Add v_unique_users view
-- Part of Phase 2.7 remediation

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
