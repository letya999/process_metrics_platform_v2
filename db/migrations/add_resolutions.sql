-- Migration: Add resolutions table and resolution_id to issues
-- Part of Phase 2.9 remediation

CREATE TABLE IF NOT EXISTS clean_jira.issue_resolutions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, external_id),
    UNIQUE(project_id, name)
);

ALTER TABLE clean_jira.issues ADD COLUMN IF NOT EXISTS resolution_id uuid REFERENCES clean_jira.issue_resolutions(id);

CREATE INDEX IF NOT EXISTS idx_cj_issue_resolutions_project ON clean_jira.issue_resolutions(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issues_resolution ON clean_jira.issues(resolution_id);
