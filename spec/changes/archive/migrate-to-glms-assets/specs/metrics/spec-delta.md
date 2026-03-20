# Spec Delta: All Metric Assets Migration to GLMS

## ADDED Requirements

### Requirement: Metric Metadata Resolution
The system SHALL provide a centralized mechanism to resolve metric IDs, project IDs, and calculation units from the database.
- Metadata MUST be resolved per-project and per-calculation.
- Resolved metadata MUST be cached within the process execution to minimize database overhead.

### Requirement: Dynamic Commitment Resolution
The system SHALL dynamically resolve workflow start and end columns ("commitment points") for flow metrics using the `metrics.commitment_rules` table.
- Resolution MUST fall back to a reasonable heuristic if no rules exist for a specific board.

### Requirement: Idempotent Metric Storage
The system SHALL support idempotent writes to the `metrics.fact_values` table using a DELETE + INSERT pattern.
- Each asset write operation SHALL delete existing rows for its specific `(metric_id, project_agg_id, time_id)` scope before inserting new rows.
- The write operation SHALL utilize the ADBC engine with the PostgreSQL `COPY` protocol for maximum performance.

## MODIFIED Requirements

### Requirement: Segmented Metric Storage
**REPLACES**: Previous Wide Table Requirement.
The system SHALL store all process metrics (Velocity, Lead Time, Throughput, CFD, Backlog Growth, TTM, Aging, Flow Efficiency) in a single unified `metrics.fact_values` table.
- Each row SHALL represent a single atomic value.
- Context (project, date, calculation, slice, entity) SHALL be provided through foreign keys and status columns.

#### Scenario: Unified Storage for Flow Metrics (Lead Time)
GIVEN a completed issue
WHEN the lead time calculation is executed
THEN the system SHALL store a single `lead_time_days` value in `metrics.fact_values`.
AND the row SHALL include `event_start_at` and `event_end_at` timestamps derived from the commitment rules.

#### Scenario: Unified Storage for Snapshot Metrics (CFD)
GIVEN a daily calculation run
WHEN the cumulative flow diagram calculation is executed
THEN the system SHALL store `cfd_count` values where `entity_type` is 'board_column' and `entity_id` is the column UUID.
AND the `slice_rule_id` SHALL be NULL.
