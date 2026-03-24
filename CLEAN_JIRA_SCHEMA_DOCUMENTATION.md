# CLEAN_JIRA_SCHEMA_DOCUMENTATION

Документ описывает **полную актуальную схему `clean_jira`** (все таблицы, поля, типы, примеры значений и связи).

Источник структуры:
- `db/schemas/clean_jira_schema.sql`
- миграции: `0007_add_issue_status_history`, `0029_add_phase1_clean_jira_tables`, `0030_add_users_view_and_schema_cleanup`, `0031_add_external_id_indexes`

Всего таблиц в `clean_jira`: **31**.

## 1. Основные связи между таблицами

- `clean_jira.projects.platform_project_id -> platform.projects.id`
- `issue_types.project_id -> projects.id`
- `issue_statuses.project_id -> projects.id`
- `issue_priorities.project_id -> projects.id`
- `issue_resolutions.project_id -> projects.id`
- `jira_users.project_id -> projects.id`
- `issues.project_id -> projects.id`
- `issues.type_id -> issue_types.id`
- `issues.status_id -> issue_statuses.id`
- `issues.priority_id -> issue_priorities.id`
- `issues.resolution_id -> issue_resolutions.id`
- `issues.parent_id -> issues.id`
- `jira_user_issue_roles.user_id -> jira_users.id`
- `jira_user_issue_roles.issue_id -> issues.id`
- `issue_status_changelog.issue_id -> issues.id`
- `issue_status_changelog.from_status_id -> issue_statuses.id`
- `issue_status_changelog.to_status_id -> issue_statuses.id`
- `issue_status_changelog.changed_by_id -> jira_users.id`
- `sprints.project_id -> projects.id`
- `sprint_issues.sprint_id -> sprints.id`
- `sprint_issues.issue_id -> issues.id`
- `sprint_issues_changelog.sprint_id -> sprints.id`
- `sprint_issues_changelog.issue_id -> issues.id`
- `sprint_issues_changelog.changed_by_id -> jira_users.id`
- `sprint_changelog.sprint_id -> sprints.id`
- `sprint_changelog.changed_by_id -> jira_users.id`
- `releases.project_id -> projects.id`
- `release_issues.release_id -> releases.id`
- `release_issues.issue_id -> issues.id`
- `release_issues_changelog.release_id -> releases.id`
- `release_issues_changelog.issue_id -> issues.id`
- `release_issues_changelog.changed_by_id -> jira_users.id`
- `release_changelog.release_id -> releases.id`
- `release_changelog.changed_by_id -> jira_users.id`
- `field_keys.project_id -> projects.id`
- `field_values.issue_id -> issues.id`
- `field_values.field_key_id -> field_keys.id`
- `field_value_changelog.issue_id -> issues.id`
- `field_value_changelog.field_key_id -> field_keys.id`
- `field_value_changelog.changed_by_id -> jira_users.id`
- `labels.project_id -> projects.id`
- `issue_labels.issue_id -> issues.id`
- `issue_labels.label_id -> labels.id`
- `boards.project_id -> projects.id`
- `board_columns.board_id -> boards.id`
- `board_column_statuses.board_column_id -> board_columns.id`
- `board_column_statuses.status_id -> issue_statuses.id`
- `comments.project_id -> projects.id`
- `comments.author_id -> jira_users.id`
- `comment_issues.comment_id -> comments.id`
- `comment_issues.issue_id -> issues.id`
- `worklogs.issue_id -> issues.id`
- `worklogs.author_id -> jira_users.id`
- `relation_issue_types.project_id -> projects.id`
- `relation_issue_issues.relation_type_id -> relation_issue_types.id`
- `relation_issue_issues.source_issue_id -> issues.id`
- `relation_issue_issues.target_issue_id -> issues.id`
- `issue_comment_blockings.issue_id -> issues.id`
- `issue_comment_blockings.comment_id -> comments.id`

## 2. Таблицы и поля

### 2.1 `clean_jira.projects`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| platform_project_id | uuid | `3c5f8e6a-8d7f-4e23-a97d-2d4d2ff3e101` |
| external_id | text | `10010` |
| external_key | text | `ENG` |
| name | text | `Engineering` |
| created_at | timestamptz | `2026-03-24T09:00:00Z` |
| updated_at | timestamptz | `2026-03-24T09:30:00Z` |

