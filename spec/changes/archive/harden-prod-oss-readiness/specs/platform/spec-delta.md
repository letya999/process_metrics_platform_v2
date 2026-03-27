# Spec Delta: Platform Hardening for Production and OSS

## ADDED Requirements

### Requirement: Protected Integration and Project Management APIs
The system SHALL require authenticated admin bearer token access for integrations and projects CRUD/sync endpoints.

#### Scenario: Unauthorized caller
WHEN a request to `/api/v1/integrations` or `/api/v1/projects` endpoints is made without a valid bearer token
THEN the system shall return `401 Unauthorized`.

### Requirement: Stateless Admin Session Tokens
The system SHALL issue and verify stateless signed admin access tokens without relying on in-memory session storage.

#### Scenario: Process restart
GIVEN a previously issued non-expired token
WHEN API process restarts
THEN token verification shall continue to work if signing secret is unchanged.

### Requirement: Deterministic Validation Command
The system SHALL provide a concrete validation runner and fail `make validate` on validation errors.

#### Scenario: Validation script failure
WHEN validation checks fail or the validation script is missing
THEN `make validate` shall exit non-zero.

### Requirement: Immutable Runtime Image Selection
The system SHALL pin runtime image tags in compose files for production-affecting services.

#### Scenario: Metabase image reference
WHEN compose manifests are reviewed
THEN Metabase image reference shall not use `latest` tag.

### Requirement: OSS Documentation Consistency
The system SHALL avoid unresolved placeholders in public clone/security guidance.

#### Scenario: Repository bootstrap docs
WHEN users follow README/SECURITY setup instructions
THEN links and placeholders shall be concrete and consistent.

### Requirement: Policy Guardrails in Developer Workflow
The system SHALL enforce policy checks in local and CI workflows for known config/documentation regressions.

#### Scenario: Pre-commit and CI execution
WHEN lint/check workflows run
THEN policy checks shall fail on mutable tags (`:latest`) and placeholder org links (`your-org`).
