# Spec Delta: Metric Store Seeding

## ADDED Requirements

### Requirement: Metric Store Seeding Logic
WHEN the seeding script is executed,
the system SHALL populate the foundational metadata and dimension tables in the `metrics` schema.

#### Scenario: Metadata Seeding
GIVEN the metrics schema exists
WHEN `scripts/seed_metric_store.py` is executed
THEN the `metrics.grains`, `metrics.definitions`, `metrics.calculations`, and `metrics.units` tables are populated with core metric groups and calculation codes.
AND each calculation SHALL have the correct FK to its corresponding grain and definition.

#### Scenario: Dimension Data Seeding
GIVEN existing Jira projects in `clean_jira.projects`
WHEN the seeding script is executed
THEN the `metrics.dim_projects` table SHALL be populated with mappings between project IDs and keys.
AND the `metrics.dim_dates` table SHALL be generated for 2024-2030 (ISO standard).

#### Scenario: Rule Inference
GIVEN existing board columns in `clean_jira.board_columns`
WHEN the seeding script is executed
THEN the system SHALL infer `metrics.commitment_rules` by matching column names (e.g., "In Progress" as start, "Done" as end).
AND the system SHALL populate `metrics.slice_rules` for "By Issue Type" and "By Priority" for all metric groups.

### Requirement: Seeding Idempotency
WHEN the seeding script is executed multiple times,
the system SHALL perform upserts or deletions/re-inserts to ensure the final state is consistent and does not contain duplicates.
