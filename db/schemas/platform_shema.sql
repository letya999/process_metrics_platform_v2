-- ============================================================================
-- SCHEMA: platform
-- Owner: platform services (auth, admin, orchestrator)
-- Purpose: Platform entities - users, integrations, projects, orchestration, audit
-- Access: auth_service, admin_service, orchestrator_service
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS platform;

COMMENT ON SCHEMA platform IS 'Platform core: users, tool integrations, projects, access control, orchestration, audit';

-- ============================================================================
-- ENUMS
-- ============================================================================

-- External tool types for pseudo-SSO
CREATE TYPE platform.external_tool_type AS ENUM (
    'metabase',
    'superset',
    'grafana'
);

COMMENT ON TYPE platform.external_tool_type IS 'External BI tools for user synchronization';

-- User roles in external tools
CREATE TYPE platform.external_tool_role AS ENUM (
    'admin',
    'editor',
    'viewer'
);

COMMENT ON TYPE platform.external_tool_role IS 'Access levels in external BI tools';

-- Integration types
CREATE TYPE platform.integration_type_enum AS ENUM (
    'jira_cloud',
    'jira_server',
    'jira_datacenter',
    'linear',
    'asana',
    'github',
    'gitlab'
);

COMMENT ON TYPE platform.integration_type_enum IS 'Supported external system types';

-- Project access levels
CREATE TYPE platform.project_access_level AS ENUM (
    'owner',
    'admin',
    'viewer'
);

COMMENT ON TYPE platform.project_access_level IS 'Project access rights: owner (full), admin (configure metrics), viewer (read-only)';

-- ============================================================================
-- TABLE: users
-- Purpose: Platform users with unified email/password authentication
-- Access: auth_service (RW), admin_service (RW), orchestrator (R)
-- ============================================================================

CREATE TABLE platform.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_password_change TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON platform.users(email);
CREATE INDEX idx_users_is_active ON platform.users(is_active);

COMMENT ON TABLE platform.users IS 'Platform users: unified authentication, SSO source for external tools';
COMMENT ON COLUMN platform.users.password_hash IS 'Single password for platform and external tools (synced via external_tool_users)';
COMMENT ON COLUMN platform.users.is_admin IS 'Platform administrator flag';
COMMENT ON COLUMN platform.users.last_password_change IS 'Track password sync status with external tools';

-- ============================================================================
-- TABLE: external_tool_users
-- Purpose: User synchronization with external BI tools (Metabase, Grafana, etc.)
-- Access: admin_service (RW), auth_service (R)
-- Pattern: Pseudo-SSO - platform users synced to external tools with same credentials
-- ============================================================================

CREATE TABLE platform.external_tool_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES platform.users(id) ON DELETE CASCADE,

    tool_type platform.external_tool_type NOT NULL,
    tool_user_id TEXT NOT NULL,
    tool_email TEXT NOT NULL,
    tool_password_hash TEXT NOT NULL,
    tool_role platform.external_tool_role NOT NULL DEFAULT 'viewer',

    sync_status TEXT NOT NULL DEFAULT 'pending',
    last_sync_at TIMESTAMPTZ,
    sync_error TEXT,

    is_active BOOLEAN NOT NULL DEFAULT true,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(user_id, tool_type),
    UNIQUE(tool_type, tool_user_id),
    UNIQUE(tool_type, tool_email)
);

CREATE INDEX idx_external_tool_users_user_id ON platform.external_tool_users(user_id);
CREATE INDEX idx_external_tool_users_tool_type ON platform.external_tool_users(tool_type);
CREATE INDEX idx_external_tool_users_sync_status ON platform.external_tool_users(sync_status);

COMMENT ON TABLE platform.external_tool_users IS 'Pseudo-SSO: sync platform users to external BI tools with matching credentials';
COMMENT ON COLUMN platform.external_tool_users.tool_password_hash IS 'Password hash in external tool (typically matches platform.users.password_hash)';
COMMENT ON COLUMN platform.external_tool_users.sync_status IS 'Sync state: pending, synced, failed';
COMMENT ON COLUMN platform.external_tool_users.tool_user_id IS 'User ID in external tool (Metabase user_id, etc.)';

