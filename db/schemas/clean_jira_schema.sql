--
-- PostgreSQL database dump
--


-- Dumped from database version 15.15
-- Dumped by pg_dump version 15.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: clean_jira; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA clean_jira;


--
-- Name: issue_hierarchy_level; Type: TYPE; Schema: clean_jira; Owner: -
--

CREATE TYPE clean_jira.issue_hierarchy_level AS ENUM (
    'epic',
    'story',
    'task',
    'subtask'
);


--
-- Name: issue_status_category; Type: TYPE; Schema: clean_jira; Owner: -
--

CREATE TYPE clean_jira.issue_status_category AS ENUM (
    'to_do',
    'in_progress',
    'done'
);


--
-- Name: release_status; Type: TYPE; Schema: clean_jira; Owner: -
--

CREATE TYPE clean_jira.release_status AS ENUM (
    'unreleased',
    'released',
    'archived'
);


--
-- Name: sprint_status; Type: TYPE; Schema: clean_jira; Owner: -
--

CREATE TYPE clean_jira.sprint_status AS ENUM (
    'future',
    'active',
    'closed'
);


--
-- Name: user_role_type; Type: TYPE; Schema: clean_jira; Owner: -
--

CREATE TYPE clean_jira.user_role_type AS ENUM (
    'assignee',
    'reporter',
    'creator',
    'watcher'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: board_column_statuses; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.board_column_statuses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    board_column_id uuid NOT NULL,
    status_id uuid NOT NULL
);


--
-- Name: TABLE board_column_statuses; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: board_columns; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.board_columns (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    board_id uuid NOT NULL,
    name text NOT NULL,
    "position" integer NOT NULL
);


--
-- Name: TABLE board_columns; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN board_columns."position"; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.board_columns."position" IS 'Display order of the column on the board';


