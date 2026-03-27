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
-- Name: raw_jira; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA raw_jira;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _dlt_loads; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira._dlt_loads (
    load_id character varying(64) NOT NULL,
    schema_name character varying,
    status bigint NOT NULL,
    inserted_at timestamp with time zone NOT NULL,
    schema_version_hash character varying
);


--
-- Name: _dlt_pipeline_state; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira._dlt_pipeline_state (
    version bigint NOT NULL,
    engine_version bigint NOT NULL,
    pipeline_name character varying NOT NULL,
    state character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    version_hash character varying,
    _dlt_load_id character varying(64) NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: _dlt_version; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira._dlt_version (
    version bigint NOT NULL,
    engine_version bigint NOT NULL,
    inserted_at timestamp with time zone NOT NULL,
    schema_name character varying NOT NULL,
    version_hash character varying NOT NULL,
    schema character varying NOT NULL
);


--
-- Name: board_configurations; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.board_configurations (
    board_id bigint NOT NULL,
    board_name character varying,
    board_type character varying,
    project_key character varying,
    columns_config__constraint_type character varying,
    filter_id character varying,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: board_configurations__columns_config__columns; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.board_configurations__columns_config__columns (
    name character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: board_configurations__columns_config__columns__statuses; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.board_configurations__columns_config__columns__statuses (
    id character varying,
    self character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: fields; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.fields (
    id character varying NOT NULL,
    key character varying,
    name character varying,
    untranslated_name character varying,
    custom boolean,
    orderable boolean,
    navigable boolean,
    searchable boolean,
    schema__type character varying,
    schema__custom character varying,
    schema__custom_id bigint,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL,
    schema__items character varying,
    schema__system character varying,
    scope__type character varying,
    scope__project__id character varying,
    schema__configuration__is_multi boolean,
    schema__configuration__com_ata7y9qwtomfieldtypes_atlassian_team boolean
);


--
-- Name: fields__clause_names; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.fields__clause_names (
    value character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues (
    expand character varying,
    id character varying NOT NULL,
    self character varying,
    key character varying,
    rendered_fields__customfield_10071 character varying,
    rendered_fields__customfield_10078 character varying,
    rendered_fields__customfield_10994 character varying,
    rendered_fields__customfield_10060 character varying,
    rendered_fields__customfield_11273 character varying,
    rendered_fields__customfield_11274 character varying,
    rendered_fields__customfield_10067 character varying,
    rendered_fields__customfield_10068 character varying,
    rendered_fields__customfield_10056 character varying,
    rendered_fields__customfield_10057 character varying,
    rendered_fields__customfield_10058 character varying,
    rendered_fields__customfield_11139 character varying,
    rendered_fields__customfield_10843 character varying,
    rendered_fields__customfield_10844 character varying,
    rendered_fields__customfield_10286 character varying,
    rendered_fields__customfield_10046 character varying,
    rendered_fields__customfield_10048 character varying,
    rendered_fields__customfield_10710 character varying,
    rendered_fields__customfield_10711 character varying,
    rendered_fields__customfield_10712 character varying,
    rendered_fields__worklog__start_at bigint,
    rendered_fields__worklog__max_results bigint,
    rendered_fields__worklog__total bigint,
    rendered_fields__customfield_10152 character varying,
    rendered_fields__customfield_10156 character varying,
    rendered_fields__customfield_10157 character varying,
    rendered_fields__customfield_10017 character varying,
    rendered_fields__customfield_11106 character varying,
    rendered_fields__updated character varying,
    rendered_fields__description character varying,
    rendered_fields__customfield_11570 character varying,
    rendered_fields__environment character varying,
    rendered_fields__comment__self character varying,
    rendered_fields__comment__max_results bigint,
    rendered_fields__comment__total bigint,
    rendered_fields__comment__start_at bigint,
    rendered_fields__statuscategorychangedate character varying,
    rendered_fields__customfield_11091 character varying,
    rendered_fields__customfield_11093 character varying,
    rendered_fields__customfield_11095 character varying,
    rendered_fields__customfield_11080 character varying,
    rendered_fields__customfield_11081 character varying,
    rendered_fields__customfield_11082 character varying,
    rendered_fields__customfield_11083 character varying,
    rendered_fields__customfield_11088 character varying,
    rendered_fields__customfield_11089 character varying,
    rendered_fields__customfield_11638 character varying,
    rendered_fields__created character varying,
    rendered_fields__customfield_11074 character varying,
    rendered_fields__customfield_11077 character varying,
    rendered_fields__customfield_11078 character varying,
    changelog__start_at bigint,
    changelog__max_results bigint,
    changelog__total bigint,
    fields__parent__id character varying,
    fields__parent__key character varying,
    fields__parent__self character varying,
    fields__parent__fields__summary character varying,
    fields__parent__fields__status__self character varying,
    fields__parent__fields__status__description character varying,
    fields__parent__fields__status__icon_url character varying,
    fields__parent__fields__status__name character varying,
    fields__parent__fields__status__id character varying,
    fields__parent__fields__status__status_category__self character varying,
    fields__parent__fields__status__status_category__id bigint,
    fields__parent__fields__status__status_category__key character varying,
    fields__parent__fields__status__status_category__color_name character varying,
    fields__parent__fields__status__status_category__name character varying,
    fields__parent__fields__priority__self character varying,
    fields__parent__fields__priority__icon_url character varying,
    fields__parent__fields__priority__name character varying,
    fields__parent__fields__priority__id character varying,
    fields__parent__fields__issuetype__self character varying,
    fields__parent__fields__issuetype__id character varying,
    fields__parent__fields__issuetype__description character varying,
    fields__parent__fields__issuetype__icon_url character varying,
    fields__parent__fields__issuetype__name character varying,
    fields__parent__fields__issuetype__subtask boolean,
    fields__parent__fields__issuetype__avatar_id bigint,
    fields__parent__fields__issuetype__hierarchy_level bigint,
    fields__status_category__self character varying,
    fields__status_category__id bigint,
    fields__status_category__key character varying,
    fields__status_category__color_name character varying,
    fields__status_category__name character varying,
    fields__reporter__self character varying,
    fields__reporter__account_id character varying,
    fields__reporter__avatar_urls___48x48 character varying,
    fields__reporter__avatar_urls___24x24 character varying,
    fields__reporter__avatar_urls___16x16 character varying,
    fields__reporter__avatar_urls___32x32 character varying,
    fields__reporter__display_name character varying,
    fields__reporter__active boolean,
    fields__reporter__time_zone character varying,
    fields__reporter__account_type character varying,
    fields__progress__progress bigint,
    fields__progress__total bigint,
    fields__votes__self character varying,
    fields__votes__votes bigint,
    fields__votes__has_voted boolean,
    fields__worklog__start_at bigint,
    fields__worklog__max_results bigint,
    fields__worklog__total bigint,
    fields__issuetype__self character varying,
    fields__issuetype__id character varying,
    fields__issuetype__description character varying,
    fields__issuetype__icon_url character varying,
    fields__issuetype__name character varying,
    fields__issuetype__subtask boolean,
    fields__issuetype__avatar_id bigint,
    fields__issuetype__hierarchy_level bigint,
    fields__project__self character varying,
    fields__project__id character varying,
    fields__project__key character varying,
    fields__project__name character varying,
    fields__project__project_type_key character varying,
    fields__project__simplified boolean,
    fields__project__avatar_urls___48x48 character varying,
    fields__project__avatar_urls___24x24 character varying,
    fields__project__avatar_urls___16x16 character varying,
    fields__project__avatar_urls___32x32 character varying,
    fields__watches__self character varying,
    fields__watches__watch_count bigint,
    fields__watches__is_watching boolean,
    fields__customfield_10019 character varying,
    fields__updated timestamp with time zone,
    fields__summary character varying,
    fields__customfield_10000 character varying,
    fields__comment__self character varying,
    fields__comment__max_results bigint,
    fields__comment__total bigint,
    fields__comment__start_at bigint,
    fields__statuscategorychangedate timestamp with time zone,
    fields__priority__self character varying,
    fields__priority__icon_url character varying,
    fields__priority__name character varying,
    fields__priority__id character varying,
    fields__status__self character varying,
    fields__status__description character varying,
    fields__status__icon_url character varying,
    fields__status__name character varying,
    fields__status__id character varying,
    fields__status__status_category__self character varying,
    fields__status__status_category__id bigint,
    fields__status__status_category__key character varying,
    fields__status__status_category__color_name character varying,
    fields__status__status_category__name character varying,
    fields__creator__self character varying,
    fields__creator__account_id character varying,
    fields__creator__avatar_urls___48x48 character varying,
    fields__creator__avatar_urls___24x24 character varying,
    fields__creator__avatar_urls___16x16 character varying,
    fields__creator__avatar_urls___32x32 character varying,
    fields__creator__display_name character varying,
    fields__creator__active boolean,
    fields__creator__time_zone character varying,
    fields__creator__account_type character varying,
    fields__aggregateprogress__progress bigint,
    fields__aggregateprogress__total bigint,
    fields__customfield_10201 character varying,
    fields__workratio bigint,
    fields__issuerestriction__should_display boolean,
    fields__created timestamp with time zone,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL,
    rendered_fields__last_viewed character varying,
    fields__last_viewed timestamp with time zone,
    fields__assignee__self character varying,
    fields__assignee__account_id character varying,
    fields__assignee__email_address character varying,
    fields__assignee__avatar_urls___48x48 character varying,
    fields__assignee__avatar_urls___24x24 character varying,
    fields__assignee__avatar_urls___16x16 character varying,
    fields__assignee__avatar_urls___32x32 character varying,
    fields__assignee__display_name character varying,
    fields__assignee__active boolean,
    fields__assignee__time_zone character varying,
    fields__assignee__account_type character varying,
    fields__reporter__email_address character varying,
    fields__customfield_10036 double precision,
    fields__customfield_11237 double precision,
    fields__description__type character varying,
    fields__description__version bigint,
    fields__customfield_10014 character varying,
    fields__creator__email_address character varying,
    rendered_fields__customfield_10011 character varying,
    rendered_fields__customfield_10013 character varying,
    fields__customfield_10017 character varying,
    fields__customfield_10012__self character varying,
    fields__customfield_10012__value character varying,
    fields__customfield_10012__id character varying,
    fields__customfield_10013 character varying,
    rendered_fields__resolutiondate character varying,
    fields__resolution__self character varying,
    fields__resolution__id character varying,
    fields__resolution__description character varying,
    fields__resolution__name character varying,
    fields__resolutiondate timestamp with time zone,
    rendered_fields__customfield_10015 character varying,
    fields__customfield_10015 character varying,
    rendered_fields__duedate character varying,
    fields__customfield_10011 character varying,
    fields__duedate character varying,
    fields__customfield_10016 double precision,
    fields__customfield_11041__self character varying,
    fields__customfield_11041__value character varying,
    fields__customfield_11041__id character varying,
    fields__customfield_10050__error_message character varying,
    fields__customfield_10050__i18n_error_message__i18n_key character varying,
    fields__customfield_10049__error_message character varying,
    fields__customfield_10049__i18n_error_message__i18n_key character varying,
    fields__customfield_10680__error_message character varying,
    fields__customfield_10680__i18n_error_message__i18n_key character varying,
    rendered_fields__aggregatetimeoriginalestimate character varying,
    rendered_fields__timeoriginalestimate character varying,
    rendered_fields__timetracking__original_estimate character varying,
    rendered_fields__timetracking__remaining_estimate character varying,
    rendered_fields__timetracking__original_estimate_seconds bigint,
    rendered_fields__timetracking__remaining_estimate_seconds bigint,
    rendered_fields__timeestimate character varying,
    rendered_fields__aggregatetimeestimate character varying,
    fields__aggregatetimeoriginalestimate bigint,
    fields__timeoriginalestimate bigint,
    fields__timetracking__original_estimate character varying,
    fields__timetracking__remaining_estimate character varying,
    fields__timetracking__original_estimate_seconds bigint,
    fields__timetracking__remaining_estimate_seconds bigint,
    fields__timeestimate bigint,
    fields__aggregatetimeestimate bigint,
    fields__progress__percent bigint,
    fields__aggregateprogress__percent bigint,
    fields__environment__type character varying,
    fields__environment__version bigint,
    rendered_fields__customfield_10197 character varying,
    rendered_fields__customfield_10186 character varying,
    rendered_fields__customfield_10610 character varying,
    rendered_fields__customfield_10611 character varying,
    rendered_fields__customfield_10612 character varying,
    rendered_fields__customfield_10224 character varying,
    rendered_fields__customfield_10331 character varying,
    rendered_fields__customfield_10332 character varying,
    rendered_fields__customfield_10415 character varying,
    fields__customfield_10291__self character varying,
    fields__customfield_10291__value character varying,
    fields__customfield_10291__id character varying,
    fields__project__project_category__self character varying,
    fields__project__project_category__id character varying,
    fields__project__project_category__description character varying,
    fields__project__project_category__name character varying,
    fields__customfield_10336__self character varying,
    fields__customfield_10336__account_id character varying,
    fields__customfield_10336__email_address character varying,
    fields__customfield_10336__avatar_urls___48x48 character varying,
    fields__customfield_10336__avatar_urls___24x24 character varying,
    fields__customfield_10336__avatar_urls___16x16 character varying,
    fields__customfield_10336__avatar_urls___32x32 character varying,
    fields__customfield_10336__display_name character varying,
    fields__customfield_10336__active boolean,
    fields__customfield_10336__time_zone character varying,
    fields__customfield_10336__account_type character varying,
    fields__customfield_11468__error_message character varying,
    fields__customfield_11468__i18n_error_message__i18n_key character varying,
    fields__customfield_10941__self character varying,
    fields__customfield_10941__value character varying,
    fields__customfield_10941__id character varying,
    fields__customfield_11435__self character varying,
    fields__customfield_11435__value character varying,
    fields__customfield_11435__id character varying,
    fields__customfield_10001__id character varying,
    fields__customfield_10001__name character varying,
    fields__customfield_10001__avatar_url character varying,
    fields__customfield_10001__is_visible boolean,
    fields__customfield_10001__is_verified boolean,
    fields__customfield_10001__title character varying,
    fields__customfield_10001__is_shared boolean,
    fields__customfield_11739 timestamp with time zone,
    rendered_fields__customfield_11739 character varying,
    fields__aggregatetimespent bigint,
    rendered_fields__aggregatetimespent character varying,
    fields__timespent bigint,
    fields__timetracking__time_spent character varying,
    fields__timetracking__time_spent_seconds bigint,
    rendered_fields__timespent character varying,
    rendered_fields__timetracking__time_spent character varying,
    rendered_fields__timetracking__time_spent_seconds bigint,
    fields__customfield_11740 character varying
);


--
-- Name: issues__changelog__histories; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__changelog__histories (
    id character varying,
    author__self character varying,
    author__account_id character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    created timestamp with time zone,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    author__email_address character varying
);


--
-- Name: issues__changelog__histories__items; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__changelog__histories__items (
    field character varying,
    fieldtype character varying,
    "to" character varying,
    to_string character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    field_id character varying,
    from_string character varying,
    "from" character varying,
    tmp_to_account_id character varying
);


--
-- Name: issues__fields__attachment; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__attachment (
    self character varying,
    id character varying,
    filename character varying,
    author__self character varying,
    author__account_id character varying,
    author__email_address character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    created timestamp with time zone,
    size bigint,
    mime_type character varying,
    content character varying,
    thumbnail character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__comm3dzdeqent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__comm3dzdeqent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__commak4pdqt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commak4pdqt__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__text character varying,
    attrs__access_level character varying,
    attrs__local_id character varying,
    attrs__url character varying,
    attrs__short_name character varying,
    attrs__order bigint,
    attrs__width__v_double double precision,
    attrs__layout character varying
);


--
-- Name: issues__fields__comment__commasbvjqent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commasbvjqent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__commbtoy5wt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commbtoy5wt__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__commdhejxqent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commdhejxqent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__href character varying
);


--
-- Name: issues__fields__comment__commelqwmgt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commelqwmgt__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__order bigint,
    attrs__url character varying,
    attrs__short_name character varying,
    attrs__id character varying,
    attrs__text character varying,
    attrs__type character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__local_id character varying
);


--
-- Name: issues__fields__comment__comments; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__comments (
    self character varying,
    id character varying,
    author__self character varying,
    author__account_id character varying,
    author__email_address character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    body__type character varying,
    body__version bigint,
    update_author__self character varying,
    update_author__account_id character varying,
    update_author__email_address character varying,
    update_author__avatar_urls___48x48 character varying,
    update_author__avatar_urls___24x24 character varying,
    update_author__avatar_urls___16x16 character varying,
    update_author__avatar_urls___32x32 character varying,
    update_author__display_name character varying,
    update_author__active boolean,
    update_author__time_zone character varying,
    update_author__account_type character varying,
    created timestamp with time zone,
    updated timestamp with time zone,
    jsd_public boolean,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__comments__body__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__comments__body__content (
    type character varying,
    attrs__local_id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__width bigint,
    attrs__width_type character varying,
    attrs__layout character varying,
    attrs__order bigint,
    attrs__level bigint,
    attrs__url character varying,
    attrs__language character varying,
    attrs__is_number_column_enabled boolean,
    attrs__width__v_double double precision,
    attrs__panel_type character varying
);


--
-- Name: issues__fields__comment__comments__body__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__comments__body__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__url character varying,
    attrs__local_id character varying,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__text character varying,
    attrs__access_level character varying,
    attrs__short_name character varying,
    attrs__order bigint,
    attrs__state character varying
);


--
-- Name: issues__fields__comment__commfgqtowent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commfgqtowent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__size bigint,
    attrs__color character varying
);


--
-- Name: issues__fields__comment__commkwmv2at__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commkwmv2at__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__width bigint,
    attrs__layout character varying
);


--
-- Name: issues__fields__comment__commlura1aent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commlura1aent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__commnjpp9qt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commnjpp9qt__content__content__content (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    text character varying,
    attrs__short_name character varying,
    attrs__id character varying,
    attrs__text character varying,
    attrs__type character varying,
    attrs__alt character varying,
    attrs__collection character varying
);


--
-- Name: issues__fields__comment__commutqfnqy__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commutqfnqy__content__content__content (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__width bigint,
    attrs__width_type character varying,
    attrs__layout character varying,
    attrs__local_id character varying,
    text character varying,
    attrs__background character varying,
    attrs__short_name character varying,
    attrs__id character varying,
    attrs__text character varying,
    attrs__width__v_double double precision,
    attrs__order bigint,
    attrs__type character varying,
    attrs__collection character varying
);


--
-- Name: issues__fields__comment__commvqfaaaent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commvqfaaaent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__comment__commw2ps0wody__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__href character varying,
    attrs__color character varying
);


