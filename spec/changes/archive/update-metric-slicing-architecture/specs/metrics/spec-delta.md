# Spec Delta: Metric Slicing Architecture Updates

## MODIFIED Requirements

### Requirement: Segmented Metric Storage
WHEN a metric slice is stored,
the system SHALL link it to its originating rule using both `slice_rule_id` and `slice_rule_name`.

#### Scenario: Enhanced Slice Storage
GIVEN any metric slice table
THEN it SHALL contain a `slice_rule_id` column as a foreign key to `metrics.metric_slice_rules(id)`.

### Requirement: Dynamic Slicing Logic
WHEN a slice rule contains a `filter_condition`,
the system SHALL apply this filter to the source data before calculating metrics for the slice.

#### Scenario: Applying Filter Condition
GIVEN a slice rule "By Status" for "Bugs Only" with filter_condition = "type_name == 'Bug'"
WHEN metrics are calculated for this slice
THEN the system shall only process data matching the filter condition.
