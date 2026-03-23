-- Migration: Add worklogs table
-- Part of Phase 2.6 remediation

CREATE TABLE IF NOT EXISTS clean_jira.worklogs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    author_id uuid REFERENCES clean_jira.jira_users(id),
    time_spent_seconds int NOT NULL,
    started_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issue_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_cj_worklogs_issue ON clean_jira.worklogs(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_worklogs_author ON clean_jira.worklogs(author_id);
CREATE INDEX IF NOT EXISTS idx_cj_worklogs_started ON clean_jira.worklogs(started_at);