--
-- Name: boards; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.boards (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE boards; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.boards IS 'Normalized Jira boards by project.';


--
-- Name: comment_issues; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.comment_issues (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    comment_id uuid NOT NULL,
    issue_id uuid NOT NULL
);


--
-- Name: TABLE comment_issues; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.comment_issues IS 'Bridge between comments and issues.';


--
-- Name: comments; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.comments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    body text NOT NULL,
    author_id uuid,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE comments; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.comments IS 'Normalized issue comments.';


--
-- Name: field_keys; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.field_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_key text NOT NULL,
    name text NOT NULL,
    is_custom boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE field_keys; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN field_keys.external_key; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: field_value_changelog; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.field_value_changelog (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    field_key_id uuid NOT NULL,
    old_value jsonb,
    new_value jsonb,
    changed_by_id uuid,
    changed_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE field_value_changelog; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.field_value_changelog IS 'History of field value changes by issue and field.';


--
-- Name: field_values; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.field_values (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    field_key_id uuid NOT NULL,
    json_value jsonb,
    value text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE field_values; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN field_values.json_value; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.field_values.json_value IS 'Json value.';


--
-- Name: COLUMN field_values.value; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: issue_comment_blockings; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_comment_blockings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    comment_id uuid NOT NULL,
    is_resolved boolean DEFAULT false NOT NULL,
    blocked_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone
);


--
-- Name: TABLE issue_comment_blockings; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.issue_comment_blockings IS 'Detected blocking references extracted from comments.';


--
-- Name: COLUMN issue_comment_blockings.is_resolved; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.issue_comment_blockings.is_resolved IS 'Boolean flag indicating whether resolved.';


--
-- Name: issue_labels; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_labels (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    label_id uuid NOT NULL
);


--
-- Name: issue_priorities; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_priorities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: issue_resolutions; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_resolutions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: issue_status_changelog; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_status_changelog (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    from_status_id uuid,
    to_status_id uuid NOT NULL,
    changed_by_id uuid,
    changed_at timestamp with time zone NOT NULL
);


--
-- Name: issue_statuses; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_statuses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    category clean_jira.issue_status_category NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE issue_statuses; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN issue_statuses.category; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: issue_types; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issue_types (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    hierarchy_level clean_jira.issue_hierarchy_level NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE issue_types; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN issue_types.hierarchy_level; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: issues; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.issues (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    external_key text NOT NULL,
    summary text NOT NULL,
    description text,
    type_id uuid NOT NULL,
    status_id uuid NOT NULL,
    parent_id uuid,
    jira_created_at timestamp with time zone NOT NULL,
    jira_updated_at timestamp with time zone NOT NULL,
    jira_resolved_at timestamp with time zone,
    db_created_at timestamp with time zone DEFAULT now() NOT NULL,
    db_updated_at timestamp with time zone DEFAULT now() NOT NULL,
    priority_id uuid,
    resolution_id uuid
);


--
-- Name: TABLE issues; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN issues.external_key; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN issues.parent_id; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.issues.parent_id IS 'Reference identifier for parent.';


--
-- Name: COLUMN issues.jira_created_at; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN issues.jira_updated_at; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN issues.jira_resolved_at; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: jira_user_issue_roles; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.jira_user_issue_roles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    role_type clean_jira.user_role_type NOT NULL,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE jira_user_issue_roles; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.jira_user_issue_roles IS 'Issue-role assignments for users (assignee, reporter, creator).';


--
-- Name: jira_users; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.jira_users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    display_name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE jira_users; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.jira_users IS 'Normalized Jira users participating in project activity.';


--
-- Name: COLUMN jira_users.external_id; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.jira_users.external_id IS 'Reference identifier for external.';


--
-- Name: labels; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.labels (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: projects; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    platform_project_id uuid NOT NULL,
    external_id text NOT NULL,
    external_key text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE projects; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN projects.external_id; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN projects.external_key; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: relation_issue_issues; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.relation_issue_issues (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    relation_type_id uuid NOT NULL,
    source_issue_id uuid NOT NULL,
    target_issue_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE relation_issue_issues; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.relation_issue_issues IS 'Directed links between source and target issues.';


--
-- Name: COLUMN relation_issue_issues.source_issue_id; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.relation_issue_issues.source_issue_id IS 'Reference identifier for source issue.';


--
-- Name: COLUMN relation_issue_issues.target_issue_id; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.relation_issue_issues.target_issue_id IS 'Reference identifier for target issue.';


--
-- Name: relation_issue_types; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.relation_issue_types (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL
);


--
-- Name: TABLE relation_issue_types; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.relation_issue_types IS 'Catalog of issue link types (blocks, relates, duplicates).';


--
-- Name: release_changelog; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.release_changelog (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    release_id uuid NOT NULL,
    field_name text NOT NULL,
    old_value text,
    new_value text,
    changed_by_id uuid,
    changed_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE release_changelog; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.release_changelog IS 'History of release property changes.';


--
-- Name: COLUMN release_changelog.field_name; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.release_changelog.field_name IS 'Field name.';


--
-- Name: release_issues; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.release_issues (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    release_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: TABLE release_issues; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN release_issues.is_active; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.release_issues.is_active IS 'Boolean flag indicating whether active.';


--
-- Name: release_issues_changelog; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.release_issues_changelog (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    release_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    action text NOT NULL,
    changed_by_id uuid,
    changed_at timestamp with time zone NOT NULL,
    CONSTRAINT release_issues_changelog_action_check CHECK ((action = ANY (ARRAY['added'::text, 'removed'::text])))
);


--
-- Name: TABLE release_issues_changelog; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.release_issues_changelog IS 'Historical issue-to-release membership changes.';


--
-- Name: releases; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.releases (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    description text,
    status clean_jira.release_status NOT NULL,
    start_date date,
    release_date date,
    is_archived boolean DEFAULT false NOT NULL,
    is_released boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE releases; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN releases.is_archived; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.releases.is_archived IS 'Boolean flag indicating whether archived.';


--
-- Name: COLUMN releases.is_released; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.releases.is_released IS 'Boolean flag indicating whether released.';


--
-- Name: sprint_changelog; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.sprint_changelog (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sprint_id uuid NOT NULL,
    field_name text NOT NULL,
    old_value text,
    new_value text,
    changed_by_id uuid,
    changed_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE sprint_changelog; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.sprint_changelog IS 'History of sprint property changes.';


--
-- Name: COLUMN sprint_changelog.field_name; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.sprint_changelog.field_name IS 'Field name.';


--
-- Name: sprint_issues; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.sprint_issues (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sprint_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: TABLE sprint_issues; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN sprint_issues.is_active; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: sprint_issues_changelog; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.sprint_issues_changelog (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    sprint_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    action text NOT NULL,
    changed_by_id uuid,
    changed_at timestamp with time zone NOT NULL,
    CONSTRAINT sprint_issues_changelog_action_check CHECK ((action = ANY (ARRAY['added'::text, 'removed'::text])))
);


--
-- Name: TABLE sprint_issues_changelog; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON TABLE clean_jira.sprint_issues_changelog IS 'Historical issue-to-sprint membership changes.';


--
-- Name: sprints; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.sprints (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    goal text,
    status clean_jira.sprint_status NOT NULL,
    start_date timestamp with time zone,
    end_date timestamp with time zone,
    complete_date timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE sprints; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: COLUMN sprints.goal; Type: COMMENT; Schema: clean_jira; Owner: -
--

COMMENT ON COLUMN clean_jira.sprints.goal IS 'Goal.';


--
-- Name: COLUMN sprints.complete_date; Type: COMMENT; Schema: clean_jira; Owner: -
--



--
-- Name: v_unique_users; Type: VIEW; Schema: clean_jira; Owner: -
--

CREATE VIEW clean_jira.v_unique_users AS
 SELECT DISTINCT ON (jira_users.external_id) jira_users.id,
    jira_users.project_id,
    jira_users.external_id,
    jira_users.display_name,
    jira_users.created_at,
    jira_users.updated_at
   FROM clean_jira.jira_users
  ORDER BY jira_users.external_id, jira_users.updated_at DESC;


--
-- Name: worklogs; Type: TABLE; Schema: clean_jira; Owner: -
--

CREATE TABLE clean_jira.worklogs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    issue_id uuid NOT NULL,
    external_id text NOT NULL,
    author_id uuid,
    time_spent_seconds integer NOT NULL,
    started_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: board_column_statuses board_column_statuses_board_column_id_status_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_column_statuses
    ADD CONSTRAINT board_column_statuses_board_column_id_status_id_key UNIQUE (board_column_id, status_id);


--
-- Name: board_column_statuses board_column_statuses_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_column_statuses
    ADD CONSTRAINT board_column_statuses_pkey PRIMARY KEY (id);


--
-- Name: board_columns board_columns_board_id_name_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_columns
    ADD CONSTRAINT board_columns_board_id_name_key UNIQUE (board_id, name);


--
-- Name: board_columns board_columns_board_id_position_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_columns
    ADD CONSTRAINT board_columns_board_id_position_key UNIQUE (board_id, "position");


--
-- Name: board_columns board_columns_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_columns
    ADD CONSTRAINT board_columns_pkey PRIMARY KEY (id);


--
-- Name: boards boards_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.boards
    ADD CONSTRAINT boards_pkey PRIMARY KEY (id);


--
-- Name: boards boards_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.boards
    ADD CONSTRAINT boards_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: comment_issues comment_issues_comment_id_issue_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comment_issues
    ADD CONSTRAINT comment_issues_comment_id_issue_id_key UNIQUE (comment_id, issue_id);


--
-- Name: comment_issues comment_issues_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comment_issues
    ADD CONSTRAINT comment_issues_pkey PRIMARY KEY (id);


--
-- Name: comments comments_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comments
    ADD CONSTRAINT comments_pkey PRIMARY KEY (id);


--
-- Name: comments comments_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comments
    ADD CONSTRAINT comments_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: field_keys field_keys_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_keys
    ADD CONSTRAINT field_keys_pkey PRIMARY KEY (id);


--
-- Name: field_keys field_keys_project_id_external_key_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_keys
    ADD CONSTRAINT field_keys_project_id_external_key_key UNIQUE (project_id, external_key);


--
-- Name: field_value_changelog field_value_changelog_issue_id_field_key_id_changed_at_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_value_changelog
    ADD CONSTRAINT field_value_changelog_issue_id_field_key_id_changed_at_key UNIQUE (issue_id, field_key_id, changed_at);


--
-- Name: field_value_changelog field_value_changelog_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_value_changelog
    ADD CONSTRAINT field_value_changelog_pkey PRIMARY KEY (id);


--
-- Name: field_values field_values_issue_id_field_key_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_values
    ADD CONSTRAINT field_values_issue_id_field_key_id_key UNIQUE (issue_id, field_key_id);


--
-- Name: field_values field_values_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_values
    ADD CONSTRAINT field_values_pkey PRIMARY KEY (id);


--
-- Name: issue_comment_blockings issue_comment_blockings_issue_id_comment_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_comment_blockings
    ADD CONSTRAINT issue_comment_blockings_issue_id_comment_id_key UNIQUE (issue_id, comment_id);


--
-- Name: issue_comment_blockings issue_comment_blockings_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_comment_blockings
    ADD CONSTRAINT issue_comment_blockings_pkey PRIMARY KEY (id);


--
-- Name: issue_labels issue_labels_issue_id_label_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_labels
    ADD CONSTRAINT issue_labels_issue_id_label_id_key UNIQUE (issue_id, label_id);


--
-- Name: issue_labels issue_labels_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_labels
    ADD CONSTRAINT issue_labels_pkey PRIMARY KEY (id);


--
-- Name: issue_priorities issue_priorities_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_priorities
    ADD CONSTRAINT issue_priorities_pkey PRIMARY KEY (id);


--
-- Name: issue_priorities issue_priorities_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_priorities
    ADD CONSTRAINT issue_priorities_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: issue_priorities issue_priorities_project_id_name_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_priorities
    ADD CONSTRAINT issue_priorities_project_id_name_key UNIQUE (project_id, name);


--
-- Name: issue_resolutions issue_resolutions_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_resolutions
    ADD CONSTRAINT issue_resolutions_pkey PRIMARY KEY (id);


--
-- Name: issue_resolutions issue_resolutions_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_resolutions
    ADD CONSTRAINT issue_resolutions_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: issue_resolutions issue_resolutions_project_id_name_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_resolutions
    ADD CONSTRAINT issue_resolutions_project_id_name_key UNIQUE (project_id, name);


--
-- Name: issue_status_changelog issue_status_changelog_issue_id_to_status_id_changed_at_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_status_changelog
    ADD CONSTRAINT issue_status_changelog_issue_id_to_status_id_changed_at_key UNIQUE (issue_id, to_status_id, changed_at);


--
-- Name: issue_status_changelog issue_status_changelog_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_status_changelog
    ADD CONSTRAINT issue_status_changelog_pkey PRIMARY KEY (id);


--
-- Name: issue_statuses issue_statuses_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_statuses
    ADD CONSTRAINT issue_statuses_pkey PRIMARY KEY (id);


--
-- Name: issue_statuses issue_statuses_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_statuses
    ADD CONSTRAINT issue_statuses_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: issue_statuses issue_statuses_project_id_name_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_statuses
    ADD CONSTRAINT issue_statuses_project_id_name_key UNIQUE (project_id, name);


--
-- Name: issue_types issue_types_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_types
    ADD CONSTRAINT issue_types_pkey PRIMARY KEY (id);


--
-- Name: issue_types issue_types_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_types
    ADD CONSTRAINT issue_types_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: issue_types issue_types_project_id_name_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_types
    ADD CONSTRAINT issue_types_project_id_name_key UNIQUE (project_id, name);


--
-- Name: issues issues_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_pkey PRIMARY KEY (id);


--
-- Name: issues issues_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: issues issues_project_id_external_key_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_project_id_external_key_key UNIQUE (project_id, external_key);


--
-- Name: jira_user_issue_roles jira_user_issue_roles_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_user_issue_roles
    ADD CONSTRAINT jira_user_issue_roles_pkey PRIMARY KEY (id);


--
-- Name: jira_user_issue_roles jira_user_issue_roles_user_id_issue_id_role_type_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_user_issue_roles
    ADD CONSTRAINT jira_user_issue_roles_user_id_issue_id_role_type_key UNIQUE (user_id, issue_id, role_type);


--
-- Name: jira_users jira_users_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_users
    ADD CONSTRAINT jira_users_pkey PRIMARY KEY (id);


--
-- Name: jira_users jira_users_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_users
    ADD CONSTRAINT jira_users_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: labels labels_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.labels
    ADD CONSTRAINT labels_pkey PRIMARY KEY (id);


--
-- Name: labels labels_project_id_name_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.labels
    ADD CONSTRAINT labels_project_id_name_key UNIQUE (project_id, name);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: projects projects_platform_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.projects
    ADD CONSTRAINT projects_platform_project_id_external_id_key UNIQUE (platform_project_id, external_id);


--
-- Name: projects projects_platform_project_id_external_key_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.projects
    ADD CONSTRAINT projects_platform_project_id_external_key_key UNIQUE (platform_project_id, external_key);


--
-- Name: relation_issue_issues relation_issue_issues_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_issues
    ADD CONSTRAINT relation_issue_issues_pkey PRIMARY KEY (id);


--
-- Name: relation_issue_issues relation_issue_issues_relation_type_id_source_issue_id_targ_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_issues
    ADD CONSTRAINT relation_issue_issues_relation_type_id_source_issue_id_targ_key UNIQUE (relation_type_id, source_issue_id, target_issue_id);


--
-- Name: relation_issue_types relation_issue_types_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_types
    ADD CONSTRAINT relation_issue_types_pkey PRIMARY KEY (id);


--
-- Name: relation_issue_types relation_issue_types_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_types
    ADD CONSTRAINT relation_issue_types_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: release_changelog release_changelog_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_changelog
    ADD CONSTRAINT release_changelog_pkey PRIMARY KEY (id);


--
-- Name: release_issues_changelog release_issues_changelog_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues_changelog
    ADD CONSTRAINT release_issues_changelog_pkey PRIMARY KEY (id);


--
-- Name: release_issues_changelog release_issues_changelog_release_id_issue_id_action_changed_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues_changelog
    ADD CONSTRAINT release_issues_changelog_release_id_issue_id_action_changed_key UNIQUE (release_id, issue_id, action, changed_at);


--
-- Name: release_issues release_issues_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues
    ADD CONSTRAINT release_issues_pkey PRIMARY KEY (id);


--
-- Name: release_issues release_issues_release_id_issue_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues
    ADD CONSTRAINT release_issues_release_id_issue_id_key UNIQUE (release_id, issue_id);


--
-- Name: releases releases_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.releases
    ADD CONSTRAINT releases_pkey PRIMARY KEY (id);


--
-- Name: releases releases_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.releases
    ADD CONSTRAINT releases_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: sprint_changelog sprint_changelog_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_changelog
    ADD CONSTRAINT sprint_changelog_pkey PRIMARY KEY (id);


--
-- Name: sprint_issues_changelog sprint_issues_changelog_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues_changelog
    ADD CONSTRAINT sprint_issues_changelog_pkey PRIMARY KEY (id);


--
-- Name: sprint_issues_changelog sprint_issues_changelog_sprint_id_issue_id_action_changed_a_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues_changelog
    ADD CONSTRAINT sprint_issues_changelog_sprint_id_issue_id_action_changed_a_key UNIQUE (sprint_id, issue_id, action, changed_at);


--
-- Name: sprint_issues sprint_issues_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues
    ADD CONSTRAINT sprint_issues_pkey PRIMARY KEY (id);


--
-- Name: sprint_issues sprint_issues_sprint_id_issue_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues
    ADD CONSTRAINT sprint_issues_sprint_id_issue_id_key UNIQUE (sprint_id, issue_id);


--
-- Name: sprints sprints_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprints
    ADD CONSTRAINT sprints_pkey PRIMARY KEY (id);


--
-- Name: sprints sprints_project_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprints
    ADD CONSTRAINT sprints_project_id_external_id_key UNIQUE (project_id, external_id);


--
-- Name: worklogs worklogs_issue_id_external_id_key; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.worklogs
    ADD CONSTRAINT worklogs_issue_id_external_id_key UNIQUE (issue_id, external_id);


--
-- Name: worklogs worklogs_pkey; Type: CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.worklogs
    ADD CONSTRAINT worklogs_pkey PRIMARY KEY (id);


--
-- Name: idx_cj_board_columns_board; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_board_columns_board ON clean_jira.board_columns USING btree (board_id);


--
-- Name: idx_cj_board_columns_position; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_board_columns_position ON clean_jira.board_columns USING btree (board_id, "position");


--
-- Name: idx_cj_boards_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_boards_project ON clean_jira.boards USING btree (project_id);


--
-- Name: idx_cj_comment_issues_comment; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_comment_issues_comment ON clean_jira.comment_issues USING btree (comment_id);


--
-- Name: idx_cj_comment_issues_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_comment_issues_issue ON clean_jira.comment_issues USING btree (issue_id);


--
-- Name: idx_cj_comments_author; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_comments_author ON clean_jira.comments USING btree (author_id);


--
-- Name: idx_cj_comments_created; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_comments_created ON clean_jira.comments USING btree (created_at);


--
-- Name: idx_cj_comments_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_comments_project ON clean_jira.comments USING btree (project_id);


--
-- Name: idx_cj_field_keys_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_keys_project ON clean_jira.field_keys USING btree (project_id);


--
-- Name: idx_cj_field_value_changelog_changed; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_value_changelog_changed ON clean_jira.field_value_changelog USING btree (changed_at);


--
-- Name: idx_cj_field_value_changelog_field_key; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_value_changelog_field_key ON clean_jira.field_value_changelog USING btree (field_key_id);


--
-- Name: idx_cj_field_value_changelog_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_value_changelog_issue ON clean_jira.field_value_changelog USING btree (issue_id);


--
-- Name: idx_cj_field_values_field_key; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_values_field_key ON clean_jira.field_values USING btree (field_key_id);


--
-- Name: idx_cj_field_values_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_values_issue ON clean_jira.field_values USING btree (issue_id);


--
-- Name: idx_cj_field_values_value; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_field_values_value ON clean_jira.field_values USING btree (value);


--
-- Name: idx_cj_isc_changed; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_isc_changed ON clean_jira.issue_status_changelog USING btree (changed_at);


--
-- Name: idx_cj_isc_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_isc_issue ON clean_jira.issue_status_changelog USING btree (issue_id);


--
-- Name: idx_cj_isc_to_status; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_isc_to_status ON clean_jira.issue_status_changelog USING btree (to_status_id);


--
-- Name: idx_cj_issue_comment_blockings_comment; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_comment_blockings_comment ON clean_jira.issue_comment_blockings USING btree (comment_id);


--
-- Name: idx_cj_issue_comment_blockings_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_comment_blockings_issue ON clean_jira.issue_comment_blockings USING btree (issue_id);


--
-- Name: idx_cj_issue_comment_blockings_resolved; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_comment_blockings_resolved ON clean_jira.issue_comment_blockings USING btree (is_resolved);


--
-- Name: idx_cj_issue_labels_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_labels_issue ON clean_jira.issue_labels USING btree (issue_id);


--
-- Name: idx_cj_issue_labels_label; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_labels_label ON clean_jira.issue_labels USING btree (label_id);


--
-- Name: idx_cj_issue_priorities_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_priorities_project ON clean_jira.issue_priorities USING btree (project_id);


--
-- Name: idx_cj_issue_resolutions_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_resolutions_project ON clean_jira.issue_resolutions USING btree (project_id);


--
-- Name: idx_cj_issue_statuses_category; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_statuses_category ON clean_jira.issue_statuses USING btree (category);


--
-- Name: idx_cj_issue_statuses_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_statuses_project ON clean_jira.issue_statuses USING btree (project_id);


--
-- Name: idx_cj_issue_types_hierarchy; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_types_hierarchy ON clean_jira.issue_types USING btree (hierarchy_level);


--
-- Name: idx_cj_issue_types_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issue_types_project ON clean_jira.issue_types USING btree (project_id);


--
-- Name: idx_cj_issues_ext_id; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_ext_id ON clean_jira.issues USING btree (external_id);


--
-- Name: idx_cj_issues_jira_created; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_jira_created ON clean_jira.issues USING btree (jira_created_at);


--
-- Name: idx_cj_issues_jira_resolved; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_jira_resolved ON clean_jira.issues USING btree (jira_resolved_at) WHERE (jira_resolved_at IS NOT NULL);


--
-- Name: idx_cj_issues_jira_updated; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_jira_updated ON clean_jira.issues USING btree (jira_updated_at);


--
-- Name: idx_cj_issues_parent; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_parent ON clean_jira.issues USING btree (parent_id);


--
-- Name: idx_cj_issues_priority; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_priority ON clean_jira.issues USING btree (priority_id);


--
-- Name: idx_cj_issues_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_project ON clean_jira.issues USING btree (project_id);


--
-- Name: idx_cj_issues_resolution; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_resolution ON clean_jira.issues USING btree (resolution_id);


--
-- Name: idx_cj_issues_status; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_status ON clean_jira.issues USING btree (status_id);


--
-- Name: idx_cj_issues_type; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_issues_type ON clean_jira.issues USING btree (type_id);


--
-- Name: idx_cj_jira_users_ext_id; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_jira_users_ext_id ON clean_jira.jira_users USING btree (external_id);


--
-- Name: idx_cj_jira_users_external; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_jira_users_external ON clean_jira.jira_users USING btree (project_id, external_id);


--
-- Name: idx_cj_jira_users_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_jira_users_project ON clean_jira.jira_users USING btree (project_id);


--
-- Name: idx_cj_labels_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_labels_project ON clean_jira.labels USING btree (project_id);


--
-- Name: idx_cj_projects_external_key; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_projects_external_key ON clean_jira.projects USING btree (platform_project_id, external_key);


--
-- Name: idx_cj_projects_platform_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_projects_platform_project ON clean_jira.projects USING btree (platform_project_id);


--
-- Name: idx_cj_relation_issue_issues_source; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_relation_issue_issues_source ON clean_jira.relation_issue_issues USING btree (source_issue_id);


--
-- Name: idx_cj_relation_issue_issues_target; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_relation_issue_issues_target ON clean_jira.relation_issue_issues USING btree (target_issue_id);


--
-- Name: idx_cj_relation_issue_issues_type; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_relation_issue_issues_type ON clean_jira.relation_issue_issues USING btree (relation_type_id);


--
-- Name: idx_cj_relation_issue_types_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_relation_issue_types_project ON clean_jira.relation_issue_types USING btree (project_id);


--
-- Name: idx_cj_release_issues_active; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_release_issues_active ON clean_jira.release_issues USING btree (is_active);


--
-- Name: idx_cj_release_issues_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_release_issues_issue ON clean_jira.release_issues USING btree (issue_id);


--
-- Name: idx_cj_release_issues_release; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_release_issues_release ON clean_jira.release_issues USING btree (release_id);


--
-- Name: idx_cj_releases_dates; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_releases_dates ON clean_jira.releases USING btree (start_date, release_date);


--
-- Name: idx_cj_releases_ext_id; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_releases_ext_id ON clean_jira.releases USING btree (external_id);


--
-- Name: idx_cj_releases_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_releases_project ON clean_jira.releases USING btree (project_id);


--
-- Name: idx_cj_releases_status; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_releases_status ON clean_jira.releases USING btree (status);


--
-- Name: idx_cj_sprint_changelog_sprint_id_field; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_changelog_sprint_id_field ON clean_jira.sprint_changelog USING btree (sprint_id, field_name, changed_at DESC);


--
-- Name: idx_cj_sprint_issues_active; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_issues_active ON clean_jira.sprint_issues USING btree (is_active);


--
-- Name: idx_cj_sprint_issues_changelog_changed; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_issues_changelog_changed ON clean_jira.sprint_issues_changelog USING btree (changed_at);


--
-- Name: idx_cj_sprint_issues_changelog_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_issues_changelog_issue ON clean_jira.sprint_issues_changelog USING btree (issue_id);


--
-- Name: idx_cj_sprint_issues_changelog_sprint; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_issues_changelog_sprint ON clean_jira.sprint_issues_changelog USING btree (sprint_id);


--
-- Name: idx_cj_sprint_issues_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_issues_issue ON clean_jira.sprint_issues USING btree (issue_id);


--
-- Name: idx_cj_sprint_issues_sprint; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprint_issues_sprint ON clean_jira.sprint_issues USING btree (sprint_id);


--
-- Name: idx_cj_sprints_dates; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprints_dates ON clean_jira.sprints USING btree (start_date, end_date);


--
-- Name: idx_cj_sprints_ext_id; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprints_ext_id ON clean_jira.sprints USING btree (external_id);


--
-- Name: idx_cj_sprints_project; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprints_project ON clean_jira.sprints USING btree (project_id);


--
-- Name: idx_cj_sprints_status; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_sprints_status ON clean_jira.sprints USING btree (status);


--
-- Name: idx_cj_user_roles_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_user_roles_issue ON clean_jira.jira_user_issue_roles USING btree (issue_id);


--
-- Name: idx_cj_user_roles_type; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_user_roles_type ON clean_jira.jira_user_issue_roles USING btree (role_type);


--
-- Name: idx_cj_user_roles_user; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_user_roles_user ON clean_jira.jira_user_issue_roles USING btree (user_id);


--
-- Name: idx_cj_worklogs_author; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_worklogs_author ON clean_jira.worklogs USING btree (author_id);


--
-- Name: idx_cj_worklogs_issue; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_worklogs_issue ON clean_jira.worklogs USING btree (issue_id);


--
-- Name: idx_cj_worklogs_started; Type: INDEX; Schema: clean_jira; Owner: -
--

CREATE INDEX idx_cj_worklogs_started ON clean_jira.worklogs USING btree (started_at);


--
-- Name: board_column_statuses board_column_statuses_board_column_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_column_statuses
    ADD CONSTRAINT board_column_statuses_board_column_id_fkey FOREIGN KEY (board_column_id) REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE;


--
-- Name: board_column_statuses board_column_statuses_status_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_column_statuses
    ADD CONSTRAINT board_column_statuses_status_id_fkey FOREIGN KEY (status_id) REFERENCES clean_jira.issue_statuses(id) ON DELETE CASCADE;


--
-- Name: board_columns board_columns_board_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.board_columns
    ADD CONSTRAINT board_columns_board_id_fkey FOREIGN KEY (board_id) REFERENCES clean_jira.boards(id) ON DELETE CASCADE;


--
-- Name: boards boards_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.boards
    ADD CONSTRAINT boards_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: comment_issues comment_issues_comment_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comment_issues
    ADD CONSTRAINT comment_issues_comment_id_fkey FOREIGN KEY (comment_id) REFERENCES clean_jira.comments(id) ON DELETE CASCADE;


--
-- Name: comment_issues comment_issues_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comment_issues
    ADD CONSTRAINT comment_issues_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: comments comments_author_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comments
    ADD CONSTRAINT comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: comments comments_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.comments
    ADD CONSTRAINT comments_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: field_keys field_keys_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_keys
    ADD CONSTRAINT field_keys_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: field_value_changelog field_value_changelog_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_value_changelog
    ADD CONSTRAINT field_value_changelog_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: field_value_changelog field_value_changelog_field_key_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_value_changelog
    ADD CONSTRAINT field_value_changelog_field_key_id_fkey FOREIGN KEY (field_key_id) REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE;


--
-- Name: field_value_changelog field_value_changelog_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_value_changelog
    ADD CONSTRAINT field_value_changelog_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: field_values field_values_field_key_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_values
    ADD CONSTRAINT field_values_field_key_id_fkey FOREIGN KEY (field_key_id) REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE;


--
-- Name: field_values field_values_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.field_values
    ADD CONSTRAINT field_values_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: issue_comment_blockings issue_comment_blockings_comment_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_comment_blockings
    ADD CONSTRAINT issue_comment_blockings_comment_id_fkey FOREIGN KEY (comment_id) REFERENCES clean_jira.comments(id) ON DELETE CASCADE;


--
-- Name: issue_comment_blockings issue_comment_blockings_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_comment_blockings
    ADD CONSTRAINT issue_comment_blockings_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: issue_labels issue_labels_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_labels
    ADD CONSTRAINT issue_labels_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: issue_labels issue_labels_label_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_labels
    ADD CONSTRAINT issue_labels_label_id_fkey FOREIGN KEY (label_id) REFERENCES clean_jira.labels(id) ON DELETE CASCADE;


--
-- Name: issue_priorities issue_priorities_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_priorities
    ADD CONSTRAINT issue_priorities_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: issue_resolutions issue_resolutions_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_resolutions
    ADD CONSTRAINT issue_resolutions_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: issue_status_changelog issue_status_changelog_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_status_changelog
    ADD CONSTRAINT issue_status_changelog_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: issue_status_changelog issue_status_changelog_from_status_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_status_changelog
    ADD CONSTRAINT issue_status_changelog_from_status_id_fkey FOREIGN KEY (from_status_id) REFERENCES clean_jira.issue_statuses(id);


--
-- Name: issue_status_changelog issue_status_changelog_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_status_changelog
    ADD CONSTRAINT issue_status_changelog_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: issue_status_changelog issue_status_changelog_to_status_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_status_changelog
    ADD CONSTRAINT issue_status_changelog_to_status_id_fkey FOREIGN KEY (to_status_id) REFERENCES clean_jira.issue_statuses(id);


--
-- Name: issue_statuses issue_statuses_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_statuses
    ADD CONSTRAINT issue_statuses_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: issue_types issue_types_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issue_types
    ADD CONSTRAINT issue_types_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: issues issues_parent_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES clean_jira.issues(id);


--
-- Name: issues issues_priority_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_priority_id_fkey FOREIGN KEY (priority_id) REFERENCES clean_jira.issue_priorities(id);


--
-- Name: issues issues_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: issues issues_resolution_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_resolution_id_fkey FOREIGN KEY (resolution_id) REFERENCES clean_jira.issue_resolutions(id);


--
-- Name: issues issues_status_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_status_id_fkey FOREIGN KEY (status_id) REFERENCES clean_jira.issue_statuses(id);


--
-- Name: issues issues_type_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.issues
    ADD CONSTRAINT issues_type_id_fkey FOREIGN KEY (type_id) REFERENCES clean_jira.issue_types(id);


--
-- Name: jira_user_issue_roles jira_user_issue_roles_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_user_issue_roles
    ADD CONSTRAINT jira_user_issue_roles_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: jira_user_issue_roles jira_user_issue_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_user_issue_roles
    ADD CONSTRAINT jira_user_issue_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES clean_jira.jira_users(id) ON DELETE CASCADE;


--
-- Name: jira_users jira_users_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.jira_users
    ADD CONSTRAINT jira_users_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: labels labels_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.labels
    ADD CONSTRAINT labels_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: projects projects_platform_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.projects
    ADD CONSTRAINT projects_platform_project_id_fkey FOREIGN KEY (platform_project_id) REFERENCES platform.projects(id) ON DELETE CASCADE;


--
-- Name: relation_issue_issues relation_issue_issues_relation_type_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_issues
    ADD CONSTRAINT relation_issue_issues_relation_type_id_fkey FOREIGN KEY (relation_type_id) REFERENCES clean_jira.relation_issue_types(id) ON DELETE CASCADE;


--
-- Name: relation_issue_issues relation_issue_issues_source_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_issues
    ADD CONSTRAINT relation_issue_issues_source_issue_id_fkey FOREIGN KEY (source_issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: relation_issue_issues relation_issue_issues_target_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_issues
    ADD CONSTRAINT relation_issue_issues_target_issue_id_fkey FOREIGN KEY (target_issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: relation_issue_types relation_issue_types_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.relation_issue_types
    ADD CONSTRAINT relation_issue_types_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: release_changelog release_changelog_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_changelog
    ADD CONSTRAINT release_changelog_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: release_changelog release_changelog_release_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_changelog
    ADD CONSTRAINT release_changelog_release_id_fkey FOREIGN KEY (release_id) REFERENCES clean_jira.releases(id) ON DELETE CASCADE;


--
-- Name: release_issues_changelog release_issues_changelog_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues_changelog
    ADD CONSTRAINT release_issues_changelog_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: release_issues_changelog release_issues_changelog_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues_changelog
    ADD CONSTRAINT release_issues_changelog_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: release_issues_changelog release_issues_changelog_release_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues_changelog
    ADD CONSTRAINT release_issues_changelog_release_id_fkey FOREIGN KEY (release_id) REFERENCES clean_jira.releases(id) ON DELETE CASCADE;


--
-- Name: release_issues release_issues_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues
    ADD CONSTRAINT release_issues_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: release_issues release_issues_release_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.release_issues
    ADD CONSTRAINT release_issues_release_id_fkey FOREIGN KEY (release_id) REFERENCES clean_jira.releases(id) ON DELETE CASCADE;


--
-- Name: releases releases_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.releases
    ADD CONSTRAINT releases_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: sprint_changelog sprint_changelog_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_changelog
    ADD CONSTRAINT sprint_changelog_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: sprint_changelog sprint_changelog_sprint_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_changelog
    ADD CONSTRAINT sprint_changelog_sprint_id_fkey FOREIGN KEY (sprint_id) REFERENCES clean_jira.sprints(id) ON DELETE CASCADE;


--
-- Name: sprint_issues_changelog sprint_issues_changelog_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues_changelog
    ADD CONSTRAINT sprint_issues_changelog_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: sprint_issues_changelog sprint_issues_changelog_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues_changelog
    ADD CONSTRAINT sprint_issues_changelog_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: sprint_issues_changelog sprint_issues_changelog_sprint_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues_changelog
    ADD CONSTRAINT sprint_issues_changelog_sprint_id_fkey FOREIGN KEY (sprint_id) REFERENCES clean_jira.sprints(id) ON DELETE CASCADE;


--
-- Name: sprint_issues sprint_issues_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues
    ADD CONSTRAINT sprint_issues_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- Name: sprint_issues sprint_issues_sprint_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprint_issues
    ADD CONSTRAINT sprint_issues_sprint_id_fkey FOREIGN KEY (sprint_id) REFERENCES clean_jira.sprints(id) ON DELETE CASCADE;


--
-- Name: sprints sprints_project_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.sprints
    ADD CONSTRAINT sprints_project_id_fkey FOREIGN KEY (project_id) REFERENCES clean_jira.projects(id) ON DELETE CASCADE;


--
-- Name: worklogs worklogs_author_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.worklogs
    ADD CONSTRAINT worklogs_author_id_fkey FOREIGN KEY (author_id) REFERENCES clean_jira.jira_users(id);


--
-- Name: worklogs worklogs_issue_id_fkey; Type: FK CONSTRAINT; Schema: clean_jira; Owner: -
--

ALTER TABLE ONLY clean_jira.worklogs
    ADD CONSTRAINT worklogs_issue_id_fkey FOREIGN KEY (issue_id) REFERENCES clean_jira.issues(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


-- Auto-generated baseline comments for missing objects
COMMENT ON COLUMN clean_jira.board_column_statuses.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.board_column_statuses.board_column_id IS 'Reference identifier for board column.';
COMMENT ON COLUMN clean_jira.board_column_statuses.status_id IS 'Reference identifier for status.';
COMMENT ON COLUMN clean_jira.board_columns.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.board_columns.board_id IS 'Reference identifier for board.';
COMMENT ON COLUMN clean_jira.board_columns.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.boards.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.boards.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.boards.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.boards.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.boards.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.comment_issues.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.comment_issues.comment_id IS 'Reference identifier for comment.';
COMMENT ON COLUMN clean_jira.comment_issues.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.comments.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.comments.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.comments.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.comments.body IS 'Body.';
COMMENT ON COLUMN clean_jira.comments.author_id IS 'Reference identifier for author.';
COMMENT ON COLUMN clean_jira.comments.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.comments.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN clean_jira.field_keys.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.field_keys.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.field_keys.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.field_keys.is_custom IS 'Boolean flag indicating whether custom.';
COMMENT ON COLUMN clean_jira.field_keys.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.field_value_changelog.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.field_value_changelog.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.field_value_changelog.field_key_id IS 'Reference identifier for field key.';
COMMENT ON COLUMN clean_jira.field_value_changelog.old_value IS 'Old value.';
COMMENT ON COLUMN clean_jira.field_value_changelog.new_value IS 'New value.';
COMMENT ON COLUMN clean_jira.field_value_changelog.changed_by_id IS 'Reference identifier for changed by.';
COMMENT ON COLUMN clean_jira.field_value_changelog.changed_at IS 'Timestamp/date value for changed at.';
COMMENT ON COLUMN clean_jira.field_values.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.field_values.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.field_values.field_key_id IS 'Reference identifier for field key.';
COMMENT ON COLUMN clean_jira.field_values.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN clean_jira.issue_comment_blockings.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_comment_blockings.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.issue_comment_blockings.comment_id IS 'Reference identifier for comment.';
COMMENT ON COLUMN clean_jira.issue_comment_blockings.blocked_at IS 'Timestamp/date value for blocked at.';
COMMENT ON COLUMN clean_jira.issue_comment_blockings.resolved_at IS 'Timestamp/date value for resolved at.';
COMMENT ON TABLE clean_jira.issue_labels IS 'Issue-to-label bridge table.';
COMMENT ON COLUMN clean_jira.issue_labels.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_labels.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.issue_labels.label_id IS 'Reference identifier for label.';
COMMENT ON TABLE clean_jira.issue_priorities IS 'Normalized catalog of Jira priorities per project.';
COMMENT ON COLUMN clean_jira.issue_priorities.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_priorities.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.issue_priorities.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.issue_priorities.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issue_priorities.created_at IS 'Row creation timestamp.';
COMMENT ON TABLE clean_jira.issue_resolutions IS 'Normalized catalog of Jira resolutions per project.';
COMMENT ON COLUMN clean_jira.issue_resolutions.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_resolutions.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.issue_resolutions.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.issue_resolutions.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issue_resolutions.description IS 'Description value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issue_resolutions.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.changed_by_id IS 'Reference identifier for changed by.';
COMMENT ON COLUMN clean_jira.issue_statuses.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_statuses.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.issue_statuses.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.issue_statuses.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issue_statuses.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.issue_types.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issue_types.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.issue_types.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.issue_types.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issue_types.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.issues.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.issues.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.issues.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.issues.summary IS 'Summary value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issues.description IS 'Description value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.issues.db_created_at IS 'Timestamp/date value for db created at.';
COMMENT ON COLUMN clean_jira.issues.db_updated_at IS 'Timestamp/date value for db updated at.';
COMMENT ON COLUMN clean_jira.issues.priority_id IS 'Reference identifier for priority.';
COMMENT ON COLUMN clean_jira.issues.resolution_id IS 'Reference identifier for resolution.';
COMMENT ON COLUMN clean_jira.jira_user_issue_roles.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.jira_user_issue_roles.user_id IS 'Reference identifier for user.';
COMMENT ON COLUMN clean_jira.jira_user_issue_roles.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.jira_user_issue_roles.role_type IS 'Role type.';
COMMENT ON COLUMN clean_jira.jira_user_issue_roles.assigned_at IS 'Timestamp/date value for assigned at.';
COMMENT ON COLUMN clean_jira.jira_users.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.jira_users.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.jira_users.display_name IS 'Display name.';
COMMENT ON COLUMN clean_jira.jira_users.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.jira_users.updated_at IS 'Row last update timestamp.';
COMMENT ON TABLE clean_jira.labels IS 'Distinct Jira labels by project.';
COMMENT ON COLUMN clean_jira.labels.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.labels.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.labels.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.labels.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.projects.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.projects.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.projects.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.projects.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN clean_jira.relation_issue_issues.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.relation_issue_issues.relation_type_id IS 'Reference identifier for relation type.';
COMMENT ON COLUMN clean_jira.relation_issue_issues.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.relation_issue_types.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.relation_issue_types.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.relation_issue_types.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.relation_issue_types.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.release_changelog.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.release_changelog.release_id IS 'Reference identifier for release.';
COMMENT ON COLUMN clean_jira.release_changelog.old_value IS 'Old value.';
COMMENT ON COLUMN clean_jira.release_changelog.new_value IS 'New value.';
COMMENT ON COLUMN clean_jira.release_changelog.changed_by_id IS 'Reference identifier for changed by.';
COMMENT ON COLUMN clean_jira.release_changelog.changed_at IS 'Timestamp/date value for changed at.';
COMMENT ON COLUMN clean_jira.release_issues.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.release_issues.release_id IS 'Reference identifier for release.';
COMMENT ON COLUMN clean_jira.release_issues.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.release_issues_changelog.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.release_issues_changelog.release_id IS 'Reference identifier for release.';
COMMENT ON COLUMN clean_jira.release_issues_changelog.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.release_issues_changelog.action IS 'Action.';
COMMENT ON COLUMN clean_jira.release_issues_changelog.changed_by_id IS 'Reference identifier for changed by.';
COMMENT ON COLUMN clean_jira.release_issues_changelog.changed_at IS 'Timestamp/date value for changed at.';
COMMENT ON COLUMN clean_jira.releases.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.releases.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.releases.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.releases.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.releases.description IS 'Description value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.releases.status IS 'Normalized lifecycle status.';
COMMENT ON COLUMN clean_jira.releases.start_date IS 'Timestamp/date value for start date.';
COMMENT ON COLUMN clean_jira.releases.release_date IS 'Timestamp/date value for release date.';
COMMENT ON COLUMN clean_jira.releases.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.releases.updated_at IS 'Row last update timestamp.';
COMMENT ON COLUMN clean_jira.sprint_changelog.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.sprint_changelog.sprint_id IS 'Reference identifier for sprint.';
COMMENT ON COLUMN clean_jira.sprint_changelog.old_value IS 'Old value.';
COMMENT ON COLUMN clean_jira.sprint_changelog.new_value IS 'New value.';
COMMENT ON COLUMN clean_jira.sprint_changelog.changed_by_id IS 'Reference identifier for changed by.';
COMMENT ON COLUMN clean_jira.sprint_changelog.changed_at IS 'Timestamp/date value for changed at.';
COMMENT ON COLUMN clean_jira.sprint_issues.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.sprint_issues.sprint_id IS 'Reference identifier for sprint.';
COMMENT ON COLUMN clean_jira.sprint_issues.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.sprint_issues_changelog.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.sprint_issues_changelog.sprint_id IS 'Reference identifier for sprint.';
COMMENT ON COLUMN clean_jira.sprint_issues_changelog.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.sprint_issues_changelog.action IS 'Action.';
COMMENT ON COLUMN clean_jira.sprint_issues_changelog.changed_by_id IS 'Reference identifier for changed by.';
COMMENT ON COLUMN clean_jira.sprint_issues_changelog.changed_at IS 'Timestamp/date value for changed at.';
COMMENT ON COLUMN clean_jira.sprints.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.sprints.project_id IS 'Reference identifier for project.';
COMMENT ON COLUMN clean_jira.sprints.name IS 'Name value from source or normalized entity.';
COMMENT ON COLUMN clean_jira.sprints.created_at IS 'Row creation timestamp.';
COMMENT ON COLUMN clean_jira.sprints.updated_at IS 'Row last update timestamp.';
COMMENT ON TABLE clean_jira.worklogs IS 'Normalized worklog entries linked to issues.';
COMMENT ON COLUMN clean_jira.worklogs.id IS 'Primary key UUID.';
COMMENT ON COLUMN clean_jira.worklogs.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.worklogs.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.worklogs.author_id IS 'Reference identifier for author.';
COMMENT ON COLUMN clean_jira.worklogs.time_spent_seconds IS 'Time spent seconds.';
COMMENT ON COLUMN clean_jira.worklogs.started_at IS 'Timestamp/date value for started at.';
COMMENT ON COLUMN clean_jira.worklogs.created_at IS 'Row creation timestamp.';
COMMENT ON VIEW clean_jira.v_unique_users IS 'View of unique active Jira users across normalized entities.';

-- Curated semantic comments (priority objects)
COMMENT ON COLUMN clean_jira.projects.external_id IS 'Reference identifier for external.';

COMMENT ON COLUMN clean_jira.issues.issue_status_id IS 'Reference identifier for issue status.';
COMMENT ON COLUMN clean_jira.issues.issue_type_id IS 'Reference identifier for issue type.';

COMMENT ON COLUMN clean_jira.issue_status_changelog.issue_id IS 'Reference identifier for issue.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.from_status_id IS 'Reference identifier for from status.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.to_status_id IS 'Reference identifier for to status.';

COMMENT ON COLUMN clean_jira.sprints.external_id IS 'Reference identifier for external.';
COMMENT ON COLUMN clean_jira.sprints.start_date IS 'Timestamp/date value for start date.';
COMMENT ON COLUMN clean_jira.sprints.end_date IS 'Timestamp/date value for end date.';





COMMENT ON TABLE clean_jira.board_column_statuses IS 'Mapping between board columns and Jira statuses.';
COMMENT ON TABLE clean_jira.releases IS 'Normalized release/version dimension from Jira.';
COMMENT ON TABLE clean_jira.release_issues IS 'Issue-to-release membership links.';

-- Curated semantic comments v2 (top tables)
COMMENT ON TABLE clean_jira.projects IS 'Normalized Jira projects dimension mapped to platform projects.';
COMMENT ON COLUMN clean_jira.projects.platform_project_id IS 'Reference identifier for platform project.';
COMMENT ON COLUMN clean_jira.projects.external_key IS 'Key from source Jira system.';

COMMENT ON TABLE clean_jira.issues IS 'Normalized Jira issues at issue grain used as core analytical source.';
COMMENT ON COLUMN clean_jira.issues.external_key IS 'Jira issue key (for example, PROJ-123).';
COMMENT ON COLUMN clean_jira.issues.type_id IS 'Reference identifier for type.';
COMMENT ON COLUMN clean_jira.issues.status_id IS 'Reference identifier for status.';
COMMENT ON COLUMN clean_jira.issues.jira_created_at IS 'Issue creation timestamp in Jira.';
COMMENT ON COLUMN clean_jira.issues.jira_updated_at IS 'Issue last update timestamp in Jira.';
COMMENT ON COLUMN clean_jira.issues.jira_resolved_at IS 'Issue resolution timestamp in Jira, if resolved.';

COMMENT ON TABLE clean_jira.issue_statuses IS 'Normalized catalog of Jira statuses per project.';
COMMENT ON COLUMN clean_jira.issue_statuses.category IS 'Normalized category value.';

COMMENT ON TABLE clean_jira.issue_types IS 'Normalized catalog of Jira issue types per project.';
COMMENT ON COLUMN clean_jira.issue_types.hierarchy_level IS 'Hierarchy level.';

COMMENT ON TABLE clean_jira.issue_status_changelog IS 'Issue status transition history used for flow metrics.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.changed_at IS 'Timestamp of status transition.';

COMMENT ON TABLE clean_jira.sprints IS 'Normalized sprint dimension with timeline and state attributes.';
COMMENT ON COLUMN clean_jira.sprints.status IS 'Normalized lifecycle status.';
COMMENT ON COLUMN clean_jira.sprints.complete_date IS 'Timestamp/date value for complete date.';

COMMENT ON TABLE clean_jira.sprint_issues IS 'Current issue-to-sprint membership snapshot.';
COMMENT ON COLUMN clean_jira.sprint_issues.is_active IS 'Whether issue is currently active in sprint snapshot.';

COMMENT ON TABLE clean_jira.board_columns IS 'Board columns used for flow and commitment interpretation.';
COMMENT ON COLUMN clean_jira.board_columns.position IS 'Position.';

COMMENT ON TABLE clean_jira.field_keys IS 'Jira field dictionary for system and custom fields.';
COMMENT ON COLUMN clean_jira.field_keys.external_key IS 'Key from source Jira system.';

COMMENT ON TABLE clean_jira.field_values IS 'Current field values by issue and field key.';
COMMENT ON COLUMN clean_jira.field_values.value IS 'Text representation of field value.';
COMMENT ON COLUMN clean_jira.field_values.value_numeric IS 'Numeric interpretation of field value when applicable.';

-- Curated semantic comments v4 (manual high-detail)
COMMENT ON TABLE clean_jira.projects IS 'Canonical project dimension in clean layer; maps Jira projects to platform project identity.';
COMMENT ON COLUMN clean_jira.projects.id IS 'Warehouse UUID for normalized project row.';
COMMENT ON COLUMN clean_jira.projects.platform_project_id IS 'FK to platform.projects; cross-layer project identity key.';
COMMENT ON COLUMN clean_jira.projects.external_id IS 'Jira project ID from source API.';
COMMENT ON COLUMN clean_jira.projects.external_key IS 'Jira project key (for example PROJ).';
COMMENT ON COLUMN clean_jira.projects.name IS 'Project display name from Jira.';

COMMENT ON TABLE clean_jira.issues IS 'Normalized issue table (one row per Jira issue) used as primary source for metric calculations.';
COMMENT ON COLUMN clean_jira.issues.id IS 'Warehouse UUID for normalized issue row.';
COMMENT ON COLUMN clean_jira.issues.project_id IS 'FK to clean_jira.projects.';
COMMENT ON COLUMN clean_jira.issues.external_id IS 'Jira issue numeric/string ID.';
COMMENT ON COLUMN clean_jira.issues.external_key IS 'Jira issue key (for example PROJ-123).';
COMMENT ON COLUMN clean_jira.issues.type_id IS 'FK to clean_jira.issue_types.';
COMMENT ON COLUMN clean_jira.issues.status_id IS 'FK to clean_jira.issue_statuses (current status).';
COMMENT ON COLUMN clean_jira.issues.jira_created_at IS 'Issue creation timestamp from Jira.';
COMMENT ON COLUMN clean_jira.issues.jira_updated_at IS 'Issue last update timestamp from Jira.';
COMMENT ON COLUMN clean_jira.issues.jira_resolved_at IS 'Issue resolution timestamp from Jira, when available.';

COMMENT ON TABLE clean_jira.issue_statuses IS 'Per-project status dictionary normalized from Jira workflow states.';
COMMENT ON COLUMN clean_jira.issue_statuses.category IS 'Mapped category enum used by metrics (to_do, in_progress, done).';

COMMENT ON TABLE clean_jira.issue_types IS 'Per-project issue type dictionary with normalized hierarchy level.';
COMMENT ON COLUMN clean_jira.issue_types.hierarchy_level IS 'Normalized hierarchy level (epic/story/task/subtask) used in eligibility rules.';

COMMENT ON TABLE clean_jira.issue_status_changelog IS 'Normalized status transition history at issue level.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.issue_id IS 'FK to issue whose status changed.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.from_status_id IS 'FK to previous status.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.to_status_id IS 'FK to new status.';
COMMENT ON COLUMN clean_jira.issue_status_changelog.changed_at IS 'Timestamp of transition event.';

COMMENT ON TABLE clean_jira.sprints IS 'Normalized sprint dimension with planned and actual timeline attributes.';
COMMENT ON COLUMN clean_jira.sprints.external_id IS 'Jira sprint ID.';
COMMENT ON COLUMN clean_jira.sprints.status IS 'Normalized sprint state.';
COMMENT ON COLUMN clean_jira.sprints.start_date IS 'Planned sprint start timestamp.';
COMMENT ON COLUMN clean_jira.sprints.end_date IS 'Planned sprint end timestamp.';
COMMENT ON COLUMN clean_jira.sprints.complete_date IS 'Actual sprint completion timestamp.';

COMMENT ON TABLE clean_jira.sprint_issues IS 'Current issue-to-sprint membership snapshot used by sprint metrics.';
COMMENT ON COLUMN clean_jira.sprint_issues.sprint_id IS 'FK to sprint.';
COMMENT ON COLUMN clean_jira.sprint_issues.issue_id IS 'FK to issue.';
COMMENT ON COLUMN clean_jira.sprint_issues.is_active IS 'Snapshot flag: TRUE if issue currently belongs to sprint.';

COMMENT ON TABLE clean_jira.board_columns IS 'Normalized board columns used for commitment and flow stage boundaries.';
COMMENT ON COLUMN clean_jira.board_columns.board_id IS 'FK to board.';
COMMENT ON COLUMN clean_jira.board_columns.name IS 'Board column name as seen in Jira board configuration.';
COMMENT ON COLUMN clean_jira.board_columns.position IS 'Column order index on board.';

COMMENT ON TABLE clean_jira.field_keys IS 'Field dictionary (system/custom Jira fields) available for normalized extraction.';
COMMENT ON COLUMN clean_jira.field_keys.external_key IS 'Jira field key (for example customfield_10020).';
COMMENT ON COLUMN clean_jira.field_keys.name IS 'Human-readable field name.';

COMMENT ON TABLE clean_jira.field_values IS 'Current issue field values by field key, used for units and custom dimensions.';
COMMENT ON COLUMN clean_jira.field_values.issue_id IS 'FK to issue.';
COMMENT ON COLUMN clean_jira.field_values.field_key_id IS 'FK to field key.';
COMMENT ON COLUMN clean_jira.field_values.value IS 'Text representation of field value.';
COMMENT ON COLUMN clean_jira.field_values.value_numeric IS 'Numeric representation used in metric calculations where applicable.';
