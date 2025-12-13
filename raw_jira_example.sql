-- DROP SCHEMA raw_jira;

CREATE SCHEMA raw_jira AUTHORIZATION postgres;
-- raw_jira._dlt_loads определение

-- Drop table

-- DROP TABLE raw_jira._dlt_loads;

CREATE TABLE raw_jira._dlt_loads ( load_id varchar(64) NOT NULL, schema_name varchar NULL, status int8 NOT NULL, inserted_at timestamptz NOT NULL, schema_version_hash varchar NULL);


-- raw_jira._dlt_pipeline_state определение

-- Drop table

-- DROP TABLE raw_jira._dlt_pipeline_state;

CREATE TABLE raw_jira._dlt_pipeline_state ( "version" int8 NOT NULL, engine_version int8 NOT NULL, pipeline_name varchar NOT NULL, state varchar NOT NULL, created_at timestamptz NOT NULL, version_hash varchar NULL, _dlt_load_id varchar(64) NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT _dlt_pipeline_state__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira._dlt_version определение

-- Drop table

-- DROP TABLE raw_jira._dlt_version;

CREATE TABLE raw_jira._dlt_version ( "version" int8 NOT NULL, engine_version int8 NOT NULL, inserted_at timestamptz NOT NULL, schema_name varchar NOT NULL, version_hash varchar NOT NULL, "schema" varchar NOT NULL);


-- raw_jira.board_configurations определение

-- Drop table

-- DROP TABLE raw_jira.board_configurations;

CREATE TABLE raw_jira.board_configurations ( board_id int8 NOT NULL, board_name varchar NULL, board_type varchar NULL, project_key varchar NULL, columns_config__constraint_type varchar NULL, filter_id varchar NULL, _dlt_load_id varchar NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT board_configurations__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.board_configurations__columns_config__columns определение

-- Drop table

-- DROP TABLE raw_jira.board_configurations__columns_config__columns;

CREATE TABLE raw_jira.board_configurations__columns_config__columns ( "name" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT board_configurations__columns_config__columns__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.board_configurations__columns_config__columns__statuses определение

-- Drop table

-- DROP TABLE raw_jira.board_configurations__columns_config__columns__statuses;

CREATE TABLE raw_jira.board_configurations__columns_config__columns__statuses ( id varchar NULL, "self" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT board_configurations__columns_config__columns__stat__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues определение

-- Drop table

-- DROP TABLE raw_jira.issues;

CREATE TABLE raw_jira.issues ( expand varchar NULL, id varchar NOT NULL, "self" varchar NULL, "key" varchar NULL, rendered_fields__customfield_10071 varchar NULL, rendered_fields__customfield_10078 varchar NULL, rendered_fields__customfield_10994 varchar NULL, rendered_fields__customfield_10060 varchar NULL, rendered_fields__customfield_11273 varchar NULL, rendered_fields__customfield_11274 varchar NULL, rendered_fields__customfield_10067 varchar NULL, rendered_fields__customfield_10068 varchar NULL, rendered_fields__customfield_10055 varchar NULL, rendered_fields__customfield_10056 varchar NULL, rendered_fields__customfield_10057 varchar NULL, rendered_fields__customfield_10058 varchar NULL, rendered_fields__customfield_11139 varchar NULL, rendered_fields__customfield_10843 varchar NULL, rendered_fields__customfield_10844 varchar NULL, rendered_fields__customfield_10044 varchar NULL, rendered_fields__customfield_10286 varchar NULL, rendered_fields__customfield_10046 varchar NULL, rendered_fields__customfield_10047 varchar NULL, rendered_fields__customfield_10048 varchar NULL, rendered_fields__customfield_10710 varchar NULL, rendered_fields__customfield_10711 varchar NULL, rendered_fields__customfield_10712 varchar NULL, rendered_fields__worklog__start_at int8 NULL, rendered_fields__worklog__max_results int8 NULL, rendered_fields__worklog__total int8 NULL, rendered_fields__customfield_10152 varchar NULL, rendered_fields__customfield_10156 varchar NULL, rendered_fields__customfield_10157 varchar NULL, rendered_fields__customfield_10017 varchar NULL, rendered_fields__customfield_11106 varchar NULL, rendered_fields__updated varchar NULL, rendered_fields__description varchar NULL, rendered_fields__environment varchar NULL, rendered_fields__comment__self varchar NULL, rendered_fields__comment__max_results int8 NULL, rendered_fields__comment__total int8 NULL, rendered_fields__comment__start_at int8 NULL, rendered_fields__statuscategorychangedate varchar NULL, rendered_fields__customfield_11091 varchar NULL, rendered_fields__customfield_11093 varchar NULL, rendered_fields__customfield_11095 varchar NULL, rendered_fields__customfield_11080 varchar NULL, rendered_fields__customfield_11081 varchar NULL, rendered_fields__customfield_11082 varchar NULL, rendered_fields__customfield_11083 varchar NULL, rendered_fields__customfield_11088 varchar NULL, rendered_fields__customfield_11089 varchar NULL, rendered_fields__customfield_11192 varchar NULL, rendered_fields__customfield_11193 varchar NULL, rendered_fields__created varchar NULL, rendered_fields__customfield_11074 varchar NULL, rendered_fields__customfield_11197 varchar NULL, rendered_fields__customfield_11198 varchar NULL, rendered_fields__customfield_11077 varchar NULL, rendered_fields__customfield_11078 varchar NULL, rendered_fields__customfield_11189 varchar NULL, changelog__start_at int8 NULL, changelog__max_results int8 NULL, changelog__total int8 NULL, fields__parent__id varchar NULL, fields__parent__key varchar NULL, fields__parent__self varchar NULL, fields__parent__fields__summary varchar NULL, fields__parent__fields__status__self varchar NULL, fields__parent__fields__status__description varchar NULL, fields__parent__fields__status__icon_url varchar NULL, fields__parent__fields__status__name varchar NULL, fields__parent__fields__status__id varchar NULL, fields__parent__fields__status__status_category__self varchar NULL, fields__parent__fields__status__status_category__id int8 NULL, fields__parent__fields__status__status_category__key varchar NULL, fields__parent__fields__status__status_category__color_name varchar NULL, fields__parent__fields__status__status_category__name varchar NULL, fields__parent__fields__priority__self varchar NULL, fields__parent__fields__priority__icon_url varchar NULL, fields__parent__fields__priority__name varchar NULL, fields__parent__fields__priority__id varchar NULL, fields__parent__fields__issuetype__self varchar NULL, fields__parent__fields__issuetype__id varchar NULL, fields__parent__fields__issuetype__description varchar NULL, fields__parent__fields__issuetype__icon_url varchar NULL, fields__parent__fields__issuetype__name varchar NULL, fields__parent__fields__issuetype__subtask bool NULL, fields__parent__fields__issuetype__avatar_id int8 NULL, fields__parent__fields__issuetype__hierarchy_level int8 NULL, fields__status_category__self varchar NULL, fields__status_category__id int8 NULL, fields__status_category__key varchar NULL, fields__status_category__color_name varchar NULL, fields__status_category__name varchar NULL, fields__reporter__self varchar NULL, fields__reporter__account_id varchar NULL, fields__reporter__avatar_urls___48x48 varchar NULL, fields__reporter__avatar_urls___24x24 varchar NULL, fields__reporter__avatar_urls___16x16 varchar NULL, fields__reporter__avatar_urls___32x32 varchar NULL, fields__reporter__display_name varchar NULL, fields__reporter__active bool NULL, fields__reporter__time_zone varchar NULL, fields__reporter__account_type varchar NULL, fields__progress__progress int8 NULL, fields__progress__total int8 NULL, fields__votes__self varchar NULL, fields__votes__votes int8 NULL, fields__votes__has_voted bool NULL, fields__worklog__start_at int8 NULL, fields__worklog__max_results int8 NULL, fields__worklog__total int8 NULL, fields__issuetype__self varchar NULL, fields__issuetype__id varchar NULL, fields__issuetype__description varchar NULL, fields__issuetype__icon_url varchar NULL, fields__issuetype__name varchar NULL, fields__issuetype__subtask bool NULL, fields__issuetype__avatar_id int8 NULL, fields__issuetype__hierarchy_level int8 NULL, fields__project__self varchar NULL, fields__project__id varchar NULL, fields__project__key varchar NULL, fields__project__name varchar NULL, fields__project__project_type_key varchar NULL, fields__project__simplified bool NULL, fields__project__avatar_urls___48x48 varchar NULL, fields__project__avatar_urls___24x24 varchar NULL, fields__project__avatar_urls___16x16 varchar NULL, fields__project__avatar_urls___32x32 varchar NULL, fields__watches__self varchar NULL, fields__watches__watch_count int8 NULL, fields__watches__is_watching bool NULL, fields__customfield_10019 varchar NULL, fields__updated timestamptz NULL, fields__summary varchar NULL, fields__customfield_10000 varchar NULL, fields__comment__self varchar NULL, fields__comment__max_results int8 NULL, fields__comment__total int8 NULL, fields__comment__start_at int8 NULL, fields__statuscategorychangedate timestamptz NULL, fields__priority__self varchar NULL, fields__priority__icon_url varchar NULL, fields__priority__name varchar NULL, fields__priority__id varchar NULL, fields__status__self varchar NULL, fields__status__description varchar NULL, fields__status__icon_url varchar NULL, fields__status__name varchar NULL, fields__status__id varchar NULL, fields__status__status_category__self varchar NULL, fields__status__status_category__id int8 NULL, fields__status__status_category__key varchar NULL, fields__status__status_category__color_name varchar NULL, fields__status__status_category__name varchar NULL, fields__creator__self varchar NULL, fields__creator__account_id varchar NULL, fields__creator__avatar_urls___48x48 varchar NULL, fields__creator__avatar_urls___24x24 varchar NULL, fields__creator__avatar_urls___16x16 varchar NULL, fields__creator__avatar_urls___32x32 varchar NULL, fields__creator__display_name varchar NULL, fields__creator__active bool NULL, fields__creator__time_zone varchar NULL, fields__creator__account_type varchar NULL, fields__aggregateprogress__progress int8 NULL, fields__aggregateprogress__total int8 NULL, fields__customfield_10201 varchar NULL, fields__workratio int8 NULL, fields__issuerestriction__should_display bool NULL, fields__created timestamptz NULL, _dlt_load_id varchar NOT NULL, _dlt_id varchar NOT NULL, fields__reporter__email_address varchar NULL, fields__customfield_10014 varchar NULL, fields__creator__email_address varchar NULL, rendered_fields__last_viewed varchar NULL, rendered_fields__customfield_10011 varchar NULL, rendered_fields__customfield_10013 varchar NULL, fields__last_viewed timestamptz NULL, fields__customfield_10017 varchar NULL, fields__customfield_10012__self varchar NULL, fields__customfield_10012__value varchar NULL, fields__customfield_10012__id varchar NULL, fields__customfield_10013 varchar NULL, fields__assignee__self varchar NULL, fields__assignee__account_id varchar NULL, fields__assignee__email_address varchar NULL, fields__assignee__avatar_urls___48x48 varchar NULL, fields__assignee__avatar_urls___24x24 varchar NULL, fields__assignee__avatar_urls___16x16 varchar NULL, fields__assignee__avatar_urls___32x32 varchar NULL, fields__assignee__display_name varchar NULL, fields__assignee__active bool NULL, fields__assignee__time_zone varchar NULL, fields__assignee__account_type varchar NULL, fields__description__type varchar NULL, fields__description__version int8 NULL, rendered_fields__customfield_10026 varchar NULL, fields__customfield_10036 float8 NULL, fields__customfield_10026 timestamptz NULL, rendered_fields__resolutiondate varchar NULL, fields__resolution__self varchar NULL, fields__resolution__id varchar NULL, fields__resolution__description varchar NULL, fields__resolution__name varchar NULL, fields__customfield_10027 varchar NULL, fields__resolutiondate timestamptz NULL, fields__customfield_11237 float8 NULL, rendered_fields__duedate varchar NULL, fields__customfield_10011 varchar NULL, fields__duedate varchar NULL, rendered_fields__customfield_10015 varchar NULL, fields__customfield_10015 varchar NULL, fields__customfield_10016 float8 NULL, fields__customfield_11041__self varchar NULL, fields__customfield_11041__value varchar NULL, fields__customfield_11041__id varchar NULL, fields__customfield_10050__error_message varchar NULL, fields__customfield_10050__i18n_error_message__i18n_key varchar NULL, fields__customfield_10049__error_message varchar NULL, fields__customfield_10049__i18n_error_message__i18n_key varchar NULL, fields__customfield_10680__error_message varchar NULL, fields__customfield_10680__i18n_error_message__i18n_key varchar NULL, rendered_fields__aggregatetimeoriginalestimate varchar NULL, rendered_fields__timeoriginalestimate varchar NULL, rendered_fields__timetracking__original_estimate varchar NULL, rendered_fields__timetracking__remaining_estimate varchar NULL, rendered_fields__timetracking__original_estimate_seconds int8 NULL, rendered_fields__timetracking__remaining_estimate_seconds int8 NULL, rendered_fields__timeestimate varchar NULL, rendered_fields__aggregatetimeestimate varchar NULL, fields__aggregatetimeoriginalestimate int8 NULL, fields__timeoriginalestimate int8 NULL, fields__timetracking__original_estimate varchar NULL, fields__timetracking__remaining_estimate varchar NULL, fields__timetracking__original_estimate_seconds int8 NULL, fields__timetracking__remaining_estimate_seconds int8 NULL, fields__timeestimate int8 NULL, fields__aggregatetimeestimate int8 NULL, fields__progress__percent int8 NULL, fields__aggregateprogress__percent int8 NULL, fields__environment__type varchar NULL, fields__environment__version int8 NULL, CONSTRAINT issues__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__changelog__histories определение

-- Drop table

-- DROP TABLE raw_jira.issues__changelog__histories;

CREATE TABLE raw_jira.issues__changelog__histories ( id varchar NULL, author__self varchar NULL, author__account_id varchar NULL, author__avatar_urls___48x48 varchar NULL, author__avatar_urls___24x24 varchar NULL, author__avatar_urls___16x16 varchar NULL, author__avatar_urls___32x32 varchar NULL, author__display_name varchar NULL, author__active bool NULL, author__time_zone varchar NULL, author__account_type varchar NULL, created timestamptz NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, author__email_address varchar NULL, CONSTRAINT issues__changelog__histories__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__changelog__histories__items определение

-- Drop table

-- DROP TABLE raw_jira.issues__changelog__histories__items;

CREATE TABLE raw_jira.issues__changelog__histories__items ( field varchar NULL, fieldtype varchar NULL, "to" varchar NULL, to_string varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, field_id varchar NULL, from_string varchar NULL, "from" varchar NULL, tmp_to_account_id varchar NULL, CONSTRAINT issues__changelog__histories__items__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__attachment определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__attachment;

CREATE TABLE raw_jira.issues__fields__attachment ( "self" varchar NULL, id varchar NULL, filename varchar NULL, author__self varchar NULL, author__account_id varchar NULL, author__email_address varchar NULL, author__avatar_urls___48x48 varchar NULL, author__avatar_urls___24x24 varchar NULL, author__avatar_urls___16x16 varchar NULL, author__avatar_urls___32x32 varchar NULL, author__display_name varchar NULL, author__active bool NULL, author__time_zone varchar NULL, author__account_type varchar NULL, created timestamptz NULL, "size" int8 NULL, mime_type varchar NULL, "content" varchar NULL, thumbnail varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__attachment__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__commak4pdqt__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__commak4pdqt__content__content__content;

CREATE TABLE raw_jira.issues__fields__comment__commak4pdqt__content__content__content ( "type" varchar NULL, "text" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__type varchar NULL, attrs__id varchar NULL, attrs__alt varchar NULL, attrs__collection varchar NULL, attrs__height int8 NULL, attrs__width int8 NULL, attrs__text varchar NULL, attrs__access_level varchar NULL, attrs__local_id varchar NULL, CONSTRAINT issues__fields__comment__commak4pdqt__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__commdhejxqent__content__content__marks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__commdhejxqent__content__content__marks;

CREATE TABLE raw_jira.issues__fields__comment__commdhejxqent__content__content__marks ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__comment__commdhejxqent__content__co__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__comments определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__comments;

CREATE TABLE raw_jira.issues__fields__comment__comments ( "self" varchar NULL, id varchar NULL, author__self varchar NULL, author__account_id varchar NULL, author__email_address varchar NULL, author__avatar_urls___48x48 varchar NULL, author__avatar_urls___24x24 varchar NULL, author__avatar_urls___16x16 varchar NULL, author__avatar_urls___32x32 varchar NULL, author__display_name varchar NULL, author__active bool NULL, author__time_zone varchar NULL, author__account_type varchar NULL, body__type varchar NULL, body__version int8 NULL, update_author__self varchar NULL, update_author__account_id varchar NULL, update_author__email_address varchar NULL, update_author__avatar_urls___48x48 varchar NULL, update_author__avatar_urls___24x24 varchar NULL, update_author__avatar_urls___16x16 varchar NULL, update_author__avatar_urls___32x32 varchar NULL, update_author__display_name varchar NULL, update_author__active bool NULL, update_author__time_zone varchar NULL, update_author__account_type varchar NULL, created timestamptz NULL, updated timestamptz NULL, jsd_public bool NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__comment__comments__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__comments__body__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__comments__body__content;

CREATE TABLE raw_jira.issues__fields__comment__comments__body__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__width int8 NULL, attrs__width_type varchar NULL, attrs__layout varchar NULL, attrs__order int8 NULL, CONSTRAINT issues__fields__comment__comments__body__content__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__comments__body__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__comments__body__content__content;

CREATE TABLE raw_jira.issues__fields__comment__comments__body__content__content ( "type" varchar NULL, "text" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__id varchar NULL, attrs__text varchar NULL, attrs__access_level varchar NULL, attrs__local_id varchar NULL, attrs__url varchar NULL, attrs__type varchar NULL, attrs__alt varchar NULL, attrs__collection varchar NULL, attrs__height int8 NULL, attrs__width int8 NULL, attrs__order int8 NULL, attrs__short_name varchar NULL, CONSTRAINT issues__fields__comment__comments__body__content__c__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__commutqfnqy__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__commutqfnqy__content__content__content;

CREATE TABLE raw_jira.issues__fields__comment__commutqfnqy__content__content__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__width int8 NULL, attrs__width_type varchar NULL, attrs__layout varchar NULL, CONSTRAINT issues__fields__comment__commutqfnqy__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks;

CREATE TABLE raw_jira.issues__fields__comment__commw2ps0wody__content__content__marks ( "type" varchar NULL, attrs__href varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__color varchar NULL, CONSTRAINT issues__fields__comment__commw2ps0wody__content__co__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__comment__commyvyajqt__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__comment__commyvyajqt__content__content__content;

CREATE TABLE raw_jira.issues__fields__comment__commyvyajqt__content__content__content ( "type" varchar NULL, "text" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__comment__commyvyajqt__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__customfield_10020 определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__customfield_10020;

CREATE TABLE raw_jira.issues__fields__customfield_10020 ( id int8 NULL, "name" varchar NULL, state varchar NULL, board_id int8 NULL, goal varchar NULL, start_date timestamptz NULL, end_date timestamptz NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, complete_date timestamptz NULL, CONSTRAINT issues__fields__customfield_10020__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__customfield_10021 определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__customfield_10021;

CREATE TABLE raw_jira.issues__fields__customfield_10021 ( "self" varchar NULL, value varchar NULL, id varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__customfield_10021__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__customfield_10025 определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__customfield_10025;

CREATE TABLE raw_jira.issues__fields__customfield_10025 ( id varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__customfield_10025__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__customfield_11039 определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__customfield_11039;

CREATE TABLE raw_jira.issues__fields__customfield_11039 ( "self" varchar NULL, value varchar NULL, id varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__customfield_11039__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__ahypbqent__content__content__marks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__ahypbqent__content__content__marks;

CREATE TABLE raw_jira.issues__fields__description__ahypbqent__content__content__marks ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__description__ahypbqent__content__co__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__content;

CREATE TABLE raw_jira.issues__fields__description__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__order int8 NULL, attrs__width int8 NULL, attrs__width_type varchar NULL, attrs__layout varchar NULL, attrs__level int8 NULL, attrs__is_number_column_enabled bool NULL, attrs__local_id varchar NULL, CONSTRAINT issues__fields__description__content__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__content__content;

CREATE TABLE raw_jira.issues__fields__description__content__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, "text" varchar NULL, attrs__type varchar NULL, attrs__id varchar NULL, attrs__alt varchar NULL, attrs__collection varchar NULL, attrs__height int8 NULL, attrs__width int8 NULL, attrs__url varchar NULL, attrs__text varchar NULL, attrs__access_level varchar NULL, CONSTRAINT issues__fields__description__content__content__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__content__content__content;

CREATE TABLE raw_jira.issues__fields__description__content__content__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__width int8 NULL, attrs__width_type varchar NULL, attrs__layout varchar NULL, attrs__language varchar NULL, attrs__order int8 NULL, CONSTRAINT issues__fields__description__content__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__content__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__content__content__content__content;

CREATE TABLE raw_jira.issues__fields__description__content__content__content__content ( "type" varchar NULL, "text" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__type varchar NULL, attrs__id varchar NULL, attrs__alt varchar NULL, attrs__collection varchar NULL, attrs__height int8 NULL, attrs__width int8 NULL, attrs__url varchar NULL, attrs__order int8 NULL, CONSTRAINT issues__fields__description__content__content__con__dlt_id_key1 UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__content__content__marks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__content__content__marks;

CREATE TABLE raw_jira.issues__fields__description__content__content__marks ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__href varchar NULL, attrs__color varchar NULL, CONSTRAINT issues__fields__description__content__content__mark__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__cxb90gt__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__cxb90gt__content__content__content;

CREATE TABLE raw_jira.issues__fields__description__cxb90gt__content__content__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__width int8 NULL, attrs__width_type varchar NULL, attrs__layout varchar NULL, attrs__order int8 NULL, attrs__url varchar NULL, "text" varchar NULL, CONSTRAINT issues__fields__description__cxb90gt__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__g2calqt__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__g2calqt__content__content__content;

CREATE TABLE raw_jira.issues__fields__description__g2calqt__content__content__content ( "type" varchar NULL, "text" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__type varchar NULL, attrs__id varchar NULL, attrs__alt varchar NULL, attrs__collection varchar NULL, attrs__height int8 NULL, attrs__width int8 NULL, CONSTRAINT issues__fields__description__g2calqt__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__g8erbqent__content__content__marks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__g8erbqent__content__content__marks;

CREATE TABLE raw_jira.issues__fields__description__g8erbqent__content__content__marks ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__description__g8erbqent__content__co__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__ihgkwat__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__ihgkwat__content__content__content;

CREATE TABLE raw_jira.issues__fields__description__ihgkwat__content__content__content ( "type" varchar NULL, attrs__layout varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, "text" varchar NULL, CONSTRAINT issues__fields__description__ihgkwat__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__jwtu1went__content__content__marks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__jwtu1went__content__content__marks;

CREATE TABLE raw_jira.issues__fields__description__jwtu1went__content__content__marks ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, attrs__href varchar NULL, CONSTRAINT issues__fields__description__jwtu1went__content__co__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__description__t8qrkat__content__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__description__t8qrkat__content__content__content;

CREATE TABLE raw_jira.issues__fields__description__t8qrkat__content__content__content ( "type" varchar NULL, attrs__type varchar NULL, attrs__id varchar NULL, attrs__alt varchar NULL, attrs__collection varchar NULL, attrs__height int8 NULL, attrs__width int8 NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__description__t8qrkat__content__cont__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__environment__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__environment__content;

CREATE TABLE raw_jira.issues__fields__environment__content ( "type" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__environment__content__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__environment__content__content определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__environment__content__content;

CREATE TABLE raw_jira.issues__fields__environment__content__content ( "type" varchar NULL, "text" varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__environment__content__content__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__fix_versions определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__fix_versions;

CREATE TABLE raw_jira.issues__fields__fix_versions ( "self" varchar NULL, id varchar NULL, description varchar NULL, "name" varchar NULL, archived bool NULL, released bool NULL, release_date varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__fix_versions__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__issuelinks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__issuelinks;

CREATE TABLE raw_jira.issues__fields__issuelinks ( id varchar NULL, "self" varchar NULL, type__id varchar NULL, type__name varchar NULL, type__inward varchar NULL, type__outward varchar NULL, type__self varchar NULL, inward_issue__id varchar NULL, inward_issue__key varchar NULL, inward_issue__self varchar NULL, inward_issue__fields__summary varchar NULL, inward_issue__fields__status__self varchar NULL, inward_issue__fields__status__description varchar NULL, inward_issue__fields__status__icon_url varchar NULL, inward_issue__fields__status__name varchar NULL, inward_issue__fields__status__id varchar NULL, inward_issue__fields__status__status_category__self varchar NULL, inward_issue__fields__status__status_category__id int8 NULL, inward_issue__fields__status__status_category__key varchar NULL, inward_issue__fields__status__status_category__color_name varchar NULL, inward_issue__fields__status__status_category__name varchar NULL, inward_issue__fields__priority__self varchar NULL, inward_issue__fields__priority__icon_url varchar NULL, inward_issue__fields__priority__name varchar NULL, inward_issue__fields__priority__id varchar NULL, inward_issue__fields__issuetype__self varchar NULL, inward_issue__fields__issuetype__id varchar NULL, inward_issue__fields__issuetype__description varchar NULL, inward_issue__fields__issuetype__icon_url varchar NULL, inward_issue__fields__issuetype__name varchar NULL, inward_issue__fields__issuetype__subtask bool NULL, inward_issue__fields__issuetype__avatar_id int8 NULL, inward_issue__fields__issuetype__hierarchy_level int8 NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, outward_issue__id varchar NULL, outward_issue__key varchar NULL, outward_issue__self varchar NULL, outward_issue__fields__summary varchar NULL, outward_issue__fields__status__self varchar NULL, outward_issue__fields__status__description varchar NULL, outward_issue__fields__status__icon_url varchar NULL, outward_issue__fields__status__name varchar NULL, outward_issue__fields__status__id varchar NULL, outward_issue__fields__status__status_category__self varchar NULL, outward_issue__fields__status__status_category__id int8 NULL, outward_issue__fields__status__status_category__key varchar NULL, outward_issue__fields__status__status_category__color_name varchar NULL, outward_issue__fields__status__status_category__name varchar NULL, outward_issue__fields__priority__self varchar NULL, outward_issue__fields__priority__icon_url varchar NULL, outward_issue__fields__priority__name varchar NULL, outward_issue__fields__priority__id varchar NULL, outward_issue__fields__issuetype__self varchar NULL, outward_issue__fields__issuetype__id varchar NULL, outward_issue__fields__issuetype__description varchar NULL, outward_issue__fields__issuetype__icon_url varchar NULL, outward_issue__fields__issuetype__name varchar NULL, outward_issue__fields__issuetype__subtask bool NULL, outward_issue__fields__issuetype__avatar_id int8 NULL, outward_issue__fields__issuetype__hierarchy_level int8 NULL, CONSTRAINT issues__fields__issuelinks__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__labels определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__labels;

CREATE TABLE raw_jira.issues__fields__labels ( value varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__labels__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__fields__subtasks определение

-- Drop table

-- DROP TABLE raw_jira.issues__fields__subtasks;

CREATE TABLE raw_jira.issues__fields__subtasks ( id varchar NULL, "key" varchar NULL, "self" varchar NULL, fields__summary varchar NULL, fields__status__self varchar NULL, fields__status__description varchar NULL, fields__status__icon_url varchar NULL, fields__status__name varchar NULL, fields__status__id varchar NULL, fields__status__status_category__self varchar NULL, fields__status__status_category__id int8 NULL, fields__status__status_category__key varchar NULL, fields__status__status_category__color_name varchar NULL, fields__status__status_category__name varchar NULL, fields__priority__self varchar NULL, fields__priority__icon_url varchar NULL, fields__priority__name varchar NULL, fields__priority__id varchar NULL, fields__issuetype__self varchar NULL, fields__issuetype__id varchar NULL, fields__issuetype__description varchar NULL, fields__issuetype__icon_url varchar NULL, fields__issuetype__name varchar NULL, fields__issuetype__subtask bool NULL, fields__issuetype__avatar_id int8 NULL, fields__issuetype__hierarchy_level int8 NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__fields__subtasks__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__rendered_fields__attachment определение

-- Drop table

-- DROP TABLE raw_jira.issues__rendered_fields__attachment;

CREATE TABLE raw_jira.issues__rendered_fields__attachment ( "self" varchar NULL, id varchar NULL, filename varchar NULL, author__self varchar NULL, author__account_id varchar NULL, author__email_address varchar NULL, author__avatar_urls___48x48 varchar NULL, author__avatar_urls___24x24 varchar NULL, author__avatar_urls___16x16 varchar NULL, author__avatar_urls___32x32 varchar NULL, author__display_name varchar NULL, author__active bool NULL, author__time_zone varchar NULL, author__account_type varchar NULL, created varchar NULL, "size" varchar NULL, mime_type varchar NULL, "content" varchar NULL, thumbnail varchar NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__rendered_fields__attachment__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.issues__rendered_fields__comment__comments определение

-- Drop table

-- DROP TABLE raw_jira.issues__rendered_fields__comment__comments;

CREATE TABLE raw_jira.issues__rendered_fields__comment__comments ( "self" varchar NULL, id varchar NULL, author__self varchar NULL, author__account_id varchar NULL, author__email_address varchar NULL, author__avatar_urls___48x48 varchar NULL, author__avatar_urls___24x24 varchar NULL, author__avatar_urls___16x16 varchar NULL, author__avatar_urls___32x32 varchar NULL, author__display_name varchar NULL, author__active bool NULL, author__time_zone varchar NULL, author__account_type varchar NULL, body varchar NULL, update_author__self varchar NULL, update_author__account_id varchar NULL, update_author__email_address varchar NULL, update_author__avatar_urls___48x48 varchar NULL, update_author__avatar_urls___24x24 varchar NULL, update_author__avatar_urls___16x16 varchar NULL, update_author__avatar_urls___32x32 varchar NULL, update_author__display_name varchar NULL, update_author__active bool NULL, update_author__time_zone varchar NULL, update_author__account_type varchar NULL, created varchar NULL, updated varchar NULL, jsd_public bool NULL, _dlt_root_id varchar NOT NULL, _dlt_parent_id varchar NOT NULL, _dlt_list_idx int8 NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT issues__rendered_fields__comment__comments__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.projects определение

-- Drop table

-- DROP TABLE raw_jira.projects;

CREATE TABLE raw_jira.projects ( expand varchar NULL, "self" varchar NULL, id varchar NOT NULL, "key" varchar NULL, description varchar NULL, lead__self varchar NULL, lead__account_id varchar NULL, lead__account_type varchar NULL, lead__avatar_urls___48x48 varchar NULL, lead__avatar_urls___24x24 varchar NULL, lead__avatar_urls___16x16 varchar NULL, lead__avatar_urls___32x32 varchar NULL, lead__display_name varchar NULL, lead__active bool NULL, "name" varchar NULL, avatar_urls___48x48 varchar NULL, avatar_urls___24x24 varchar NULL, avatar_urls___16x16 varchar NULL, avatar_urls___32x32 varchar NULL, project_type_key varchar NULL, simplified bool NULL, "style" varchar NULL, is_private bool NULL, _dlt_load_id varchar NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT projects__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.sprints определение

-- Drop table

-- DROP TABLE raw_jira.sprints;

CREATE TABLE raw_jira.sprints ( id int8 NOT NULL, "self" varchar NULL, state varchar NULL, "name" varchar NULL, start_date timestamptz NULL, end_date timestamptz NULL, complete_date timestamptz NULL, origin_board_id int8 NULL, goal varchar NULL, board_id int8 NULL, board_name varchar NULL, _dlt_load_id varchar NOT NULL, _dlt_id varchar NOT NULL, created_date timestamptz NULL, CONSTRAINT sprints__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.users определение

-- Drop table

-- DROP TABLE raw_jira.users;

CREATE TABLE raw_jira.users ( "self" varchar NULL, account_id varchar NOT NULL, account_type varchar NULL, email_address varchar NULL, avatar_urls___48x48 varchar NULL, avatar_urls___24x24 varchar NULL, avatar_urls___16x16 varchar NULL, avatar_urls___32x32 varchar NULL, display_name varchar NULL, active bool NULL, time_zone varchar NULL, locale varchar NULL, _dlt_load_id varchar NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT users__dlt_id_key UNIQUE (_dlt_id));


-- raw_jira.versions определение

-- Drop table

-- DROP TABLE raw_jira.versions;

CREATE TABLE raw_jira.versions ( "self" varchar NULL, id varchar NOT NULL, description varchar NULL, "name" varchar NULL, archived bool NULL, released bool NULL, release_date varchar NULL, user_release_date varchar NULL, project_id varchar NULL, project_key varchar NULL, _dlt_load_id varchar NOT NULL, _dlt_id varchar NOT NULL, CONSTRAINT versions__dlt_id_key UNIQUE (_dlt_id));
