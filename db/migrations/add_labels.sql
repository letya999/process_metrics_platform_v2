-- Migration: Add labels and issue_labels tables
-- Part of Phase 2.5 remediation

CREATE TABLE IF NOT EXISTS clean_jira.labels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS clean_jira.issue_labels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
    label_id uuid NOT NULL REFERENCES clean_jira.labels(id) ON DELETE CASCADE,
    UNIQUE(issue_id, label_id)
);

CREATE INDEX IF NOT EXISTS idx_cj_labels_project ON clean_jira.labels(project_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_labels_issue ON clean_jira.issue_labels(issue_id);
CREATE INDEX IF NOT EXISTS idx_cj_issue_labels_label ON clean_jira.issue_labels(label_id);
