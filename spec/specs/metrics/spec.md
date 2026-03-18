# Metrics Specification

This capability manages the definition, calculation, and segmentation of process metrics.

## Requirements

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