### 2.2 `clean_jira.issue_types`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `bc5cfd2d-7f43-4fc6-bb9f-2a67c6543e95` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `10001` |
| name | text | `Story` |
| hierarchy_level | clean_jira.issue_hierarchy_level | `story` |
| created_at | timestamptz | `2026-03-24T09:01:00Z` |

### 2.3 `clean_jira.issue_statuses`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `8fd64f29-3d5e-42f2-b3f4-90b535dd5a01` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `3` |
| name | text | `In Progress` |
| category | clean_jira.issue_status_category | `in_progress` |
| created_at | timestamptz | `2026-03-24T09:02:00Z` |

### 2.4 `clean_jira.issue_priorities`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `4fe9119f-0791-4ec1-8920-b6f4b1f73de4` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `2` |
| name | text | `High` |
| created_at | timestamptz | `2026-03-24T09:03:00Z` |

### 2.5 `clean_jira.issue_resolutions`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `4d2e0538-57a2-4ca8-b5a8-1a7e0f17ec28` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `10000` |
| name | text | `Done` |
| description | text | `Work completed` |
| created_at | timestamptz | `2026-03-24T09:03:30Z` |

### 2.6 `clean_jira.jira_users`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `5b10a2844c20165700ede21g` |
| display_name | text | `Ivan Petrov` |
| created_at | timestamptz | `2026-03-24T09:05:00Z` |
| updated_at | timestamptz | `2026-03-24T09:05:00Z` |

### 2.7 `clean_jira.issues`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `123456` |
| external_key | text | `ENG-245` |
| summary | text | `Implement metrics endpoint` |
| description | text | `Need add aggregation and filters` |
| type_id | uuid | `bc5cfd2d-7f43-4fc6-bb9f-2a67c6543e95` |
| status_id | uuid | `8fd64f29-3d5e-42f2-b3f4-90b535dd5a01` |
| priority_id | uuid | `4fe9119f-0791-4ec1-8920-b6f4b1f73de4` |
| resolution_id | uuid | `4d2e0538-57a2-4ca8-b5a8-1a7e0f17ec28` |
| parent_id | uuid | `a4c5d1bb-a42a-4d2a-987d-030b62ea01fd` |
| jira_created_at | timestamptz | `2026-03-01T08:00:00Z` |
| jira_updated_at | timestamptz | `2026-03-24T08:30:00Z` |
| jira_resolved_at | timestamptz | `2026-03-24T08:45:00Z` |
| db_created_at | timestamptz | `2026-03-24T08:45:10Z` |
| db_updated_at | timestamptz | `2026-03-24T08:45:10Z` |

### 2.8 `clean_jira.jira_user_issue_roles`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `9ec12f1e-1f9e-4522-a0cc-16bdbdcbfda9` |
| user_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| role_type | clean_jira.user_role_type | `assignee` |
| assigned_at | timestamptz | `2026-03-24T09:06:00Z` |

### 2.9 `clean_jira.issue_status_changelog`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `ad8f7b22-aeb0-45df-9d6a-d47cd1aa7232` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| from_status_id | uuid | `c4a6037b-e666-43c0-8eb0-4ec814fef694` |
| to_status_id | uuid | `8fd64f29-3d5e-42f2-b3f4-90b535dd5a01` |
| changed_by_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| changed_at | timestamptz | `2026-03-10T10:15:00Z` |

### 2.10 `clean_jira.sprints`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `f7ec2ba7-1c56-4f68-92a8-a19fb808fc7a` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `47` |
| name | text | `Sprint 24` |
| goal | text | `Ship reporting MVP` |
| status | clean_jira.sprint_status | `active` |
| start_date | timestamptz | `2026-03-15T07:00:00Z` |
| end_date | timestamptz | `2026-03-29T19:00:00Z` |
| complete_date | timestamptz | `2026-03-29T18:30:00Z` |
| created_at | timestamptz | `2026-03-15T06:59:00Z` |
| updated_at | timestamptz | `2026-03-24T09:10:00Z` |