-- ============================================================================
-- TABLE: integration_types
-- Purpose: Reference dictionary of supported external system types
-- Access: All services (R), admin_service (RW)
-- ============================================================================

CREATE TABLE platform.integration_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name platform.integration_type_enum UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_integration_types_name ON platform.integration_types(name);
CREATE INDEX idx_integration_types_is_active ON platform.integration_types(is_active);

COMMENT ON TABLE platform.integration_types IS 'Catalog of supported integration types (Jira, GitLab, Linear, etc.)';

-- Populate base types
INSERT INTO platform.integration_types (name, description) VALUES
    ('jira_cloud', 'Jira Cloud integration'),
    ('jira_server', 'Jira Server integration (self-hosted)'),
    ('jira_datacenter', 'Jira Data Center integration (self-hosted)'),
    ('linear', 'Linear integration'),
    ('asana', 'Asana integration'),
    ('github', 'GitHub integration'),
    ('gitlab', 'GitLab integration');

-- ============================================================================
-- TABLE: tool_integrations
-- Purpose: User connections to external systems with API credentials
-- Access: admin_service (RW), connector services (R), orchestrator (R)
-- Security: Tokens stored via secret_reference (env vars, Vault, AWS Secrets)
-- ============================================================================

CREATE TABLE platform.tool_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES platform.users(id) ON DELETE CASCADE,
    integration_type_id UUID NOT NULL REFERENCES platform.integration_types(id),

    -- Connection parameters
    instance_url TEXT,
    user_email TEXT,

    -- Secure token storage (preferred)
    secret_reference TEXT,
    secret_provider TEXT DEFAULT 'env',

    -- Fallback insecure storage (deprecated, dev/test only)
    api_token_unsafe TEXT,

    api_token_expires_at TIMESTAMPTZ,
    api_token_expired BOOLEAN DEFAULT FALSE NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT true,
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT,
    last_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(user_id, integration_type_id, instance_url),

    CHECK (
        -- Either secure storage (and NO insecure)
        (secret_reference IS NOT NULL AND secret_provider IS NOT NULL AND api_token_unsafe IS NULL)
        OR
        -- Or insecure storage (and NO secure)
        (secret_reference IS NULL AND secret_provider IS NULL AND api_token_unsafe IS NOT NULL)
    )
);

CREATE INDEX idx_tool_integrations_user_id ON platform.tool_integrations(user_id);
CREATE INDEX idx_tool_integrations_integration_type_id ON platform.tool_integrations(integration_type_id);
CREATE INDEX idx_tool_integrations_is_active ON platform.tool_integrations(is_active);
CREATE INDEX idx_tool_integrations_last_sync ON platform.tool_integrations(last_sync_at);
CREATE INDEX idx_tool_integrations_secret_provider ON platform.tool_integrations(secret_provider);

COMMENT ON TABLE platform.tool_integrations IS 'User integrations with external systems: API credentials, sync status';
COMMENT ON COLUMN platform.tool_integrations.instance_url IS 'Instance URL for self-hosted systems (NULL for SaaS)';
COMMENT ON COLUMN platform.tool_integrations.user_email IS 'User email in integrated system';
COMMENT ON COLUMN platform.tool_integrations.secret_reference IS 'Secret location: INTEGRATION_TOKEN_{uuid} for env, vault://path for Vault, aws://path for AWS';
COMMENT ON COLUMN platform.tool_integrations.secret_provider IS 'Secret provider: env, vault, aws_secrets, hardcoded';
COMMENT ON COLUMN platform.tool_integrations.api_token_unsafe IS 'INSECURE! Dev/test only. Must be NULL in production';
COMMENT ON COLUMN platform.tool_integrations.last_sync_status IS 'Last sync result: success, failed, partial';

-- ============================================================================
-- TABLE: projects
-- Purpose: Projects imported from external systems
-- Access: admin_service (RW), bi_layer (R), orchestrator (R)
-- Pattern: Denormalized owner_user_id for fast access without JOINs
-- ============================================================================

