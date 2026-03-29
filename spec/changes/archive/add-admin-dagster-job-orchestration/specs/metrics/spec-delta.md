# Spec Delta: Admin Dagster Job Orchestration

## ADDED Requirements

### Requirement: Admin-Triggered Dagster Jobs
The system SHALL allow authenticated admin users to trigger supported Dagster jobs from Admin Studio.

#### Scenario: Launch supported job
GIVEN an authenticated admin user
WHEN the user requests launch of a supported job (`jira_sync_job`, `jira_raw_job`, `jira_clean_job`, or `metrics_refresh_job`)
THEN the system SHALL launch the Dagster run
AND return the Dagster `run_id` and initial run status.

#### Scenario: Reject unsupported job
GIVEN an authenticated admin user
WHEN the user requests launch of a job outside the allow-list
THEN the system SHALL reject the request with a client error.

### Requirement: Dagster Run Monitoring in Admin Studio
The system SHALL expose run monitoring data required for admin operations.

#### Scenario: Poll run details
GIVEN a launched Dagster run
WHEN admin UI polls run details
THEN the system SHALL return run status, start/end timestamps, and step-level status summary.

#### Scenario: Show errors for failed run
GIVEN a run that fails
WHEN admin UI requests run details
THEN the system SHALL return recent failure/error events for display.

### Requirement: Dedicated Admin Orchestration Page
The system SHALL provide a dedicated Admin Studio page/section for job orchestration separate from metrics configuration forms.

#### Scenario: Separate orchestration surface
GIVEN an authenticated admin user
WHEN the user navigates in Admin Studio
THEN the user SHALL be able to open a dedicated orchestration page/section
AND run/monitor jobs without using the Dagster web UI.