### 2.11 `clean_jira.sprint_issues`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `2f568572-a2ea-4fad-bc81-f4b9159f4197` |
| sprint_id | uuid | `f7ec2ba7-1c56-4f68-92a8-a19fb808fc7a` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| is_active | boolean | `true` |

### 2.12 `clean_jira.sprint_issues_changelog`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `7de86814-87de-4438-b11d-b5f9ec5e9f4d` |
| sprint_id | uuid | `f7ec2ba7-1c56-4f68-92a8-a19fb808fc7a` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| action | text | `added` |
| changed_by_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| changed_at | timestamptz | `2026-03-16T10:00:00Z` |

### 2.13 `clean_jira.sprint_changelog`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `af4fc0cf-4c5f-4602-a481-4bf10bd95ac7` |
| sprint_id | uuid | `f7ec2ba7-1c56-4f68-92a8-a19fb808fc7a` |
| field_name | text | `goal` |
| old_value | text | `Ship API` |
| new_value | text | `Ship reporting MVP` |
| changed_by_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| changed_at | timestamptz | `2026-03-17T12:00:00Z` |

### 2.14 `clean_jira.releases`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `a5ea8a79-f63f-43f7-8012-f3d7b6f8eb46` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `10021` |
| name | text | `v2.4.0` |
| description | text | `Quarterly release` |
| status | clean_jira.release_status | `released` |
| start_date | date | `2026-03-01` |
| release_date | date | `2026-03-31` |
| is_archived | boolean | `false` |
| is_released | boolean | `true` |
| created_at | timestamptz | `2026-03-01T00:00:00Z` |
| updated_at | timestamptz | `2026-03-24T09:12:00Z` |

### 2.15 `clean_jira.release_issues`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `12bba6be-f454-4677-b4cd-04868cf50dcb` |
| release_id | uuid | `a5ea8a79-f63f-43f7-8012-f3d7b6f8eb46` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| is_active | boolean | `true` |

### 2.16 `clean_jira.release_issues_changelog`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `3b87a70b-bf08-4fea-af41-79c50c4f70be` |
| release_id | uuid | `a5ea8a79-f63f-43f7-8012-f3d7b6f8eb46` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| action | text | `added` |
| changed_by_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| changed_at | timestamptz | `2026-03-20T10:00:00Z` |

### 2.17 `clean_jira.release_changelog`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `193e8fa6-f52e-48f8-8696-9f95f7c476b0` |
| release_id | uuid | `a5ea8a79-f63f-43f7-8012-f3d7b6f8eb46` |
| field_name | text | `release_date` |
| old_value | text | `2026-03-28` |
| new_value | text | `2026-03-31` |
| changed_by_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| changed_at | timestamptz | `2026-03-21T15:00:00Z` |

### 2.18 `clean_jira.field_keys`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `d4df1f88-b607-4ac2-bfb7-c8a32ba7792b` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_key | text | `customfield_10016` |
| name | text | `Story Points` |
| is_custom | boolean | `true` |
| created_at | timestamptz | `2026-03-05T07:00:00Z` |

### 2.19 `clean_jira.field_values`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `244ff8a8-f0ad-4c39-bfef-b8ddcfc6f0d5` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| field_key_id | uuid | `d4df1f88-b607-4ac2-bfb7-c8a32ba7792b` |
| json_value | jsonb | `8` |
| value | text | `8` |
| updated_at | timestamptz | `2026-03-24T09:13:00Z` |

### 2.20 `clean_jira.field_value_changelog`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `72dd77fa-6f8c-46aa-9005-66762943f959` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| field_key_id | uuid | `d4df1f88-b607-4ac2-bfb7-c8a32ba7792b` |
| old_value | jsonb | `5` |
| new_value | jsonb | `8` |
| changed_by_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| changed_at | timestamptz | `2026-03-22T11:10:00Z` |

### 2.21 `clean_jira.labels`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `794a9739-3beb-4a17-a78b-45818fb6fe0d` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| name | text | `backend` |
| created_at | timestamptz | `2026-03-10T09:00:00Z` |