CREATE TABLE platform.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES platform.users(id) ON DELETE CASCADE,
    tool_integration_id UUID NOT NULL REFERENCES platform.tool_integrations(id) ON DELETE CASCADE,

    external_key TEXT NOT NULL,
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    external_url TEXT,

    is_active BOOLEAN NOT NULL DEFAULT true,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(tool_integration_id, external_id)
);

CREATE INDEX idx_projects_owner_user_id ON platform.projects(owner_user_id);
CREATE INDEX idx_projects_tool_integration_id ON platform.projects(tool_integration_id);
CREATE INDEX idx_projects_external_key ON platform.projects(external_key);
CREATE INDEX idx_projects_is_active ON platform.projects(is_active);
CREATE INDEX idx_projects_owner_active ON platform.projects(owner_user_id, is_active);

COMMENT ON TABLE platform.projects IS 'Projects from external systems: Jira projects, GitLab projects, Linear teams, etc.';
COMMENT ON COLUMN platform.projects.owner_user_id IS 'Project owner (denormalized from tool_integrations for fast access)';
COMMENT ON COLUMN platform.projects.external_key IS 'Project key in external system (e.g. PROJ, ENG)';
COMMENT ON COLUMN platform.projects.external_id IS 'Project ID in external system';
COMMENT ON COLUMN platform.projects.external_url IS 'Direct link to project in external system (may be NULL)';

-- ============================================================================
-- TABLE: project_access
-- Purpose: Granular project access control
-- Access: admin_service (RW), bi_layer (R)
-- Pattern: owner = full access, admin = configure metrics, viewer = read-only
-- ============================================================================

CREATE TABLE platform.project_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES platform.users(id) ON DELETE CASCADE,
    access_level platform.project_access_level NOT NULL,

    granted_by UUID REFERENCES platform.users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(project_id, user_id)
);

CREATE INDEX idx_project_access_project_id ON platform.project_access(project_id);
CREATE INDEX idx_project_access_user_id ON platform.project_access(user_id);
CREATE INDEX idx_project_access_level ON platform.project_access(access_level);
CREATE INDEX idx_project_access_user_level ON platform.project_access(user_id, access_level);

COMMENT ON TABLE platform.project_access IS 'Granular project permissions: owner, admin, viewer';
COMMENT ON COLUMN platform.project_access.access_level IS 'owner = full access, admin = configure metrics, viewer = read-only';
COMMENT ON COLUMN platform.project_access.granted_by IS 'User who granted access';

-- ============================================================================
-- TABLE: audit_log
-- Purpose: Audit trail of all user actions
-- Access: monitoring_service (RW), admin_service (R)
-- ============================================================================

CREATE TABLE platform.audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES platform.users(id) ON DELETE SET NULL,

    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,

    details JSONB,

    ip_address INET,
    user_agent TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_user_id ON platform.audit_log(user_id);
CREATE INDEX idx_audit_log_action ON platform.audit_log(action);
CREATE INDEX idx_audit_log_entity ON platform.audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_log_created_at ON platform.audit_log(created_at DESC);

COMMENT ON TABLE platform.audit_log IS 'User action audit trail for security and compliance';
COMMENT ON COLUMN platform.audit_log.action IS 'Action format: entity.action (e.g. user.created, project.access_granted)';
COMMENT ON COLUMN platform.audit_log.details IS 'Additional action details in JSON format';

-- ============================================================================
-- TABLE: pipelines
-- Purpose: Pipeline definitions for orchestration
-- Access: orchestrator (RW), monitoring_service (R)
-- ============================================================================

CREATE TABLE platform.pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    description TEXT,

    is_active BOOLEAN NOT NULL DEFAULT true,
    schedule_cron TEXT,

    prefect_flow_id TEXT,
    prefect_deployment_id TEXT,

    config JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipelines_name ON platform.pipelines(name);
CREATE INDEX idx_pipelines_is_active ON platform.pipelines(is_active);
CREATE INDEX idx_pipelines_prefect_flow_id ON platform.pipelines(prefect_flow_id);

