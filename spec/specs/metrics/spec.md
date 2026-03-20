# Metrics Specification

This capability manages the definition, calculation, and segmentation of process metrics.

## Requirements

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

### Requirement: Metric Slice Rules Definition
The system SHALL support defining rules for segmenting metrics into slices.
- Rules can be global (project_id = NULL) or project-specific.
- Rules can apply to all metrics (target_metric_table = 'default') or specific metrics.

#### Scenario: Global Slice Rule Application
GIVEN a global slice rule "By Issue Type" with target_metric_table = 'default'
WHEN metrics are calculated for any project
THEN the system shall apply this rule to generate segmented data in *_slices tables.

### Requirement: Segmented Metric Storage
The system SHALL store segmented metric data in dedicated slice tables.
- Each slice table MUST follow a consistent structure.
- Each slice MUST be linked to its originating rule and the specific value of the segment.

#### Scenario: Consistent Slice Table Structure
GIVEN any metric slice table (e.g., fact_velocity_slices)
THEN it SHALL contain columns for project_id, slice_rule_name, and slice_value.

### Requirement: Dynamic Slicing Logic
The system SHALL dynamically apply slicing rules during metric calculation.
- The logic MUST handle mapping between rule-defined grouping columns and source data columns.
- The logic MUST support filtering source data based on an optional filter condition.
