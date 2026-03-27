# Spec Delta: Metrics Admin Studio and Config API

## ADDED Requirements

### Requirement: Admin Authentication for Configuration
The system SHALL require authenticated admin access for all metrics-admin endpoints.

#### Scenario: Admin login and token-based access
GIVEN an active `platform.users` record with `is_admin = true`
WHEN login is performed with valid credentials
THEN the system shall return an access token accepted by admin endpoints.

### Requirement: Contract-Driven Calculation Configuration
The system SHALL expose a contract catalog describing configuration requirements per calculation.

#### Scenario: Contract discovery
WHEN admin UI requests the contract catalog
THEN the response shall indicate for each `calc_code` whether unit binding, commitment rules, slicing, and settings are required/optional.

### Requirement: Metadata Catalog for clean_jira selection
The system SHALL expose catalog endpoints for selecting source metadata used in configs.

#### Scenario: Source data selection
WHEN admin UI loads project scope
THEN it shall be able to fetch projects, boards, board columns, statuses, issue types, custom fields, and clean_jira schema map.

### Requirement: Config CRUD in Metrics Schema
The system SHALL support API-based create/read/update/delete operations for metrics config tables.

#### Scenario: Manage commitment rules
WHEN admin updates commitment points for a project/board/calculation
THEN the system shall persist changes in `metrics.commitment_rules` with uniqueness guarantees.

#### Scenario: Manage calculation settings
WHEN admin configures parameterized metric settings
THEN the system shall persist JSON settings in `metrics.calculation_settings` (project-specific or global).

#### Scenario: Manage unit bindings
WHEN admin maps units to source fields
THEN the system shall persist project/global records in `metrics.units` and keep unique constraints valid.

#### Scenario: Manage slice rules
WHEN admin defines segmentation rules
THEN the system shall persist records in `metrics.slice_rules` and return effective rules by scope.

### Requirement: Configuration Validation API
The system SHALL provide validation diagnostics for project-level metric configuration completeness.

#### Scenario: Missing config detection
WHEN validation is requested for a project
THEN the response shall include missing unit mappings, missing commitment rules, and missing required calculation settings.

### Requirement: Separate Admin UI Runtime
The system SHALL run Streamlit Admin Studio as a dedicated container image/service.

#### Scenario: Independent deployment
WHEN docker compose is started
THEN the admin UI shall run in its own service and connect to API via network URL.