COMMENT ON TABLE platform.pipelines IS 'Pipeline definitions for Prefect orchestration';
COMMENT ON COLUMN platform.pipelines.schedule_cron IS 'Execution schedule in cron format';
COMMENT ON COLUMN platform.pipelines.config IS 'Custom pipeline configuration in JSON format';
COMMENT ON COLUMN platform.pipelines.prefect_flow_id IS 'Prefect flow identifier';
COMMENT ON COLUMN platform.pipelines.prefect_deployment_id IS 'Prefect deployment identifier';

-- ============================================================================
-- TABLE: pipeline_runs
-- Purpose: Pipeline execution history
-- Access: orchestrator (RW), monitoring_service (R), bi_layer (R)
-- ============================================================================

CREATE TABLE platform.pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID NOT NULL REFERENCES platform.pipelines(id) ON DELETE CASCADE,
    project_id UUID REFERENCES platform.projects(id) ON DELETE SET NULL,

    status TEXT NOT NULL DEFAULT 'pending',

    prefect_flow_run_id TEXT,
    prefect_state JSONB,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,

    error_message TEXT,
    error_trace TEXT,

    metrics JSONB,
    config JSONB,

    triggered_by UUID REFERENCES platform.users(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_runs_pipeline_id ON platform.pipeline_runs(pipeline_id);
CREATE INDEX idx_pipeline_runs_project_id ON platform.pipeline_runs(project_id);
CREATE INDEX idx_pipeline_runs_status ON platform.pipeline_runs(status);
CREATE INDEX idx_pipeline_runs_created_at ON platform.pipeline_runs(created_at DESC);
CREATE INDEX idx_pipeline_runs_prefect_flow_run_id ON platform.pipeline_runs(prefect_flow_run_id);
CREATE INDEX idx_pipeline_runs_project_created ON platform.pipeline_runs(project_id, created_at DESC);

COMMENT ON TABLE platform.pipeline_runs IS 'Pipeline execution history with Prefect integration';
COMMENT ON COLUMN platform.pipeline_runs.status IS 'Execution status (format from Prefect)';
COMMENT ON COLUMN platform.pipeline_runs.prefect_state IS 'Full Prefect state in JSON format';
COMMENT ON COLUMN platform.pipeline_runs.metrics IS 'Execution metrics: rows processed, etc.';
COMMENT ON COLUMN platform.pipeline_runs.triggered_by IS 'User who triggered (NULL for scheduled runs)';
COMMENT ON COLUMN platform.pipeline_runs.prefect_flow_run_id IS 'Prefect flow run identifier';

-- ============================================================================
-- TABLE: pipeline_tasks
-- Purpose: Individual task execution within pipeline runs
-- Access: orchestrator (RW), monitoring_service (R)
-- ============================================================================

CREATE TABLE platform.pipeline_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID NOT NULL REFERENCES platform.pipeline_runs(id) ON DELETE CASCADE,

    task_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',

    prefect_task_run_id TEXT,
    prefect_state JSONB,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,

    error_message TEXT,
    error_trace TEXT,

    metrics JSONB,
    input_params JSONB,
    output_result JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_tasks_pipeline_run_id ON platform.pipeline_tasks(pipeline_run_id);
CREATE INDEX idx_pipeline_tasks_status ON platform.pipeline_tasks(status);
CREATE INDEX idx_pipeline_tasks_task_name ON platform.pipeline_tasks(task_name);
CREATE INDEX idx_pipeline_tasks_created_at ON platform.pipeline_tasks(created_at DESC);
CREATE INDEX idx_pipeline_tasks_prefect_task_run_id ON platform.pipeline_tasks(prefect_task_run_id);

COMMENT ON TABLE platform.pipeline_tasks IS 'Task execution history within pipeline runs';
COMMENT ON COLUMN platform.pipeline_tasks.status IS 'Task status (format from Prefect)';
COMMENT ON COLUMN platform.pipeline_tasks.prefect_state IS 'Full Prefect task state in JSON format';
COMMENT ON COLUMN platform.pipeline_tasks.input_params IS 'Task input parameters';
COMMENT ON COLUMN platform.pipeline_tasks.output_result IS 'Task execution result';
COMMENT ON COLUMN platform.pipeline_tasks.prefect_task_run_id IS 'Prefect task run identifier';

-- ============================================================================
-- END OF SCHEMA: platform
-- ============================================================================