### 2.22 `clean_jira.issue_labels`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `b47ecfe2-6fc7-4a86-b4a8-c89d2fca2a79` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| label_id | uuid | `794a9739-3beb-4a17-a78b-45818fb6fe0d` |

### 2.23 `clean_jira.boards`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `910d43a8-789d-486f-b719-387e384f7a3a` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `12` |
| name | text | `Engineering Scrum Board` |
| created_at | timestamptz | `2026-03-01T06:00:00Z` |

### 2.24 `clean_jira.board_columns`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `8ed04ac2-6c82-4e63-b2db-f6ed6bf5cf9a` |
| board_id | uuid | `910d43a8-789d-486f-b719-387e384f7a3a` |
| name | text | `In Progress` |
| position | int | `2` |

### 2.25 `clean_jira.board_column_statuses`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `5c2f86c8-4d0e-417c-b6ca-b74b16e0a95e` |
| board_column_id | uuid | `8ed04ac2-6c82-4e63-b2db-f6ed6bf5cf9a` |
| status_id | uuid | `8fd64f29-3d5e-42f2-b3f4-90b535dd5a01` |

### 2.26 `clean_jira.comments`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `a7704693-938f-4cc8-a45b-83de5ca67787` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `100890` |
| body | text | `Blocked by API rate limits` |
| author_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| created_at | timestamptz | `2026-03-19T13:00:00Z` |
| updated_at | timestamptz | `2026-03-19T13:10:00Z` |

### 2.27 `clean_jira.comment_issues`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `189359c3-48f4-4826-a7f9-9912879813ec` |
| comment_id | uuid | `a7704693-938f-4cc8-a45b-83de5ca67787` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |

### 2.28 `clean_jira.worklogs`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `13d98198-2786-4f4e-a88b-950443f8c7f2` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| external_id | text | `700123` |
| author_id | uuid | `57bbf8d9-5d23-40f5-8a22-6f310f0a31f8` |
| time_spent_seconds | int | `14400` |
| started_at | timestamptz | `2026-03-18T09:00:00Z` |
| created_at | timestamptz | `2026-03-18T13:00:00Z` |

### 2.29 `clean_jira.relation_issue_types`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `87e84971-c694-42f9-a928-dfd63ff6a1ba` |
| project_id | uuid | `0f8fad5b-d9cb-469f-a165-70867728950e` |
| external_id | text | `10003` |
| name | text | `blocks` |

### 2.30 `clean_jira.relation_issue_issues`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `d87329df-747f-4c01-a4b5-65d7d0f2df47` |
| relation_type_id | uuid | `87e84971-c694-42f9-a928-dfd63ff6a1ba` |
| source_issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| target_issue_id | uuid | `ad3b3a96-c95f-4b70-bc39-bbe958a830f8` |
| created_at | timestamptz | `2026-03-18T11:00:00Z` |

### 2.31 `clean_jira.issue_comment_blockings`

| Поле | Тип | Пример значения |
|---|---|---|
| id | uuid | `fb3df34e-9d3d-4ff6-a37e-37758ea91fc9` |
| issue_id | uuid | `b3e50f77-92a9-4bd7-b6ed-6b2ebf5e84c4` |
| comment_id | uuid | `a7704693-938f-4cc8-a45b-83de5ca67787` |
| is_resolved | boolean | `false` |
| blocked_at | timestamptz | `2026-03-19T13:00:00Z` |
| resolved_at | timestamptz | `2026-03-20T08:00:00Z` |

## 3. Enum-типы схемы `clean_jira`

- `clean_jira.issue_hierarchy_level`: `epic`, `story`, `task`, `subtask`
- `clean_jira.issue_status_category`: `to_do`, `in_progress`, `done`
- `clean_jira.user_role_type`: `assignee`, `reporter`, `creator`, `watcher`
- `clean_jira.sprint_status`: `future`, `active`, `closed`
- `clean_jira.release_status`: `unreleased`, `released`, `archived`

## 4. Дополнительно

- В схеме есть представление `clean_jira.v_unique_users` (это **VIEW**, не таблица).
- По таблице `issues`: колонка `resolution_id` добавлена миграцией `0029`, а `issue_status_changelog` добавлена миграцией `0007`.
