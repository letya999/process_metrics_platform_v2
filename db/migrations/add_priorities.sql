-- Migration: Add priorities table and priority_id to issues
-- Part of Phase 2.8 remediation

CREATE TABLE IF NOT EXISTS clean_jira.issue_priorities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

ALTER TABLE clean_jira.issues ADD COLUMN IF NOT EXISTS priority_id uuid REFERENCES clean_jira.issue_priorities(id);

CREATE INDEX IF NOT EXISTS idx_cj_issue_priorities_project ON clean_jira.issue_priorities(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_priority ON clean_jira.issues(priority_id);