--
-- Name: issues__fields__comment__commyvyajqt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commyvyajqt__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__local_id character varying,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__url character varying,
    attrs__layout character varying,
    attrs__order bigint,
    attrs__width_type character varying
);


--
-- Name: issues__fields__comment__commzmilvgnt__content__attrs__colwidth; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__comment__commzmilvgnt__content__attrs__colwidth (
    value bigint,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10020; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10020 (
    id bigint,
    name character varying,
    state character varying,
    board_id bigint,
    goal character varying,
    start_date timestamp with time zone,
    end_date timestamp with time zone,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    complete_date timestamp with time zone
);


--
-- Name: issues__fields__customfield_10021; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10021 (
    self character varying,
    value character varying,
    id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10025; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10025 (
    id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10253; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10253 (
    self character varying,
    value character varying,
    id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10254; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10254 (
    self character varying,
    value character varying,
    id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10309; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10309 (
    self character varying,
    account_id character varying,
    email_address character varying,
    avatar_urls___48x48 character varying,
    avatar_urls___24x24 character varying,
    avatar_urls___16x16 character varying,
    avatar_urls___32x32 character varying,
    display_name character varying,
    active boolean,
    time_zone character varying,
    account_type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10311; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10311 (
    self character varying,
    account_id character varying,
    email_address character varying,
    avatar_urls___48x48 character varying,
    avatar_urls___24x24 character varying,
    avatar_urls___16x16 character varying,
    avatar_urls___32x32 character varying,
    display_name character varying,
    active boolean,
    time_zone character varying,
    account_type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_10327; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_10327 (
    self character varying,
    account_id character varying,
    email_address character varying,
    avatar_urls___48x48 character varying,
    avatar_urls___24x24 character varying,
    avatar_urls___16x16 character varying,
    avatar_urls___32x32 character varying,
    display_name character varying,
    active boolean,
    time_zone character varying,
    account_type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__customfield_11039; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__customfield_11039 (
    self character varying,
    value character varying,
    id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__description__1b8wfwt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__1b8wfwt__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__description__4my9qgent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__4my9qgent__content__content__marks (
    type character varying,
    attrs__href character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__description__ahypbqent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__ahypbqent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__href character varying
);


--
-- Name: issues__fields__description__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content (
    type character varying,
    attrs__local_id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__order bigint,
    attrs__width bigint,
    attrs__width_type character varying,
    attrs__layout character varying,
    attrs__level bigint,
    attrs__is_number_column_enabled boolean,
    attrs__url character varying,
    attrs__language character varying,
    attrs__panel_type character varying,
    attrs__width__v_double double precision,
    attrs__title character varying,
    attrs__datasource__id character varying,
    attrs__datasource__parameters__cloud_id character varying,
    attrs__datasource__parameters__jql character varying
);


--
-- Name: issues__fields__description__content__attrs__datasource__views; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content__attrs__datasource__views (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__description__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__url character varying,
    attrs__local_id character varying,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__text character varying,
    attrs__access_level character varying,
    attrs__state character varying,
    attrs__short_name character varying,
    attrs__layout character varying,
    attrs__order bigint
);


--
-- Name: issues__fields__description__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content__content__content (
    type character varying,
    attrs__local_id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__width bigint,
    attrs__width_type character varying,
    attrs__layout character varying,
    attrs__language character varying,
    attrs__order bigint,
    attrs__background character varying,
    text character varying,
    attrs__width__v_double double precision,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__url character varying
);


--
-- Name: issues__fields__description__content__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__local_id character varying,
    attrs__url character varying,
    attrs__order bigint,
    attrs__width_type character varying,
    attrs__layout character varying,
    attrs__text character varying,
    attrs__access_level character varying,
    attrs__short_name character varying
);


--
-- Name: issues__fields__description__content__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__description__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__href character varying,
    attrs__color character varying,
    attrs__size bigint
);


--
-- Name: issues__fields__description__cxb90gt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__cxb90gt__content__content__content (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__width bigint,
    attrs__width_type character varying,
    attrs__layout character varying,
    attrs__local_id character varying,
    attrs__order bigint,
    attrs__url character varying,
    text character varying,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__short_name character varying,
    attrs__text character varying
);


--
-- Name: issues__fields__description__cywg2aent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__cywg2aent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__description__ejpj8wt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__ejpj8wt__content__content__content (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    text character varying
);


--
-- Name: issues__fields__description__g2calqt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__g2calqt__content__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    attrs__url character varying,
    attrs__order bigint
);


--
-- Name: issues__fields__description__g8erbqent__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__g8erbqent__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__href character varying,
    attrs__color character varying
);


--
-- Name: issues__fields__description__ihgkwat__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__ihgkwat__content__content__content (
    type character varying,
    attrs__layout character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    text character varying
);


--
-- Name: issues__fields__description__jwtu1went__content__content__marks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__jwtu1went__content__content__marks (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    attrs__href character varying,
    attrs__size bigint,
    attrs__color character varying
);


--
-- Name: issues__fields__description__nkeuxw__views__properties__columns; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__nkeuxw__views__properties__columns (
    key character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    width bigint
);


--
-- Name: issues__fields__description__nnkbewt__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__nnkbewt__content__content__content (
    type text,
    text text,
    _dlt_root_id text NOT NULL,
    _dlt_parent_id text NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id text NOT NULL
);


--
-- Name: issues__fields__description__t8qrkat__content__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__description__t8qrkat__content__content__content (
    type character varying,
    attrs__type character varying,
    attrs__id character varying,
    attrs__alt character varying,
    attrs__collection character varying,
    attrs__height bigint,
    attrs__width bigint,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    text character varying,
    attrs__url character varying
);


--
-- Name: issues__fields__environment__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__environment__content (
    type character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__environment__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__environment__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__fix_versions; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__fix_versions (
    self character varying,
    id character varying,
    description character varying,
    name character varying,
    archived boolean,
    released boolean,
    release_date character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__issuelinks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__issuelinks (
    id character varying,
    self character varying,
    type__id character varying,
    type__name character varying,
    type__inward character varying,
    type__outward character varying,
    type__self character varying,
    outward_issue__id character varying,
    outward_issue__key character varying,
    outward_issue__self character varying,
    outward_issue__fields__summary character varying,
    outward_issue__fields__status__self character varying,
    outward_issue__fields__status__description character varying,
    outward_issue__fields__status__icon_url character varying,
    outward_issue__fields__status__name character varying,
    outward_issue__fields__status__id character varying,
    outward_issue__fields__status__status_category__self character varying,
    outward_issue__fields__status__status_category__id bigint,
    outward_issue__fields__status__status_category__key character varying,
    outward_issue__fields__status__status_category__color_name character varying,
    outward_issue__fields__status__status_category__name character varying,
    outward_issue__fields__priority__self character varying,
    outward_issue__fields__priority__icon_url character varying,
    outward_issue__fields__priority__name character varying,
    outward_issue__fields__priority__id character varying,
    outward_issue__fields__issuetype__self character varying,
    outward_issue__fields__issuetype__id character varying,
    outward_issue__fields__issuetype__description character varying,
    outward_issue__fields__issuetype__icon_url character varying,
    outward_issue__fields__issuetype__name character varying,
    outward_issue__fields__issuetype__subtask boolean,
    outward_issue__fields__issuetype__avatar_id bigint,
    outward_issue__fields__issuetype__hierarchy_level bigint,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    inward_issue__id character varying,
    inward_issue__key character varying,
    inward_issue__self character varying,
    inward_issue__fields__summary character varying,
    inward_issue__fields__status__self character varying,
    inward_issue__fields__status__description character varying,
    inward_issue__fields__status__icon_url character varying,
    inward_issue__fields__status__name character varying,
    inward_issue__fields__status__id character varying,
    inward_issue__fields__status__status_category__self character varying,
    inward_issue__fields__status__status_category__id bigint,
    inward_issue__fields__status__status_category__key character varying,
    inward_issue__fields__status__status_category__color_name character varying,
    inward_issue__fields__status__status_category__name character varying,
    inward_issue__fields__priority__self character varying,
    inward_issue__fields__priority__icon_url character varying,
    inward_issue__fields__priority__name character varying,
    inward_issue__fields__priority__id character varying,
    inward_issue__fields__issuetype__self character varying,
    inward_issue__fields__issuetype__id character varying,
    inward_issue__fields__issuetype__description character varying,
    inward_issue__fields__issuetype__icon_url character varying,
    inward_issue__fields__issuetype__name character varying,
    inward_issue__fields__issuetype__subtask boolean,
    inward_issue__fields__issuetype__avatar_id bigint,
    inward_issue__fields__issuetype__hierarchy_level bigint,
    outward_issue__fields__issuetype__entity_id character varying,
    inward_issue__fields__issuetype__entity_id character varying
);


--
-- Name: issues__fields__labels; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__labels (
    value character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__subtasks; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__subtasks (
    id character varying,
    key character varying,
    self character varying,
    fields__summary character varying,
    fields__status__self character varying,
    fields__status__description character varying,
    fields__status__icon_url character varying,
    fields__status__name character varying,
    fields__status__id character varying,
    fields__status__status_category__self character varying,
    fields__status__status_category__id bigint,
    fields__status__status_category__key character varying,
    fields__status__status_category__color_name character varying,
    fields__status__status_category__name character varying,
    fields__priority__self character varying,
    fields__priority__icon_url character varying,
    fields__priority__name character varying,
    fields__priority__id character varying,
    fields__issuetype__self character varying,
    fields__issuetype__id character varying,
    fields__issuetype__description character varying,
    fields__issuetype__icon_url character varying,
    fields__issuetype__name character varying,
    fields__issuetype__subtask boolean,
    fields__issuetype__avatar_id bigint,
    fields__issuetype__hierarchy_level bigint,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__worklog__worklogs; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__worklog__worklogs (
    self character varying,
    created timestamp with time zone,
    updated timestamp with time zone,
    started timestamp with time zone,
    time_spent character varying,
    time_spent_seconds bigint,
    id character varying,
    issue_id character varying,
    update_author__self character varying,
    update_author__account_id character varying,
    update_author__email_address character varying,
    update_author__display_name character varying,
    update_author__active boolean,
    update_author__time_zone character varying,
    update_author__account_type character varying,
    update_author__avatar_urls___48x48 character varying,
    update_author__avatar_urls___24x24 character varying,
    update_author__avatar_urls___16x16 character varying,
    update_author__avatar_urls___32x32 character varying,
    author__self character varying,
    author__account_id character varying,
    author__email_address character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    comment__type character varying,
    comment__version bigint
);


--
-- Name: issues__fields__worklog__worklogs__comment__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__worklog__worklogs__comment__content (
    type character varying,
    attrs__local_id character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__fields__worklog__worklogs__comment__content__content; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__fields__worklog__worklogs__comment__content__content (
    type character varying,
    text character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__rendered_fields__attachment; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__rendered_fields__attachment (
    self character varying,
    id character varying,
    filename character varying,
    author__self character varying,
    author__account_id character varying,
    author__email_address character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    created character varying,
    size character varying,
    mime_type character varying,
    content character varying,
    thumbnail character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__rendered_fields__comment__comments; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__rendered_fields__comment__comments (
    self character varying,
    id character varying,
    author__self character varying,
    author__account_id character varying,
    author__email_address character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    body character varying,
    update_author__self character varying,
    update_author__account_id character varying,
    update_author__email_address character varying,
    update_author__avatar_urls___48x48 character varying,
    update_author__avatar_urls___24x24 character varying,
    update_author__avatar_urls___16x16 character varying,
    update_author__avatar_urls___32x32 character varying,
    update_author__display_name character varying,
    update_author__active boolean,
    update_author__time_zone character varying,
    update_author__account_type character varying,
    created character varying,
    updated character varying,
    jsd_public boolean,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: issues__rendered_fields__worklog__worklogs; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.issues__rendered_fields__worklog__worklogs (
    self character varying,
    created character varying,
    updated character varying,
    started character varying,
    time_spent character varying,
    id character varying,
    issue_id character varying,
    update_author__self character varying,
    update_author__account_id character varying,
    update_author__email_address character varying,
    update_author__display_name character varying,
    update_author__active boolean,
    update_author__time_zone character varying,
    update_author__account_type character varying,
    update_author__avatar_urls___48x48 character varying,
    update_author__avatar_urls___24x24 character varying,
    update_author__avatar_urls___16x16 character varying,
    update_author__avatar_urls___32x32 character varying,
    author__self character varying,
    author__account_id character varying,
    author__email_address character varying,
    author__display_name character varying,
    author__active boolean,
    author__time_zone character varying,
    author__account_type character varying,
    author__avatar_urls___48x48 character varying,
    author__avatar_urls___24x24 character varying,
    author__avatar_urls___16x16 character varying,
    author__avatar_urls___32x32 character varying,
    _dlt_root_id character varying NOT NULL,
    _dlt_parent_id character varying NOT NULL,
    _dlt_list_idx bigint NOT NULL,
    _dlt_id character varying NOT NULL,
    comment character varying
);


--
-- Name: projects; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.projects (
    expand character varying,
    self character varying,
    id character varying NOT NULL,
    key character varying,
    description character varying,
    lead__self character varying,
    lead__account_id character varying,
    lead__account_type character varying,
    lead__avatar_urls___48x48 character varying,
    lead__avatar_urls___24x24 character varying,
    lead__avatar_urls___16x16 character varying,
    lead__avatar_urls___32x32 character varying,
    lead__display_name character varying,
    lead__active boolean,
    name character varying,
    avatar_urls___48x48 character varying,
    avatar_urls___24x24 character varying,
    avatar_urls___16x16 character varying,
    avatar_urls___32x32 character varying,
    project_type_key character varying,
    simplified boolean,
    style character varying,
    is_private boolean,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL,
    project_category__self character varying,
    project_category__id character varying,
    project_category__name character varying,
    project_category__description character varying
);


--
-- Name: sprints; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.sprints (
    id bigint NOT NULL,
    self character varying,
    state character varying,
    name character varying,
    start_date timestamp with time zone,
    end_date timestamp with time zone,
    complete_date timestamp with time zone,
    origin_board_id bigint,
    goal character varying,
    board_id bigint,
    board_name character varying,
    project_key character varying,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL,
    created_date timestamp with time zone
);


--
-- Name: users; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.users (
    self character varying,
    account_id character varying NOT NULL,
    account_type character varying,
    email_address character varying,
    avatar_urls___48x48 character varying,
    avatar_urls___24x24 character varying,
    avatar_urls___16x16 character varying,
    avatar_urls___32x32 character varying,
    display_name character varying,
    active boolean,
    time_zone character varying,
    locale character varying,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL
);


--
-- Name: versions; Type: TABLE; Schema: raw_jira; Owner: -
--

CREATE TABLE raw_jira.versions (
    self character varying,
    id character varying NOT NULL,
    description character varying,
    name character varying,
    archived boolean,
    released boolean,
    release_date character varying,
    user_release_date character varying,
    project_id character varying,
    project_key character varying,
    _dlt_load_id character varying NOT NULL,
    _dlt_id character varying NOT NULL,
    overdue boolean
);


--
-- Name: _dlt_pipeline_state _dlt_pipeline_state__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira._dlt_pipeline_state
    ADD CONSTRAINT _dlt_pipeline_state__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: board_configurations__columns_config__columns board_configurations__columns_config__columns__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.board_configurations__columns_config__columns
    ADD CONSTRAINT board_configurations__columns_config__columns__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: board_configurations__columns_config__columns__statuses board_configurations__columns_config__columns__stat__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.board_configurations__columns_config__columns__statuses
    ADD CONSTRAINT board_configurations__columns_config__columns__stat__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: board_configurations board_configurations__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.board_configurations
    ADD CONSTRAINT board_configurations__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: fields__clause_names fields__clause_names__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.fields__clause_names
    ADD CONSTRAINT fields__clause_names__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: fields fields__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.fields
    ADD CONSTRAINT fields__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__changelog__histories issues__changelog__histories__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__changelog__histories
    ADD CONSTRAINT issues__changelog__histories__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__changelog__histories__items issues__changelog__histories__items__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__changelog__histories__items
    ADD CONSTRAINT issues__changelog__histories__items__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues issues__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues
    ADD CONSTRAINT issues__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__attachment issues__fields__attachment__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__attachment
    ADD CONSTRAINT issues__fields__attachment__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__comm3dzdeqent__content__content__marks issues__fields__comment__comm3dzdeqent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__comm3dzdeqent__content__content__marks
    ADD CONSTRAINT issues__fields__comment__comm3dzdeqent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commak4pdqt__content__content__content issues__fields__comment__commak4pdqt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commak4pdqt__content__content__content
    ADD CONSTRAINT issues__fields__comment__commak4pdqt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commasbvjqent__content__content__marks issues__fields__comment__commasbvjqent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commasbvjqent__content__content__marks
    ADD CONSTRAINT issues__fields__comment__commasbvjqent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commbtoy5wt__content__content__content issues__fields__comment__commbtoy5wt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commbtoy5wt__content__content__content
    ADD CONSTRAINT issues__fields__comment__commbtoy5wt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commdhejxqent__content__content__marks issues__fields__comment__commdhejxqent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commdhejxqent__content__content__marks
    ADD CONSTRAINT issues__fields__comment__commdhejxqent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commelqwmgt__content__content__content issues__fields__comment__commelqwmgt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commelqwmgt__content__content__content
    ADD CONSTRAINT issues__fields__comment__commelqwmgt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__comments__body__content__content issues__fields__comment__comments__body__content__c__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__comments__body__content__content
    ADD CONSTRAINT issues__fields__comment__comments__body__content__c__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__comments__body__content issues__fields__comment__comments__body__content__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__comments__body__content
    ADD CONSTRAINT issues__fields__comment__comments__body__content__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__comments issues__fields__comment__comments__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__comments
    ADD CONSTRAINT issues__fields__comment__comments__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commfgqtowent__content__content__marks issues__fields__comment__commfgqtowent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commfgqtowent__content__content__marks
    ADD CONSTRAINT issues__fields__comment__commfgqtowent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commkwmv2at__content__content__content issues__fields__comment__commkwmv2at__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commkwmv2at__content__content__content
    ADD CONSTRAINT issues__fields__comment__commkwmv2at__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commlura1aent__content__content__marks issues__fields__comment__commlura1aent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commlura1aent__content__content__marks
    ADD CONSTRAINT issues__fields__comment__commlura1aent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commnjpp9qt__content__content__content issues__fields__comment__commnjpp9qt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commnjpp9qt__content__content__content
    ADD CONSTRAINT issues__fields__comment__commnjpp9qt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commutqfnqy__content__content__content issues__fields__comment__commutqfnqy__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commutqfnqy__content__content__content
    ADD CONSTRAINT issues__fields__comment__commutqfnqy__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commvqfaaaent__content__content__marks issues__fields__comment__commvqfaaaent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commvqfaaaent__content__content__marks
    ADD CONSTRAINT issues__fields__comment__commvqfaaaent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commw2ps0wody__content__content__marks issues__fields__comment__commw2ps0wody__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks
    ADD CONSTRAINT issues__fields__comment__commw2ps0wody__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commyvyajqt__content__content__content issues__fields__comment__commyvyajqt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commyvyajqt__content__content__content
    ADD CONSTRAINT issues__fields__comment__commyvyajqt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__comment__commzmilvgnt__content__attrs__colwidth issues__fields__comment__commzmilvgnt__content__att__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__comment__commzmilvgnt__content__attrs__colwidth
    ADD CONSTRAINT issues__fields__comment__commzmilvgnt__content__att__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10020 issues__fields__customfield_10020__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10020
    ADD CONSTRAINT issues__fields__customfield_10020__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10021 issues__fields__customfield_10021__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10021
    ADD CONSTRAINT issues__fields__customfield_10021__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10025 issues__fields__customfield_10025__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10025
    ADD CONSTRAINT issues__fields__customfield_10025__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10253 issues__fields__customfield_10253__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10253
    ADD CONSTRAINT issues__fields__customfield_10253__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10254 issues__fields__customfield_10254__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10254
    ADD CONSTRAINT issues__fields__customfield_10254__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10309 issues__fields__customfield_10309__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10309
    ADD CONSTRAINT issues__fields__customfield_10309__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10311 issues__fields__customfield_10311__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10311
    ADD CONSTRAINT issues__fields__customfield_10311__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_10327 issues__fields__customfield_10327__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_10327
    ADD CONSTRAINT issues__fields__customfield_10327__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__customfield_11039 issues__fields__customfield_11039__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__customfield_11039
    ADD CONSTRAINT issues__fields__customfield_11039__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__1b8wfwt__content__content__content issues__fields__description__1b8wfwt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__1b8wfwt__content__content__content
    ADD CONSTRAINT issues__fields__description__1b8wfwt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__4my9qgent__content__content__marks issues__fields__description__4my9qgent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__4my9qgent__content__content__marks
    ADD CONSTRAINT issues__fields__description__4my9qgent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__ahypbqent__content__content__marks issues__fields__description__ahypbqent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__ahypbqent__content__content__marks
    ADD CONSTRAINT issues__fields__description__ahypbqent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content__attrs__datasource__views issues__fields__description__content__attrs__dataso__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content__attrs__datasource__views
    ADD CONSTRAINT issues__fields__description__content__attrs__dataso__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content__content__content issues__fields__description__content__content__con__dlt_id_key1; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content__content__content
    ADD CONSTRAINT issues__fields__description__content__content__con__dlt_id_key1 UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content__content__content__marks issues__fields__description__content__content__con__dlt_id_key2; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content__content__content__marks
    ADD CONSTRAINT issues__fields__description__content__content__con__dlt_id_key2 UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content__content__content__content issues__fields__description__content__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content__content__content__content
    ADD CONSTRAINT issues__fields__description__content__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content__content issues__fields__description__content__content__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content__content
    ADD CONSTRAINT issues__fields__description__content__content__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content__content__marks issues__fields__description__content__content__mark__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content__content__marks
    ADD CONSTRAINT issues__fields__description__content__content__mark__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__content issues__fields__description__content__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__content
    ADD CONSTRAINT issues__fields__description__content__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__cxb90gt__content__content__content issues__fields__description__cxb90gt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__cxb90gt__content__content__content
    ADD CONSTRAINT issues__fields__description__cxb90gt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__cywg2aent__content__content__marks issues__fields__description__cywg2aent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__cywg2aent__content__content__marks
    ADD CONSTRAINT issues__fields__description__cywg2aent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__ejpj8wt__content__content__content issues__fields__description__ejpj8wt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__ejpj8wt__content__content__content
    ADD CONSTRAINT issues__fields__description__ejpj8wt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__g2calqt__content__content__content issues__fields__description__g2calqt__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__g2calqt__content__content__content
    ADD CONSTRAINT issues__fields__description__g2calqt__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__g8erbqent__content__content__marks issues__fields__description__g8erbqent__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__g8erbqent__content__content__marks
    ADD CONSTRAINT issues__fields__description__g8erbqent__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__ihgkwat__content__content__content issues__fields__description__ihgkwat__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__ihgkwat__content__content__content
    ADD CONSTRAINT issues__fields__description__ihgkwat__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__jwtu1went__content__content__marks issues__fields__description__jwtu1went__content__co__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__jwtu1went__content__content__marks
    ADD CONSTRAINT issues__fields__description__jwtu1went__content__co__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__nkeuxw__views__properties__columns issues__fields__description__nkeuxw__views__propert__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__nkeuxw__views__properties__columns
    ADD CONSTRAINT issues__fields__description__nkeuxw__views__propert__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__description__t8qrkat__content__content__content issues__fields__description__t8qrkat__content__cont__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__description__t8qrkat__content__content__content
    ADD CONSTRAINT issues__fields__description__t8qrkat__content__cont__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__environment__content__content issues__fields__environment__content__content__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__environment__content__content
    ADD CONSTRAINT issues__fields__environment__content__content__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__environment__content issues__fields__environment__content__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__environment__content
    ADD CONSTRAINT issues__fields__environment__content__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__fix_versions issues__fields__fix_versions__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__fix_versions
    ADD CONSTRAINT issues__fields__fix_versions__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__issuelinks issues__fields__issuelinks__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__issuelinks
    ADD CONSTRAINT issues__fields__issuelinks__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__labels issues__fields__labels__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__labels
    ADD CONSTRAINT issues__fields__labels__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__subtasks issues__fields__subtasks__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__subtasks
    ADD CONSTRAINT issues__fields__subtasks__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__worklog__worklogs__comment__content issues__fields__worklog__worklogs__comment__conten__dlt_id_key1; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__worklog__worklogs__comment__content
    ADD CONSTRAINT issues__fields__worklog__worklogs__comment__conten__dlt_id_key1 UNIQUE (_dlt_id);


--
-- Name: issues__fields__worklog__worklogs__comment__content__content issues__fields__worklog__worklogs__comment__content__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__worklog__worklogs__comment__content__content
    ADD CONSTRAINT issues__fields__worklog__worklogs__comment__content__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__fields__worklog__worklogs issues__fields__worklog__worklogs__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__fields__worklog__worklogs
    ADD CONSTRAINT issues__fields__worklog__worklogs__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__rendered_fields__attachment issues__rendered_fields__attachment__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__rendered_fields__attachment
    ADD CONSTRAINT issues__rendered_fields__attachment__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__rendered_fields__comment__comments issues__rendered_fields__comment__comments__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__rendered_fields__comment__comments
    ADD CONSTRAINT issues__rendered_fields__comment__comments__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: issues__rendered_fields__worklog__worklogs issues__rendered_fields__worklog__worklogs__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.issues__rendered_fields__worklog__worklogs
    ADD CONSTRAINT issues__rendered_fields__worklog__worklogs__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: projects projects__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.projects
    ADD CONSTRAINT projects__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: sprints sprints__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.sprints
    ADD CONSTRAINT sprints__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: users users__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.users
    ADD CONSTRAINT users__dlt_id_key UNIQUE (_dlt_id);


--
-- Name: versions versions__dlt_id_key; Type: CONSTRAINT; Schema: raw_jira; Owner: -
--

ALTER TABLE ONLY raw_jira.versions
    ADD CONSTRAINT versions__dlt_id_key UNIQUE (_dlt_id);


--
-- PostgreSQL database dump complete
--


-- Auto-generated baseline comments for missing objects
COMMENT ON TABLE raw_jira._dlt_loads IS 'Raw Jira object mirrored from source API:  dlt loads.';
COMMENT ON COLUMN raw_jira._dlt_loads.load_id IS 'Raw Jira source field: load id.';
COMMENT ON COLUMN raw_jira._dlt_loads.schema_name IS 'Raw Jira source field: schema name.';
COMMENT ON COLUMN raw_jira._dlt_loads.status IS 'Raw Jira source field: status.';
COMMENT ON COLUMN raw_jira._dlt_loads.inserted_at IS 'Raw Jira source field: inserted at.';
COMMENT ON COLUMN raw_jira._dlt_loads.schema_version_hash IS 'Raw Jira source field: schema version hash.';
COMMENT ON TABLE raw_jira._dlt_pipeline_state IS 'Raw Jira object mirrored from source API:  dlt pipeline state.';
COMMENT ON COLUMN raw_jira._dlt_pipeline_state.version IS 'Raw Jira source field: version.';
COMMENT ON COLUMN raw_jira._dlt_pipeline_state.engine_version IS 'Raw Jira source field: engine version.';
COMMENT ON COLUMN raw_jira._dlt_pipeline_state.pipeline_name IS 'Raw Jira source field: pipeline name.';
COMMENT ON COLUMN raw_jira._dlt_pipeline_state.state IS 'Raw Jira source field: state.';
COMMENT ON COLUMN raw_jira._dlt_pipeline_state.created_at IS 'Raw Jira source field: created at.';
COMMENT ON COLUMN raw_jira._dlt_pipeline_state.version_hash IS 'Raw Jira source field: version hash.';
COMMENT ON TABLE raw_jira._dlt_version IS 'Raw Jira object mirrored from source API:  dlt version.';
COMMENT ON COLUMN raw_jira._dlt_version.version IS 'Raw Jira source field: version.';
COMMENT ON COLUMN raw_jira._dlt_version.engine_version IS 'Raw Jira source field: engine version.';
COMMENT ON COLUMN raw_jira._dlt_version.inserted_at IS 'Raw Jira source field: inserted at.';
COMMENT ON COLUMN raw_jira._dlt_version.schema_name IS 'Raw Jira source field: schema name.';
COMMENT ON COLUMN raw_jira._dlt_version.version_hash IS 'Raw Jira source field: version hash.';
COMMENT ON COLUMN raw_jira._dlt_version.schema IS 'Raw Jira source field: schema.';
COMMENT ON TABLE raw_jira.board_configurations IS 'Raw Jira object mirrored from source API: board configurations.';
COMMENT ON COLUMN raw_jira.board_configurations.board_id IS 'Raw Jira source field: board id.';
COMMENT ON COLUMN raw_jira.board_configurations.board_name IS 'Raw Jira source field: board name.';
COMMENT ON COLUMN raw_jira.board_configurations.board_type IS 'Raw Jira source field: board type.';
COMMENT ON COLUMN raw_jira.board_configurations.project_key IS 'Raw Jira source field: project key.';
COMMENT ON COLUMN raw_jira.board_configurations.columns_config__constraint_type IS 'Raw Jira source field: columns config  constraint type.';
COMMENT ON COLUMN raw_jira.board_configurations.filter_id IS 'Raw Jira source field: filter id.';
COMMENT ON TABLE raw_jira.board_configurations__columns_config__columns IS 'Raw Jira object mirrored from source API: board configurations  columns config  columns.';
COMMENT ON COLUMN raw_jira.board_configurations__columns_config__columns.name IS 'Raw Jira source field: name.';
COMMENT ON TABLE raw_jira.board_configurations__columns_config__columns__statuses IS 'Raw Jira object mirrored from source API: board configurations  columns config  columns  statuses.';
COMMENT ON COLUMN raw_jira.board_configurations__columns_config__columns__statuses.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.board_configurations__columns_config__columns__statuses.self IS 'Raw Jira source field: self.';
COMMENT ON TABLE raw_jira.fields IS 'Raw Jira object mirrored from source API: fields.';
COMMENT ON COLUMN raw_jira.fields.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.fields.key IS 'Raw Jira source field: key.';
COMMENT ON COLUMN raw_jira.fields.name IS 'Raw Jira source field: name.';
COMMENT ON COLUMN raw_jira.fields.untranslated_name IS 'Raw Jira source field: untranslated name.';
COMMENT ON COLUMN raw_jira.fields.custom IS 'Raw Jira source field: custom.';
COMMENT ON COLUMN raw_jira.fields.orderable IS 'Raw Jira source field: orderable.';
COMMENT ON COLUMN raw_jira.fields.navigable IS 'Raw Jira source field: navigable.';
COMMENT ON COLUMN raw_jira.fields.searchable IS 'Raw Jira source field: searchable.';
COMMENT ON COLUMN raw_jira.fields.schema__type IS 'Raw Jira source field: schema  type.';
COMMENT ON COLUMN raw_jira.fields.schema__custom IS 'Raw Jira source field: schema  custom.';
COMMENT ON COLUMN raw_jira.fields.schema__custom_id IS 'Raw Jira source field: schema  custom id.';
COMMENT ON COLUMN raw_jira.fields.schema__items IS 'Raw Jira source field: schema  items.';
COMMENT ON COLUMN raw_jira.fields.schema__system IS 'Raw Jira source field: schema  system.';
COMMENT ON COLUMN raw_jira.fields.scope__type IS 'Raw Jira source field: scope  type.';
COMMENT ON COLUMN raw_jira.fields.scope__project__id IS 'Raw Jira source field: scope  project  id.';
COMMENT ON COLUMN raw_jira.fields.schema__configuration__is_multi IS 'Raw Jira source field: schema  configuration  is multi.';
COMMENT ON COLUMN raw_jira.fields.schema__configuration__com_ata7y9qwtomfieldtypes_atlassian_team IS 'Raw Jira source field: schema  configuration  com ata7y9qwtomfieldtypes atlassian team.';
COMMENT ON TABLE raw_jira.fields__clause_names IS 'Raw Jira object mirrored from source API: fields  clause names.';
COMMENT ON COLUMN raw_jira.fields__clause_names.value IS 'Raw Jira source field: value.';
COMMENT ON TABLE raw_jira.issues IS 'Raw Jira object mirrored from source API: issues.';
COMMENT ON COLUMN raw_jira.issues.expand IS 'Raw Jira source field: expand.';
COMMENT ON COLUMN raw_jira.issues.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues.key IS 'Raw Jira source field: key.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10071 IS 'Raw Jira source field: rendered fields  customfield 10071.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10078 IS 'Raw Jira source field: rendered fields  customfield 10078.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10994 IS 'Raw Jira source field: rendered fields  customfield 10994.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10060 IS 'Raw Jira source field: rendered fields  customfield 10060.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11273 IS 'Raw Jira source field: rendered fields  customfield 11273.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11274 IS 'Raw Jira source field: rendered fields  customfield 11274.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10067 IS 'Raw Jira source field: rendered fields  customfield 10067.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10068 IS 'Raw Jira source field: rendered fields  customfield 10068.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10056 IS 'Raw Jira source field: rendered fields  customfield 10056.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10057 IS 'Raw Jira source field: rendered fields  customfield 10057.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10058 IS 'Raw Jira source field: rendered fields  customfield 10058.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11139 IS 'Raw Jira source field: rendered fields  customfield 11139.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10843 IS 'Raw Jira source field: rendered fields  customfield 10843.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10844 IS 'Raw Jira source field: rendered fields  customfield 10844.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10286 IS 'Raw Jira source field: rendered fields  customfield 10286.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10046 IS 'Raw Jira source field: rendered fields  customfield 10046.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10048 IS 'Raw Jira source field: rendered fields  customfield 10048.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10710 IS 'Raw Jira source field: rendered fields  customfield 10710.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10711 IS 'Raw Jira source field: rendered fields  customfield 10711.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10712 IS 'Raw Jira source field: rendered fields  customfield 10712.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__worklog__start_at IS 'Raw Jira source field: rendered fields  worklog  start at.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__worklog__max_results IS 'Raw Jira source field: rendered fields  worklog  max results.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__worklog__total IS 'Raw Jira source field: rendered fields  worklog  total.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10152 IS 'Raw Jira source field: rendered fields  customfield 10152.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10156 IS 'Raw Jira source field: rendered fields  customfield 10156.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10157 IS 'Raw Jira source field: rendered fields  customfield 10157.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10017 IS 'Raw Jira source field: rendered fields  customfield 10017.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11106 IS 'Raw Jira source field: rendered fields  customfield 11106.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__updated IS 'Raw Jira source field: rendered fields  updated.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__description IS 'Raw Jira source field: rendered fields  description.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11570 IS 'Raw Jira source field: rendered fields  customfield 11570.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__environment IS 'Raw Jira source field: rendered fields  environment.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__comment__self IS 'Raw Jira source field: rendered fields  comment  self.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__comment__max_results IS 'Raw Jira source field: rendered fields  comment  max results.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__comment__total IS 'Raw Jira source field: rendered fields  comment  total.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__comment__start_at IS 'Raw Jira source field: rendered fields  comment  start at.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__statuscategorychangedate IS 'Raw Jira source field: rendered fields  statuscategorychangedate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11091 IS 'Raw Jira source field: rendered fields  customfield 11091.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11093 IS 'Raw Jira source field: rendered fields  customfield 11093.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11095 IS 'Raw Jira source field: rendered fields  customfield 11095.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11080 IS 'Raw Jira source field: rendered fields  customfield 11080.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11081 IS 'Raw Jira source field: rendered fields  customfield 11081.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11082 IS 'Raw Jira source field: rendered fields  customfield 11082.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11083 IS 'Raw Jira source field: rendered fields  customfield 11083.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11088 IS 'Raw Jira source field: rendered fields  customfield 11088.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11089 IS 'Raw Jira source field: rendered fields  customfield 11089.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11638 IS 'Raw Jira source field: rendered fields  customfield 11638.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__created IS 'Raw Jira source field: rendered fields  created.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11074 IS 'Raw Jira source field: rendered fields  customfield 11074.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11077 IS 'Raw Jira source field: rendered fields  customfield 11077.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11078 IS 'Raw Jira source field: rendered fields  customfield 11078.';
COMMENT ON COLUMN raw_jira.issues.changelog__start_at IS 'Raw Jira source field: changelog  start at.';
COMMENT ON COLUMN raw_jira.issues.changelog__max_results IS 'Raw Jira source field: changelog  max results.';
COMMENT ON COLUMN raw_jira.issues.changelog__total IS 'Raw Jira source field: changelog  total.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__id IS 'Raw Jira source field: fields  parent  id.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__key IS 'Raw Jira source field: fields  parent  key.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__self IS 'Raw Jira source field: fields  parent  self.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__summary IS 'Raw Jira source field: fields  parent  fields  summary.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__self IS 'Raw Jira source field: fields  parent  fields  status  self.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__description IS 'Raw Jira source field: fields  parent  fields  status  description.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__icon_url IS 'Raw Jira source field: fields  parent  fields  status  icon url.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__name IS 'Raw Jira source field: fields  parent  fields  status  name.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__id IS 'Raw Jira source field: fields  parent  fields  status  id.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__status_category__self IS 'Raw Jira source field: fields  parent  fields  status  status category  self.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__status_category__id IS 'Raw Jira source field: fields  parent  fields  status  status category  id.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__status_category__key IS 'Raw Jira source field: fields  parent  fields  status  status category  key.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__status_category__color_name IS 'Raw Jira source field: fields  parent  fields  status  status category  color name.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__status__status_category__name IS 'Raw Jira source field: fields  parent  fields  status  status category  name.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__priority__self IS 'Raw Jira source field: fields  parent  fields  priority  self.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__priority__icon_url IS 'Raw Jira source field: fields  parent  fields  priority  icon url.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__priority__name IS 'Raw Jira source field: fields  parent  fields  priority  name.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__priority__id IS 'Raw Jira source field: fields  parent  fields  priority  id.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__self IS 'Raw Jira source field: fields  parent  fields  issuetype  self.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__id IS 'Raw Jira source field: fields  parent  fields  issuetype  id.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__description IS 'Raw Jira source field: fields  parent  fields  issuetype  description.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__icon_url IS 'Raw Jira source field: fields  parent  fields  issuetype  icon url.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__name IS 'Raw Jira source field: fields  parent  fields  issuetype  name.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__subtask IS 'Raw Jira source field: fields  parent  fields  issuetype  subtask.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__avatar_id IS 'Raw Jira source field: fields  parent  fields  issuetype  avatar id.';
COMMENT ON COLUMN raw_jira.issues.fields__parent__fields__issuetype__hierarchy_level IS 'Raw Jira source field: fields  parent  fields  issuetype  hierarchy level.';
COMMENT ON COLUMN raw_jira.issues.fields__status_category__self IS 'Raw Jira source field: fields  status category  self.';
COMMENT ON COLUMN raw_jira.issues.fields__status_category__id IS 'Raw Jira source field: fields  status category  id.';
COMMENT ON COLUMN raw_jira.issues.fields__status_category__key IS 'Raw Jira source field: fields  status category  key.';
COMMENT ON COLUMN raw_jira.issues.fields__status_category__color_name IS 'Raw Jira source field: fields  status category  color name.';
COMMENT ON COLUMN raw_jira.issues.fields__status_category__name IS 'Raw Jira source field: fields  status category  name.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__self IS 'Raw Jira source field: fields  reporter  self.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__account_id IS 'Raw Jira source field: fields  reporter  account id.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__avatar_urls___48x48 IS 'Raw Jira source field: fields  reporter  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__avatar_urls___24x24 IS 'Raw Jira source field: fields  reporter  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__avatar_urls___16x16 IS 'Raw Jira source field: fields  reporter  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__avatar_urls___32x32 IS 'Raw Jira source field: fields  reporter  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__display_name IS 'Raw Jira source field: fields  reporter  display name.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__active IS 'Raw Jira source field: fields  reporter  active.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__time_zone IS 'Raw Jira source field: fields  reporter  time zone.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__account_type IS 'Raw Jira source field: fields  reporter  account type.';
COMMENT ON COLUMN raw_jira.issues.fields__progress__progress IS 'Raw Jira source field: fields  progress  progress.';
COMMENT ON COLUMN raw_jira.issues.fields__progress__total IS 'Raw Jira source field: fields  progress  total.';
COMMENT ON COLUMN raw_jira.issues.fields__votes__self IS 'Raw Jira source field: fields  votes  self.';
COMMENT ON COLUMN raw_jira.issues.fields__votes__votes IS 'Raw Jira source field: fields  votes  votes.';
COMMENT ON COLUMN raw_jira.issues.fields__votes__has_voted IS 'Raw Jira source field: fields  votes  has voted.';
COMMENT ON COLUMN raw_jira.issues.fields__worklog__start_at IS 'Raw Jira source field: fields  worklog  start at.';
COMMENT ON COLUMN raw_jira.issues.fields__worklog__max_results IS 'Raw Jira source field: fields  worklog  max results.';
COMMENT ON COLUMN raw_jira.issues.fields__worklog__total IS 'Raw Jira source field: fields  worklog  total.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__self IS 'Raw Jira source field: fields  issuetype  self.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__id IS 'Raw Jira source field: fields  issuetype  id.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__description IS 'Raw Jira source field: fields  issuetype  description.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__icon_url IS 'Raw Jira source field: fields  issuetype  icon url.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__name IS 'Raw Jira source field: fields  issuetype  name.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__subtask IS 'Raw Jira source field: fields  issuetype  subtask.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__avatar_id IS 'Raw Jira source field: fields  issuetype  avatar id.';
COMMENT ON COLUMN raw_jira.issues.fields__issuetype__hierarchy_level IS 'Raw Jira source field: fields  issuetype  hierarchy level.';
COMMENT ON COLUMN raw_jira.issues.fields__project__self IS 'Raw Jira source field: fields  project  self.';
COMMENT ON COLUMN raw_jira.issues.fields__project__id IS 'Raw Jira source field: fields  project  id.';
COMMENT ON COLUMN raw_jira.issues.fields__project__key IS 'Raw Jira source field: fields  project  key.';
COMMENT ON COLUMN raw_jira.issues.fields__project__name IS 'Raw Jira source field: fields  project  name.';
COMMENT ON COLUMN raw_jira.issues.fields__project__project_type_key IS 'Raw Jira source field: fields  project  project type key.';
COMMENT ON COLUMN raw_jira.issues.fields__project__simplified IS 'Raw Jira source field: fields  project  simplified.';
COMMENT ON COLUMN raw_jira.issues.fields__project__avatar_urls___48x48 IS 'Raw Jira source field: fields  project  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues.fields__project__avatar_urls___24x24 IS 'Raw Jira source field: fields  project  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues.fields__project__avatar_urls___16x16 IS 'Raw Jira source field: fields  project  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues.fields__project__avatar_urls___32x32 IS 'Raw Jira source field: fields  project  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues.fields__watches__self IS 'Raw Jira source field: fields  watches  self.';
COMMENT ON COLUMN raw_jira.issues.fields__watches__watch_count IS 'Raw Jira source field: fields  watches  watch count.';
COMMENT ON COLUMN raw_jira.issues.fields__watches__is_watching IS 'Raw Jira source field: fields  watches  is watching.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10019 IS 'Raw Jira source field: fields  customfield 10019.';
COMMENT ON COLUMN raw_jira.issues.fields__updated IS 'Raw Jira source field: fields  updated.';
COMMENT ON COLUMN raw_jira.issues.fields__summary IS 'Raw Jira source field: fields  summary.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10000 IS 'Raw Jira source field: fields  customfield 10000.';
COMMENT ON COLUMN raw_jira.issues.fields__comment__self IS 'Raw Jira source field: fields  comment  self.';
COMMENT ON COLUMN raw_jira.issues.fields__comment__max_results IS 'Raw Jira source field: fields  comment  max results.';
COMMENT ON COLUMN raw_jira.issues.fields__comment__total IS 'Raw Jira source field: fields  comment  total.';
COMMENT ON COLUMN raw_jira.issues.fields__comment__start_at IS 'Raw Jira source field: fields  comment  start at.';
COMMENT ON COLUMN raw_jira.issues.fields__statuscategorychangedate IS 'Raw Jira source field: fields  statuscategorychangedate.';
COMMENT ON COLUMN raw_jira.issues.fields__priority__self IS 'Raw Jira source field: fields  priority  self.';
COMMENT ON COLUMN raw_jira.issues.fields__priority__icon_url IS 'Raw Jira source field: fields  priority  icon url.';
COMMENT ON COLUMN raw_jira.issues.fields__priority__name IS 'Raw Jira source field: fields  priority  name.';
COMMENT ON COLUMN raw_jira.issues.fields__priority__id IS 'Raw Jira source field: fields  priority  id.';
COMMENT ON COLUMN raw_jira.issues.fields__status__self IS 'Raw Jira source field: fields  status  self.';
COMMENT ON COLUMN raw_jira.issues.fields__status__description IS 'Raw Jira source field: fields  status  description.';
COMMENT ON COLUMN raw_jira.issues.fields__status__icon_url IS 'Raw Jira source field: fields  status  icon url.';
COMMENT ON COLUMN raw_jira.issues.fields__status__name IS 'Raw Jira source field: fields  status  name.';
COMMENT ON COLUMN raw_jira.issues.fields__status__id IS 'Raw Jira source field: fields  status  id.';
COMMENT ON COLUMN raw_jira.issues.fields__status__status_category__self IS 'Raw Jira source field: fields  status  status category  self.';
COMMENT ON COLUMN raw_jira.issues.fields__status__status_category__id IS 'Raw Jira source field: fields  status  status category  id.';
COMMENT ON COLUMN raw_jira.issues.fields__status__status_category__key IS 'Raw Jira source field: fields  status  status category  key.';
COMMENT ON COLUMN raw_jira.issues.fields__status__status_category__color_name IS 'Raw Jira source field: fields  status  status category  color name.';
COMMENT ON COLUMN raw_jira.issues.fields__status__status_category__name IS 'Raw Jira source field: fields  status  status category  name.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__self IS 'Raw Jira source field: fields  creator  self.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__account_id IS 'Raw Jira source field: fields  creator  account id.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__avatar_urls___48x48 IS 'Raw Jira source field: fields  creator  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__avatar_urls___24x24 IS 'Raw Jira source field: fields  creator  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__avatar_urls___16x16 IS 'Raw Jira source field: fields  creator  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__avatar_urls___32x32 IS 'Raw Jira source field: fields  creator  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__display_name IS 'Raw Jira source field: fields  creator  display name.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__active IS 'Raw Jira source field: fields  creator  active.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__time_zone IS 'Raw Jira source field: fields  creator  time zone.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__account_type IS 'Raw Jira source field: fields  creator  account type.';
COMMENT ON COLUMN raw_jira.issues.fields__aggregateprogress__progress IS 'Raw Jira source field: fields  aggregateprogress  progress.';
COMMENT ON COLUMN raw_jira.issues.fields__aggregateprogress__total IS 'Raw Jira source field: fields  aggregateprogress  total.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10201 IS 'Raw Jira source field: fields  customfield 10201.';
COMMENT ON COLUMN raw_jira.issues.fields__workratio IS 'Raw Jira source field: fields  workratio.';
COMMENT ON COLUMN raw_jira.issues.fields__issuerestriction__should_display IS 'Raw Jira source field: fields  issuerestriction  should display.';
COMMENT ON COLUMN raw_jira.issues.fields__created IS 'Raw Jira source field: fields  created.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__last_viewed IS 'Raw Jira source field: rendered fields  last viewed.';
COMMENT ON COLUMN raw_jira.issues.fields__last_viewed IS 'Raw Jira source field: fields  last viewed.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__self IS 'Raw Jira source field: fields  assignee  self.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__account_id IS 'Raw Jira source field: fields  assignee  account id.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__email_address IS 'Raw Jira source field: fields  assignee  email address.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__avatar_urls___48x48 IS 'Raw Jira source field: fields  assignee  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__avatar_urls___24x24 IS 'Raw Jira source field: fields  assignee  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__avatar_urls___16x16 IS 'Raw Jira source field: fields  assignee  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__avatar_urls___32x32 IS 'Raw Jira source field: fields  assignee  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__display_name IS 'Raw Jira source field: fields  assignee  display name.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__active IS 'Raw Jira source field: fields  assignee  active.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__time_zone IS 'Raw Jira source field: fields  assignee  time zone.';
COMMENT ON COLUMN raw_jira.issues.fields__assignee__account_type IS 'Raw Jira source field: fields  assignee  account type.';
COMMENT ON COLUMN raw_jira.issues.fields__reporter__email_address IS 'Raw Jira source field: fields  reporter  email address.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10036 IS 'Raw Jira source field: fields  customfield 10036.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11237 IS 'Raw Jira source field: fields  customfield 11237.';
COMMENT ON COLUMN raw_jira.issues.fields__description__type IS 'Raw Jira source field: fields  description  type.';
COMMENT ON COLUMN raw_jira.issues.fields__description__version IS 'Raw Jira source field: fields  description  version.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10014 IS 'Raw Jira source field: fields  customfield 10014.';
COMMENT ON COLUMN raw_jira.issues.fields__creator__email_address IS 'Raw Jira source field: fields  creator  email address.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10011 IS 'Raw Jira source field: rendered fields  customfield 10011.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10013 IS 'Raw Jira source field: rendered fields  customfield 10013.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10017 IS 'Raw Jira source field: fields  customfield 10017.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10012__self IS 'Raw Jira source field: fields  customfield 10012  self.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10012__value IS 'Raw Jira source field: fields  customfield 10012  value.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10012__id IS 'Raw Jira source field: fields  customfield 10012  id.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10013 IS 'Raw Jira source field: fields  customfield 10013.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__resolutiondate IS 'Raw Jira source field: rendered fields  resolutiondate.';
COMMENT ON COLUMN raw_jira.issues.fields__resolution__self IS 'Raw Jira source field: fields  resolution  self.';
COMMENT ON COLUMN raw_jira.issues.fields__resolution__id IS 'Raw Jira source field: fields  resolution  id.';
COMMENT ON COLUMN raw_jira.issues.fields__resolution__description IS 'Raw Jira source field: fields  resolution  description.';
COMMENT ON COLUMN raw_jira.issues.fields__resolution__name IS 'Raw Jira source field: fields  resolution  name.';
COMMENT ON COLUMN raw_jira.issues.fields__resolutiondate IS 'Raw Jira source field: fields  resolutiondate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10015 IS 'Raw Jira source field: rendered fields  customfield 10015.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10015 IS 'Raw Jira source field: fields  customfield 10015.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__duedate IS 'Raw Jira source field: rendered fields  duedate.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10011 IS 'Raw Jira source field: fields  customfield 10011.';
COMMENT ON COLUMN raw_jira.issues.fields__duedate IS 'Raw Jira source field: fields  duedate.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10016 IS 'Raw Jira source field: fields  customfield 10016.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11041__self IS 'Raw Jira source field: fields  customfield 11041  self.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11041__value IS 'Raw Jira source field: fields  customfield 11041  value.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11041__id IS 'Raw Jira source field: fields  customfield 11041  id.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10050__error_message IS 'Raw Jira source field: fields  customfield 10050  error message.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10050__i18n_error_message__i18n_key IS 'Raw Jira source field: fields  customfield 10050  i18n error message  i18n key.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10049__error_message IS 'Raw Jira source field: fields  customfield 10049  error message.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10049__i18n_error_message__i18n_key IS 'Raw Jira source field: fields  customfield 10049  i18n error message  i18n key.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10680__error_message IS 'Raw Jira source field: fields  customfield 10680  error message.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10680__i18n_error_message__i18n_key IS 'Raw Jira source field: fields  customfield 10680  i18n error message  i18n key.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__aggregatetimeoriginalestimate IS 'Raw Jira source field: rendered fields  aggregatetimeoriginalestimate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timeoriginalestimate IS 'Raw Jira source field: rendered fields  timeoriginalestimate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timetracking__original_estimate IS 'Raw Jira source field: rendered fields  timetracking  original estimate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timetracking__remaining_estimate IS 'Raw Jira source field: rendered fields  timetracking  remaining estimate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timetracking__original_estimate_seconds IS 'Raw Jira source field: rendered fields  timetracking  original estimate seconds.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timetracking__remaining_estimate_seconds IS 'Raw Jira source field: rendered fields  timetracking  remaining estimate seconds.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timeestimate IS 'Raw Jira source field: rendered fields  timeestimate.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__aggregatetimeestimate IS 'Raw Jira source field: rendered fields  aggregatetimeestimate.';
COMMENT ON COLUMN raw_jira.issues.fields__aggregatetimeoriginalestimate IS 'Raw Jira source field: fields  aggregatetimeoriginalestimate.';
COMMENT ON COLUMN raw_jira.issues.fields__timeoriginalestimate IS 'Raw Jira source field: fields  timeoriginalestimate.';
COMMENT ON COLUMN raw_jira.issues.fields__timetracking__original_estimate IS 'Raw Jira source field: fields  timetracking  original estimate.';
COMMENT ON COLUMN raw_jira.issues.fields__timetracking__remaining_estimate IS 'Raw Jira source field: fields  timetracking  remaining estimate.';
COMMENT ON COLUMN raw_jira.issues.fields__timetracking__original_estimate_seconds IS 'Raw Jira source field: fields  timetracking  original estimate seconds.';
COMMENT ON COLUMN raw_jira.issues.fields__timetracking__remaining_estimate_seconds IS 'Raw Jira source field: fields  timetracking  remaining estimate seconds.';
COMMENT ON COLUMN raw_jira.issues.fields__timeestimate IS 'Raw Jira source field: fields  timeestimate.';
COMMENT ON COLUMN raw_jira.issues.fields__aggregatetimeestimate IS 'Raw Jira source field: fields  aggregatetimeestimate.';
COMMENT ON COLUMN raw_jira.issues.fields__progress__percent IS 'Raw Jira source field: fields  progress  percent.';
COMMENT ON COLUMN raw_jira.issues.fields__aggregateprogress__percent IS 'Raw Jira source field: fields  aggregateprogress  percent.';
COMMENT ON COLUMN raw_jira.issues.fields__environment__type IS 'Raw Jira source field: fields  environment  type.';
COMMENT ON COLUMN raw_jira.issues.fields__environment__version IS 'Raw Jira source field: fields  environment  version.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10197 IS 'Raw Jira source field: rendered fields  customfield 10197.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10186 IS 'Raw Jira source field: rendered fields  customfield 10186.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10610 IS 'Raw Jira source field: rendered fields  customfield 10610.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10611 IS 'Raw Jira source field: rendered fields  customfield 10611.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10612 IS 'Raw Jira source field: rendered fields  customfield 10612.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10224 IS 'Raw Jira source field: rendered fields  customfield 10224.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10331 IS 'Raw Jira source field: rendered fields  customfield 10331.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10332 IS 'Raw Jira source field: rendered fields  customfield 10332.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_10415 IS 'Raw Jira source field: rendered fields  customfield 10415.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10291__self IS 'Raw Jira source field: fields  customfield 10291  self.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10291__value IS 'Raw Jira source field: fields  customfield 10291  value.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10291__id IS 'Raw Jira source field: fields  customfield 10291  id.';
COMMENT ON COLUMN raw_jira.issues.fields__project__project_category__self IS 'Raw Jira source field: fields  project  project category  self.';
COMMENT ON COLUMN raw_jira.issues.fields__project__project_category__id IS 'Raw Jira source field: fields  project  project category  id.';
COMMENT ON COLUMN raw_jira.issues.fields__project__project_category__description IS 'Raw Jira source field: fields  project  project category  description.';
COMMENT ON COLUMN raw_jira.issues.fields__project__project_category__name IS 'Raw Jira source field: fields  project  project category  name.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__self IS 'Raw Jira source field: fields  customfield 10336  self.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__account_id IS 'Raw Jira source field: fields  customfield 10336  account id.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__email_address IS 'Raw Jira source field: fields  customfield 10336  email address.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__avatar_urls___48x48 IS 'Raw Jira source field: fields  customfield 10336  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__avatar_urls___24x24 IS 'Raw Jira source field: fields  customfield 10336  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__avatar_urls___16x16 IS 'Raw Jira source field: fields  customfield 10336  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__avatar_urls___32x32 IS 'Raw Jira source field: fields  customfield 10336  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__display_name IS 'Raw Jira source field: fields  customfield 10336  display name.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__active IS 'Raw Jira source field: fields  customfield 10336  active.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__time_zone IS 'Raw Jira source field: fields  customfield 10336  time zone.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10336__account_type IS 'Raw Jira source field: fields  customfield 10336  account type.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11468__error_message IS 'Raw Jira source field: fields  customfield 11468  error message.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11468__i18n_error_message__i18n_key IS 'Raw Jira source field: fields  customfield 11468  i18n error message  i18n key.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10941__self IS 'Raw Jira source field: fields  customfield 10941  self.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10941__value IS 'Raw Jira source field: fields  customfield 10941  value.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10941__id IS 'Raw Jira source field: fields  customfield 10941  id.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11435__self IS 'Raw Jira source field: fields  customfield 11435  self.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11435__value IS 'Raw Jira source field: fields  customfield 11435  value.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11435__id IS 'Raw Jira source field: fields  customfield 11435  id.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__id IS 'Raw Jira source field: fields  customfield 10001  id.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__name IS 'Raw Jira source field: fields  customfield 10001  name.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__avatar_url IS 'Raw Jira source field: fields  customfield 10001  avatar url.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__is_visible IS 'Raw Jira source field: fields  customfield 10001  is visible.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__is_verified IS 'Raw Jira source field: fields  customfield 10001  is verified.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__title IS 'Raw Jira source field: fields  customfield 10001  title.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_10001__is_shared IS 'Raw Jira source field: fields  customfield 10001  is shared.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11739 IS 'Raw Jira source field: fields  customfield 11739.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__customfield_11739 IS 'Raw Jira source field: rendered fields  customfield 11739.';
COMMENT ON COLUMN raw_jira.issues.fields__aggregatetimespent IS 'Raw Jira source field: fields  aggregatetimespent.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__aggregatetimespent IS 'Raw Jira source field: rendered fields  aggregatetimespent.';
COMMENT ON COLUMN raw_jira.issues.fields__timespent IS 'Raw Jira source field: fields  timespent.';
COMMENT ON COLUMN raw_jira.issues.fields__timetracking__time_spent IS 'Raw Jira source field: fields  timetracking  time spent.';
COMMENT ON COLUMN raw_jira.issues.fields__timetracking__time_spent_seconds IS 'Raw Jira source field: fields  timetracking  time spent seconds.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timespent IS 'Raw Jira source field: rendered fields  timespent.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timetracking__time_spent IS 'Raw Jira source field: rendered fields  timetracking  time spent.';
COMMENT ON COLUMN raw_jira.issues.rendered_fields__timetracking__time_spent_seconds IS 'Raw Jira source field: rendered fields  timetracking  time spent seconds.';
COMMENT ON COLUMN raw_jira.issues.fields__customfield_11740 IS 'Raw Jira source field: fields  customfield 11740.';
COMMENT ON TABLE raw_jira.issues__changelog__histories IS 'Raw Jira object mirrored from source API: issues  changelog  histories.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON TABLE raw_jira.issues__changelog__histories__items IS 'Raw Jira object mirrored from source API: issues  changelog  histories  items.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.field IS 'Raw Jira source field: field.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.fieldtype IS 'Raw Jira source field: fieldtype.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.to IS 'Raw Jira source field: to.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.to_string IS 'Raw Jira source field: to string.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.field_id IS 'Raw Jira source field: field id.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.from_string IS 'Raw Jira source field: from string.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.from IS 'Raw Jira source field: from.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.tmp_to_account_id IS 'Raw Jira source field: tmp to account id.';
COMMENT ON TABLE raw_jira.issues__fields__attachment IS 'Raw Jira object mirrored from source API: issues  fields  attachment.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.filename IS 'Raw Jira source field: filename.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.size IS 'Raw Jira source field: size.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.mime_type IS 'Raw Jira source field: mime type.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.content IS 'Raw Jira source field: content.';
COMMENT ON COLUMN raw_jira.issues__fields__attachment.thumbnail IS 'Raw Jira source field: thumbnail.';
COMMENT ON TABLE raw_jira.issues__fields__comment__comm3dzdeqent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  comm3dzdeqent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comm3dzdeqent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commak4pdqt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commak4pdqt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__access_level IS 'Raw Jira source field: attrs  access level.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__width__v_double IS 'Raw Jira source field: attrs  width  v double.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commak4pdqt__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commasbvjqent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  commasbvjqent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commasbvjqent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commbtoy5wt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commbtoy5wt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commbtoy5wt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commbtoy5wt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commdhejxqent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  commdhejxqent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commdhejxqent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commdhejxqent__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commelqwmgt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commelqwmgt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commelqwmgt__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON TABLE raw_jira.issues__fields__comment__comments IS 'Raw Jira object mirrored from source API: issues  fields  comment  comments.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.body__type IS 'Raw Jira source field: body  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.body__version IS 'Raw Jira source field: body  version.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__self IS 'Raw Jira source field: update author  self.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__account_id IS 'Raw Jira source field: update author  account id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__email_address IS 'Raw Jira source field: update author  email address.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__avatar_urls___48x48 IS 'Raw Jira source field: update author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__avatar_urls___24x24 IS 'Raw Jira source field: update author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__avatar_urls___16x16 IS 'Raw Jira source field: update author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__avatar_urls___32x32 IS 'Raw Jira source field: update author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__display_name IS 'Raw Jira source field: update author  display name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__active IS 'Raw Jira source field: update author  active.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__time_zone IS 'Raw Jira source field: update author  time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.update_author__account_type IS 'Raw Jira source field: update author  account type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.updated IS 'Raw Jira source field: updated.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments.jsd_public IS 'Raw Jira source field: jsd public.';
COMMENT ON TABLE raw_jira.issues__fields__comment__comments__body__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  comments  body  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__level IS 'Raw Jira source field: attrs  level.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__language IS 'Raw Jira source field: attrs  language.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__is_number_column_enabled IS 'Raw Jira source field: attrs  is number column enabled.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__width__v_double IS 'Raw Jira source field: attrs  width  v double.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content.attrs__panel_type IS 'Raw Jira source field: attrs  panel type.';
COMMENT ON TABLE raw_jira.issues__fields__comment__comments__body__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  comments  body  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__access_level IS 'Raw Jira source field: attrs  access level.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__comments__body__content__content.attrs__state IS 'Raw Jira source field: attrs  state.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commfgqtowent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  commfgqtowent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commfgqtowent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commfgqtowent__content__content__marks.attrs__size IS 'Raw Jira source field: attrs  size.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commfgqtowent__content__content__marks.attrs__color IS 'Raw Jira source field: attrs  color.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commkwmv2at__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commkwmv2at  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commkwmv2at__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commkwmv2at__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commkwmv2at__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commkwmv2at__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commlura1aent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  commlura1aent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commlura1aent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commnjpp9qt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commnjpp9qt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commnjpp9qt__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commutqfnqy__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commutqfnqy  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__background IS 'Raw Jira source field: attrs  background.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__width__v_double IS 'Raw Jira source field: attrs  width  v double.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commutqfnqy__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commvqfaaaent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  commvqfaaaent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commvqfaaaent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  comment  commw2ps0wody  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks.attrs__color IS 'Raw Jira source field: attrs  color.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commyvyajqt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  comment  commyvyajqt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commyvyajqt__content__content__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON TABLE raw_jira.issues__fields__comment__commzmilvgnt__content__attrs__colwidth IS 'Raw Jira object mirrored from source API: issues  fields  comment  commzmilvgnt  content  attrs  colwidth.';
COMMENT ON COLUMN raw_jira.issues__fields__comment__commzmilvgnt__content__attrs__colwidth.value IS 'Raw Jira source field: value.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10020 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10020.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.name IS 'Raw Jira source field: name.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.state IS 'Raw Jira source field: state.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.board_id IS 'Raw Jira source field: board id.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.goal IS 'Raw Jira source field: goal.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.start_date IS 'Raw Jira source field: start date.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.end_date IS 'Raw Jira source field: end date.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.complete_date IS 'Raw Jira source field: complete date.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10021 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10021.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10021.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10021.value IS 'Raw Jira source field: value.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10021.id IS 'Raw Jira source field: id.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10025 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10025.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10025.id IS 'Raw Jira source field: id.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10253 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10253.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10253.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10253.value IS 'Raw Jira source field: value.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10253.id IS 'Raw Jira source field: id.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10254 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10254.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10254.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10254.value IS 'Raw Jira source field: value.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10254.id IS 'Raw Jira source field: id.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10309 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10309.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.account_id IS 'Raw Jira source field: account id.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.email_address IS 'Raw Jira source field: email address.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.avatar_urls___48x48 IS 'Raw Jira source field: avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.avatar_urls___24x24 IS 'Raw Jira source field: avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.avatar_urls___16x16 IS 'Raw Jira source field: avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.avatar_urls___32x32 IS 'Raw Jira source field: avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.display_name IS 'Raw Jira source field: display name.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.active IS 'Raw Jira source field: active.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.time_zone IS 'Raw Jira source field: time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10309.account_type IS 'Raw Jira source field: account type.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10311 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10311.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.account_id IS 'Raw Jira source field: account id.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.email_address IS 'Raw Jira source field: email address.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.avatar_urls___48x48 IS 'Raw Jira source field: avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.avatar_urls___24x24 IS 'Raw Jira source field: avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.avatar_urls___16x16 IS 'Raw Jira source field: avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.avatar_urls___32x32 IS 'Raw Jira source field: avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.display_name IS 'Raw Jira source field: display name.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.active IS 'Raw Jira source field: active.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.time_zone IS 'Raw Jira source field: time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10311.account_type IS 'Raw Jira source field: account type.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_10327 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 10327.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.account_id IS 'Raw Jira source field: account id.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.email_address IS 'Raw Jira source field: email address.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.avatar_urls___48x48 IS 'Raw Jira source field: avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.avatar_urls___24x24 IS 'Raw Jira source field: avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.avatar_urls___16x16 IS 'Raw Jira source field: avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.avatar_urls___32x32 IS 'Raw Jira source field: avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.display_name IS 'Raw Jira source field: display name.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.active IS 'Raw Jira source field: active.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.time_zone IS 'Raw Jira source field: time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10327.account_type IS 'Raw Jira source field: account type.';
COMMENT ON TABLE raw_jira.issues__fields__customfield_11039 IS 'Raw Jira object mirrored from source API: issues  fields  customfield 11039.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_11039.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_11039.value IS 'Raw Jira source field: value.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_11039.id IS 'Raw Jira source field: id.';
COMMENT ON TABLE raw_jira.issues__fields__description__1b8wfwt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  1b8wfwt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__1b8wfwt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__1b8wfwt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__fields__description__4my9qgent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  4my9qgent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__4my9qgent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__4my9qgent__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON TABLE raw_jira.issues__fields__description__ahypbqent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  ahypbqent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ahypbqent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ahypbqent__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON TABLE raw_jira.issues__fields__description__content IS 'Raw Jira object mirrored from source API: issues  fields  description  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__level IS 'Raw Jira source field: attrs  level.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__is_number_column_enabled IS 'Raw Jira source field: attrs  is number column enabled.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__language IS 'Raw Jira source field: attrs  language.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__panel_type IS 'Raw Jira source field: attrs  panel type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__width__v_double IS 'Raw Jira source field: attrs  width  v double.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__title IS 'Raw Jira source field: attrs  title.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__datasource__id IS 'Raw Jira source field: attrs  datasource  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__datasource__parameters__cloud_id IS 'Raw Jira source field: attrs  datasource  parameters  cloud id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content.attrs__datasource__parameters__jql IS 'Raw Jira source field: attrs  datasource  parameters  jql.';
COMMENT ON TABLE raw_jira.issues__fields__description__content__attrs__datasource__views IS 'Raw Jira object mirrored from source API: issues  fields  description  content  attrs  datasource  views.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__attrs__datasource__views.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__description__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__access_level IS 'Raw Jira source field: attrs  access level.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__state IS 'Raw Jira source field: attrs  state.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON TABLE raw_jira.issues__fields__description__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__language IS 'Raw Jira source field: attrs  language.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__background IS 'Raw Jira source field: attrs  background.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__width__v_double IS 'Raw Jira source field: attrs  width  v double.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON TABLE raw_jira.issues__fields__description__content__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  content  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__access_level IS 'Raw Jira source field: attrs  access level.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON TABLE raw_jira.issues__fields__description__content__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  content  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__description__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__marks.attrs__color IS 'Raw Jira source field: attrs  color.';
COMMENT ON COLUMN raw_jira.issues__fields__description__content__content__marks.attrs__size IS 'Raw Jira source field: attrs  size.';
COMMENT ON TABLE raw_jira.issues__fields__description__cxb90gt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  cxb90gt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__width_type IS 'Raw Jira source field: attrs  width type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__short_name IS 'Raw Jira source field: attrs  short name.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cxb90gt__content__content__content.attrs__text IS 'Raw Jira source field: attrs  text.';
COMMENT ON TABLE raw_jira.issues__fields__description__cywg2aent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  cywg2aent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__cywg2aent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__description__ejpj8wt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  ejpj8wt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ejpj8wt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ejpj8wt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__fields__description__g2calqt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  g2calqt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g2calqt__content__content__content.attrs__order IS 'Raw Jira source field: attrs  order.';
COMMENT ON TABLE raw_jira.issues__fields__description__g8erbqent__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  g8erbqent  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g8erbqent__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g8erbqent__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON COLUMN raw_jira.issues__fields__description__g8erbqent__content__content__marks.attrs__color IS 'Raw Jira source field: attrs  color.';
COMMENT ON TABLE raw_jira.issues__fields__description__ihgkwat__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  ihgkwat  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ihgkwat__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ihgkwat__content__content__content.attrs__layout IS 'Raw Jira source field: attrs  layout.';
COMMENT ON COLUMN raw_jira.issues__fields__description__ihgkwat__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__fields__description__jwtu1went__content__content__marks IS 'Raw Jira object mirrored from source API: issues  fields  description  jwtu1went  content  content  marks.';
COMMENT ON COLUMN raw_jira.issues__fields__description__jwtu1went__content__content__marks.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__jwtu1went__content__content__marks.attrs__href IS 'Raw Jira source field: attrs  href.';
COMMENT ON COLUMN raw_jira.issues__fields__description__jwtu1went__content__content__marks.attrs__size IS 'Raw Jira source field: attrs  size.';
COMMENT ON COLUMN raw_jira.issues__fields__description__jwtu1went__content__content__marks.attrs__color IS 'Raw Jira source field: attrs  color.';
COMMENT ON TABLE raw_jira.issues__fields__description__nkeuxw__views__properties__columns IS 'Raw Jira object mirrored from source API: issues  fields  description  nkeuxw  views  properties  columns.';
COMMENT ON COLUMN raw_jira.issues__fields__description__nkeuxw__views__properties__columns.key IS 'Raw Jira source field: key.';
COMMENT ON COLUMN raw_jira.issues__fields__description__nkeuxw__views__properties__columns.width IS 'Raw Jira source field: width.';
COMMENT ON TABLE raw_jira.issues__fields__description__nnkbewt__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  nnkbewt  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__nnkbewt__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__nnkbewt__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__fields__description__t8qrkat__content__content__content IS 'Raw Jira object mirrored from source API: issues  fields  description  t8qrkat  content  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__type IS 'Raw Jira source field: attrs  type.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__id IS 'Raw Jira source field: attrs  id.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__alt IS 'Raw Jira source field: attrs  alt.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__collection IS 'Raw Jira source field: attrs  collection.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__height IS 'Raw Jira source field: attrs  height.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__width IS 'Raw Jira source field: attrs  width.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON COLUMN raw_jira.issues__fields__description__t8qrkat__content__content__content.attrs__url IS 'Raw Jira source field: attrs  url.';
COMMENT ON TABLE raw_jira.issues__fields__environment__content IS 'Raw Jira object mirrored from source API: issues  fields  environment  content.';
COMMENT ON COLUMN raw_jira.issues__fields__environment__content.type IS 'Raw Jira source field: type.';
COMMENT ON TABLE raw_jira.issues__fields__environment__content__content IS 'Raw Jira object mirrored from source API: issues  fields  environment  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__environment__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__environment__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__fields__fix_versions IS 'Raw Jira object mirrored from source API: issues  fields  fix versions.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.description IS 'Raw Jira source field: description.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.name IS 'Raw Jira source field: name.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.archived IS 'Raw Jira source field: archived.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.released IS 'Raw Jira source field: released.';
COMMENT ON COLUMN raw_jira.issues__fields__fix_versions.release_date IS 'Raw Jira source field: release date.';
COMMENT ON TABLE raw_jira.issues__fields__issuelinks IS 'Raw Jira object mirrored from source API: issues  fields  issuelinks.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.type__id IS 'Raw Jira source field: type  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.type__name IS 'Raw Jira source field: type  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.type__inward IS 'Raw Jira source field: type  inward.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.type__outward IS 'Raw Jira source field: type  outward.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.type__self IS 'Raw Jira source field: type  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__id IS 'Raw Jira source field: outward issue  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__key IS 'Raw Jira source field: outward issue  key.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__self IS 'Raw Jira source field: outward issue  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__summary IS 'Raw Jira source field: outward issue  fields  summary.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__self IS 'Raw Jira source field: outward issue  fields  status  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__description IS 'Raw Jira source field: outward issue  fields  status  description.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__icon_url IS 'Raw Jira source field: outward issue  fields  status  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__name IS 'Raw Jira source field: outward issue  fields  status  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__id IS 'Raw Jira source field: outward issue  fields  status  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__status_category__self IS 'Raw Jira source field: outward issue  fields  status  status category  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__status_category__id IS 'Raw Jira source field: outward issue  fields  status  status category  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__status_category__key IS 'Raw Jira source field: outward issue  fields  status  status category  key.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__status_category__color_name IS 'Raw Jira source field: outward issue  fields  status  status category  color name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__status__status_category__name IS 'Raw Jira source field: outward issue  fields  status  status category  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__priority__self IS 'Raw Jira source field: outward issue  fields  priority  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__priority__icon_url IS 'Raw Jira source field: outward issue  fields  priority  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__priority__name IS 'Raw Jira source field: outward issue  fields  priority  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__priority__id IS 'Raw Jira source field: outward issue  fields  priority  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__self IS 'Raw Jira source field: outward issue  fields  issuetype  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__id IS 'Raw Jira source field: outward issue  fields  issuetype  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__description IS 'Raw Jira source field: outward issue  fields  issuetype  description.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__icon_url IS 'Raw Jira source field: outward issue  fields  issuetype  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__name IS 'Raw Jira source field: outward issue  fields  issuetype  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__subtask IS 'Raw Jira source field: outward issue  fields  issuetype  subtask.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__avatar_id IS 'Raw Jira source field: outward issue  fields  issuetype  avatar id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__hierarchy_level IS 'Raw Jira source field: outward issue  fields  issuetype  hierarchy level.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__id IS 'Raw Jira source field: inward issue  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__key IS 'Raw Jira source field: inward issue  key.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__self IS 'Raw Jira source field: inward issue  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__summary IS 'Raw Jira source field: inward issue  fields  summary.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__self IS 'Raw Jira source field: inward issue  fields  status  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__description IS 'Raw Jira source field: inward issue  fields  status  description.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__icon_url IS 'Raw Jira source field: inward issue  fields  status  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__name IS 'Raw Jira source field: inward issue  fields  status  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__id IS 'Raw Jira source field: inward issue  fields  status  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__status_category__self IS 'Raw Jira source field: inward issue  fields  status  status category  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__status_category__id IS 'Raw Jira source field: inward issue  fields  status  status category  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__status_category__key IS 'Raw Jira source field: inward issue  fields  status  status category  key.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__status_category__color_name IS 'Raw Jira source field: inward issue  fields  status  status category  color name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__status__status_category__name IS 'Raw Jira source field: inward issue  fields  status  status category  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__priority__self IS 'Raw Jira source field: inward issue  fields  priority  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__priority__icon_url IS 'Raw Jira source field: inward issue  fields  priority  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__priority__name IS 'Raw Jira source field: inward issue  fields  priority  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__priority__id IS 'Raw Jira source field: inward issue  fields  priority  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__self IS 'Raw Jira source field: inward issue  fields  issuetype  self.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__id IS 'Raw Jira source field: inward issue  fields  issuetype  id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__description IS 'Raw Jira source field: inward issue  fields  issuetype  description.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__icon_url IS 'Raw Jira source field: inward issue  fields  issuetype  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__name IS 'Raw Jira source field: inward issue  fields  issuetype  name.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__subtask IS 'Raw Jira source field: inward issue  fields  issuetype  subtask.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__avatar_id IS 'Raw Jira source field: inward issue  fields  issuetype  avatar id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__hierarchy_level IS 'Raw Jira source field: inward issue  fields  issuetype  hierarchy level.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.outward_issue__fields__issuetype__entity_id IS 'Raw Jira source field: outward issue  fields  issuetype  entity id.';
COMMENT ON COLUMN raw_jira.issues__fields__issuelinks.inward_issue__fields__issuetype__entity_id IS 'Raw Jira source field: inward issue  fields  issuetype  entity id.';
COMMENT ON TABLE raw_jira.issues__fields__labels IS 'Raw Jira object mirrored from source API: issues  fields  labels.';
COMMENT ON COLUMN raw_jira.issues__fields__labels.value IS 'Raw Jira source field: value.';
COMMENT ON TABLE raw_jira.issues__fields__subtasks IS 'Raw Jira object mirrored from source API: issues  fields  subtasks.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.key IS 'Raw Jira source field: key.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__summary IS 'Raw Jira source field: fields  summary.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__self IS 'Raw Jira source field: fields  status  self.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__description IS 'Raw Jira source field: fields  status  description.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__icon_url IS 'Raw Jira source field: fields  status  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__name IS 'Raw Jira source field: fields  status  name.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__id IS 'Raw Jira source field: fields  status  id.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__status_category__self IS 'Raw Jira source field: fields  status  status category  self.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__status_category__id IS 'Raw Jira source field: fields  status  status category  id.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__status_category__key IS 'Raw Jira source field: fields  status  status category  key.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__status_category__color_name IS 'Raw Jira source field: fields  status  status category  color name.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__status__status_category__name IS 'Raw Jira source field: fields  status  status category  name.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__priority__self IS 'Raw Jira source field: fields  priority  self.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__priority__icon_url IS 'Raw Jira source field: fields  priority  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__priority__name IS 'Raw Jira source field: fields  priority  name.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__priority__id IS 'Raw Jira source field: fields  priority  id.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__self IS 'Raw Jira source field: fields  issuetype  self.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__id IS 'Raw Jira source field: fields  issuetype  id.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__description IS 'Raw Jira source field: fields  issuetype  description.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__icon_url IS 'Raw Jira source field: fields  issuetype  icon url.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__name IS 'Raw Jira source field: fields  issuetype  name.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__subtask IS 'Raw Jira source field: fields  issuetype  subtask.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__avatar_id IS 'Raw Jira source field: fields  issuetype  avatar id.';
COMMENT ON COLUMN raw_jira.issues__fields__subtasks.fields__issuetype__hierarchy_level IS 'Raw Jira source field: fields  issuetype  hierarchy level.';
COMMENT ON TABLE raw_jira.issues__fields__worklog__worklogs IS 'Raw Jira object mirrored from source API: issues  fields  worklog  worklogs.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.updated IS 'Raw Jira source field: updated.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.started IS 'Raw Jira source field: started.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.time_spent IS 'Raw Jira source field: time spent.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.time_spent_seconds IS 'Raw Jira source field: time spent seconds.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.issue_id IS 'Raw Jira source field: issue id.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__self IS 'Raw Jira source field: update author  self.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__account_id IS 'Raw Jira source field: update author  account id.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__email_address IS 'Raw Jira source field: update author  email address.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__display_name IS 'Raw Jira source field: update author  display name.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__active IS 'Raw Jira source field: update author  active.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__time_zone IS 'Raw Jira source field: update author  time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__account_type IS 'Raw Jira source field: update author  account type.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__avatar_urls___48x48 IS 'Raw Jira source field: update author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__avatar_urls___24x24 IS 'Raw Jira source field: update author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__avatar_urls___16x16 IS 'Raw Jira source field: update author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.update_author__avatar_urls___32x32 IS 'Raw Jira source field: update author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.comment__type IS 'Raw Jira source field: comment  type.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs.comment__version IS 'Raw Jira source field: comment  version.';
COMMENT ON TABLE raw_jira.issues__fields__worklog__worklogs__comment__content IS 'Raw Jira object mirrored from source API: issues  fields  worklog  worklogs  comment  content.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs__comment__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs__comment__content.attrs__local_id IS 'Raw Jira source field: attrs  local id.';
COMMENT ON TABLE raw_jira.issues__fields__worklog__worklogs__comment__content__content IS 'Raw Jira object mirrored from source API: issues  fields  worklog  worklogs  comment  content  content.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs__comment__content__content.type IS 'Raw Jira source field: type.';
COMMENT ON COLUMN raw_jira.issues__fields__worklog__worklogs__comment__content__content.text IS 'Raw Jira source field: text.';
COMMENT ON TABLE raw_jira.issues__rendered_fields__attachment IS 'Raw Jira object mirrored from source API: issues  rendered fields  attachment.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.filename IS 'Raw Jira source field: filename.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.size IS 'Raw Jira source field: size.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.mime_type IS 'Raw Jira source field: mime type.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.content IS 'Raw Jira source field: content.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__attachment.thumbnail IS 'Raw Jira source field: thumbnail.';
COMMENT ON TABLE raw_jira.issues__rendered_fields__comment__comments IS 'Raw Jira object mirrored from source API: issues  rendered fields  comment  comments.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.body IS 'Raw Jira source field: body.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__self IS 'Raw Jira source field: update author  self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__account_id IS 'Raw Jira source field: update author  account id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__email_address IS 'Raw Jira source field: update author  email address.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__avatar_urls___48x48 IS 'Raw Jira source field: update author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__avatar_urls___24x24 IS 'Raw Jira source field: update author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__avatar_urls___16x16 IS 'Raw Jira source field: update author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__avatar_urls___32x32 IS 'Raw Jira source field: update author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__display_name IS 'Raw Jira source field: update author  display name.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__active IS 'Raw Jira source field: update author  active.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__time_zone IS 'Raw Jira source field: update author  time zone.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.update_author__account_type IS 'Raw Jira source field: update author  account type.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.updated IS 'Raw Jira source field: updated.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__comment__comments.jsd_public IS 'Raw Jira source field: jsd public.';
COMMENT ON TABLE raw_jira.issues__rendered_fields__worklog__worklogs IS 'Raw Jira object mirrored from source API: issues  rendered fields  worklog  worklogs.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.created IS 'Raw Jira source field: created.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.updated IS 'Raw Jira source field: updated.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.started IS 'Raw Jira source field: started.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.time_spent IS 'Raw Jira source field: time spent.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.issue_id IS 'Raw Jira source field: issue id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__self IS 'Raw Jira source field: update author  self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__account_id IS 'Raw Jira source field: update author  account id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__email_address IS 'Raw Jira source field: update author  email address.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__display_name IS 'Raw Jira source field: update author  display name.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__active IS 'Raw Jira source field: update author  active.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__time_zone IS 'Raw Jira source field: update author  time zone.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__account_type IS 'Raw Jira source field: update author  account type.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__avatar_urls___48x48 IS 'Raw Jira source field: update author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__avatar_urls___24x24 IS 'Raw Jira source field: update author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__avatar_urls___16x16 IS 'Raw Jira source field: update author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.update_author__avatar_urls___32x32 IS 'Raw Jira source field: update author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__self IS 'Raw Jira source field: author  self.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__account_id IS 'Raw Jira source field: author  account id.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__email_address IS 'Raw Jira source field: author  email address.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__display_name IS 'Raw Jira source field: author  display name.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__active IS 'Raw Jira source field: author  active.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__time_zone IS 'Raw Jira source field: author  time zone.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__account_type IS 'Raw Jira source field: author  account type.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__avatar_urls___48x48 IS 'Raw Jira source field: author  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__avatar_urls___24x24 IS 'Raw Jira source field: author  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__avatar_urls___16x16 IS 'Raw Jira source field: author  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.author__avatar_urls___32x32 IS 'Raw Jira source field: author  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.issues__rendered_fields__worklog__worklogs.comment IS 'Raw Jira source field: comment.';
COMMENT ON TABLE raw_jira.projects IS 'Raw Jira object mirrored from source API: projects.';
COMMENT ON COLUMN raw_jira.projects.expand IS 'Raw Jira source field: expand.';
COMMENT ON COLUMN raw_jira.projects.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.projects.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.projects.key IS 'Raw Jira source field: key.';
COMMENT ON COLUMN raw_jira.projects.description IS 'Raw Jira source field: description.';
COMMENT ON COLUMN raw_jira.projects.lead__self IS 'Raw Jira source field: lead  self.';
COMMENT ON COLUMN raw_jira.projects.lead__account_id IS 'Raw Jira source field: lead  account id.';
COMMENT ON COLUMN raw_jira.projects.lead__account_type IS 'Raw Jira source field: lead  account type.';
COMMENT ON COLUMN raw_jira.projects.lead__avatar_urls___48x48 IS 'Raw Jira source field: lead  avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.projects.lead__avatar_urls___24x24 IS 'Raw Jira source field: lead  avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.projects.lead__avatar_urls___16x16 IS 'Raw Jira source field: lead  avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.projects.lead__avatar_urls___32x32 IS 'Raw Jira source field: lead  avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.projects.lead__display_name IS 'Raw Jira source field: lead  display name.';
COMMENT ON COLUMN raw_jira.projects.lead__active IS 'Raw Jira source field: lead  active.';
COMMENT ON COLUMN raw_jira.projects.name IS 'Raw Jira source field: name.';
COMMENT ON COLUMN raw_jira.projects.avatar_urls___48x48 IS 'Raw Jira source field: avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.projects.avatar_urls___24x24 IS 'Raw Jira source field: avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.projects.avatar_urls___16x16 IS 'Raw Jira source field: avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.projects.avatar_urls___32x32 IS 'Raw Jira source field: avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.projects.project_type_key IS 'Raw Jira source field: project type key.';
COMMENT ON COLUMN raw_jira.projects.simplified IS 'Raw Jira source field: simplified.';
COMMENT ON COLUMN raw_jira.projects.style IS 'Raw Jira source field: style.';
COMMENT ON COLUMN raw_jira.projects.is_private IS 'Raw Jira source field: is private.';
COMMENT ON COLUMN raw_jira.projects.project_category__self IS 'Raw Jira source field: project category  self.';
COMMENT ON COLUMN raw_jira.projects.project_category__id IS 'Raw Jira source field: project category  id.';
COMMENT ON COLUMN raw_jira.projects.project_category__name IS 'Raw Jira source field: project category  name.';
COMMENT ON COLUMN raw_jira.projects.project_category__description IS 'Raw Jira source field: project category  description.';
COMMENT ON TABLE raw_jira.sprints IS 'Raw Jira object mirrored from source API: sprints.';
COMMENT ON COLUMN raw_jira.sprints.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.sprints.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.sprints.state IS 'Raw Jira source field: state.';
COMMENT ON COLUMN raw_jira.sprints.name IS 'Raw Jira source field: name.';
COMMENT ON COLUMN raw_jira.sprints.start_date IS 'Raw Jira source field: start date.';
COMMENT ON COLUMN raw_jira.sprints.end_date IS 'Raw Jira source field: end date.';
COMMENT ON COLUMN raw_jira.sprints.complete_date IS 'Raw Jira source field: complete date.';
COMMENT ON COLUMN raw_jira.sprints.origin_board_id IS 'Raw Jira source field: origin board id.';
COMMENT ON COLUMN raw_jira.sprints.goal IS 'Raw Jira source field: goal.';
COMMENT ON COLUMN raw_jira.sprints.board_id IS 'Raw Jira source field: board id.';
COMMENT ON COLUMN raw_jira.sprints.board_name IS 'Raw Jira source field: board name.';
COMMENT ON COLUMN raw_jira.sprints.project_key IS 'Raw Jira source field: project key.';
COMMENT ON COLUMN raw_jira.sprints.created_date IS 'Raw Jira source field: created date.';
COMMENT ON TABLE raw_jira.users IS 'Raw Jira object mirrored from source API: users.';
COMMENT ON COLUMN raw_jira.users.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.users.account_id IS 'Raw Jira source field: account id.';
COMMENT ON COLUMN raw_jira.users.account_type IS 'Raw Jira source field: account type.';
COMMENT ON COLUMN raw_jira.users.email_address IS 'Raw Jira source field: email address.';
COMMENT ON COLUMN raw_jira.users.avatar_urls___48x48 IS 'Raw Jira source field: avatar urls   48x48.';
COMMENT ON COLUMN raw_jira.users.avatar_urls___24x24 IS 'Raw Jira source field: avatar urls   24x24.';
COMMENT ON COLUMN raw_jira.users.avatar_urls___16x16 IS 'Raw Jira source field: avatar urls   16x16.';
COMMENT ON COLUMN raw_jira.users.avatar_urls___32x32 IS 'Raw Jira source field: avatar urls   32x32.';
COMMENT ON COLUMN raw_jira.users.display_name IS 'Raw Jira source field: display name.';
COMMENT ON COLUMN raw_jira.users.active IS 'Raw Jira source field: active.';
COMMENT ON COLUMN raw_jira.users.time_zone IS 'Raw Jira source field: time zone.';
COMMENT ON COLUMN raw_jira.users.locale IS 'Raw Jira source field: locale.';
COMMENT ON TABLE raw_jira.versions IS 'Raw Jira object mirrored from source API: versions.';
COMMENT ON COLUMN raw_jira.versions.self IS 'Raw Jira source field: self.';
COMMENT ON COLUMN raw_jira.versions.id IS 'Raw Jira source field: id.';
COMMENT ON COLUMN raw_jira.versions.description IS 'Raw Jira source field: description.';
COMMENT ON COLUMN raw_jira.versions.name IS 'Raw Jira source field: name.';
COMMENT ON COLUMN raw_jira.versions.archived IS 'Raw Jira source field: archived.';
COMMENT ON COLUMN raw_jira.versions.released IS 'Raw Jira source field: released.';
COMMENT ON COLUMN raw_jira.versions.release_date IS 'Raw Jira source field: release date.';
COMMENT ON COLUMN raw_jira.versions.user_release_date IS 'Raw Jira source field: user release date.';
COMMENT ON COLUMN raw_jira.versions.project_id IS 'Raw Jira source field: project id.';
COMMENT ON COLUMN raw_jira.versions.project_key IS 'Raw Jira source field: project key.';
COMMENT ON COLUMN raw_jira.versions.overdue IS 'Raw Jira source field: overdue.';

-- Curated semantic comments (priority objects)
COMMENT ON TABLE raw_jira.issues IS 'Raw Jira issues payload as returned by Jira search API; source of truth for issue-level ingestion.';
COMMENT ON COLUMN raw_jira.issues.id IS 'Jira issue ID from source system.';
COMMENT ON COLUMN raw_jira.issues.key IS 'Jira issue key (for example, PROJ-123).';
COMMENT ON COLUMN raw_jira.issues.fields__project__id IS 'Jira project ID embedded in issue payload.';
COMMENT ON COLUMN raw_jira.issues.fields__project__key IS 'Jira project key embedded in issue payload.';
COMMENT ON COLUMN raw_jira.issues.fields__status__id IS 'Current Jira status ID in raw payload.';
COMMENT ON COLUMN raw_jira.issues.fields__status__name IS 'Current Jira status name in raw payload.';
COMMENT ON COLUMN raw_jira.issues.fields__created IS 'Issue creation timestamp in Jira.';
COMMENT ON COLUMN raw_jira.issues.fields__updated IS 'Last update timestamp in Jira.';
COMMENT ON COLUMN raw_jira.issues.fields__resolutiondate IS 'Resolution timestamp from Jira when available.';

COMMENT ON TABLE raw_jira.issues__changelog__histories IS 'Raw changelog history entries nested under issues payload.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.created IS 'Timestamp of changelog history event.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__account_id IS 'Jira account ID of change author.';

COMMENT ON TABLE raw_jira.issues__changelog__histories__items IS 'Raw field-level changelog items from Jira histories.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.field IS 'Changed field name in Jira changelog item.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.from_string IS 'Previous field value (display form).';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.to_string IS 'New field value (display form).';

COMMENT ON TABLE raw_jira.issues__fields__customfield_10020 IS 'Raw sprint custom field values attached to issues (Jira customfield_10020).';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.id IS 'Sprint ID captured inside custom field value.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.name IS 'Sprint name captured inside custom field value.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.state IS 'Sprint state captured inside custom field value.';

COMMENT ON TABLE raw_jira.sprints IS 'Raw Jira sprints payload used to build clean sprint entities.';
COMMENT ON COLUMN raw_jira.sprints.id IS 'Jira sprint ID.';
COMMENT ON COLUMN raw_jira.sprints.name IS 'Sprint name from Jira.';
COMMENT ON COLUMN raw_jira.sprints.state IS 'Sprint lifecycle state (future/active/closed).';
COMMENT ON COLUMN raw_jira.sprints.start_date IS 'Sprint planned start timestamp.';
COMMENT ON COLUMN raw_jira.sprints.end_date IS 'Sprint planned end timestamp.';
COMMENT ON COLUMN raw_jira.sprints.complete_date IS 'Sprint completion timestamp.';

-- Curated semantic comments v2 (top tables)
COMMENT ON TABLE raw_jira.issues IS 'Primary raw Jira issue payload from search API, including flattened fields and rendered fragments.';
COMMENT ON COLUMN raw_jira.issues.id IS 'Stable Jira issue identifier.';
COMMENT ON COLUMN raw_jira.issues.key IS 'Human-readable Jira issue key (for example, PROJ-123).';
COMMENT ON COLUMN raw_jira.issues.self IS 'Jira API URL of the issue resource.';

COMMENT ON TABLE raw_jira.issues__changelog__histories IS 'Raw changelog history events attached to issues (one row per history entry).';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.created IS 'Timestamp when this changelog history event was recorded.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories.author__account_id IS 'Jira account ID of the user who made the change.';

COMMENT ON TABLE raw_jira.issues__changelog__histories__items IS 'Raw field-level changes inside each changelog history event (one row per changed field).';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.field IS 'Changed Jira field name.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.from_string IS 'Previous display value of the changed field.';
COMMENT ON COLUMN raw_jira.issues__changelog__histories__items.to_string IS 'New display value of the changed field.';

COMMENT ON TABLE raw_jira.issues__fields__customfield_10020 IS 'Raw sprint custom field entries captured from Jira issue payload (customfield_10020).';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.id IS 'Sprint ID referenced by issue custom field.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.state IS 'Sprint state snapshot from custom field payload.';
COMMENT ON COLUMN raw_jira.issues__fields__customfield_10020.complete_date IS 'Sprint completion timestamp from custom field payload.';

COMMENT ON TABLE raw_jira.sprints IS 'Raw sprint dimension extracted from Jira Agile API.';
COMMENT ON COLUMN raw_jira.sprints.id IS 'Jira sprint ID.';
COMMENT ON COLUMN raw_jira.sprints.state IS 'Sprint lifecycle state (future, active, closed).';
COMMENT ON COLUMN raw_jira.sprints.start_date IS 'Planned sprint start timestamp.';
COMMENT ON COLUMN raw_jira.sprints.end_date IS 'Planned sprint end timestamp.';
COMMENT ON COLUMN raw_jira.sprints.complete_date IS 'Actual sprint completion timestamp.';
