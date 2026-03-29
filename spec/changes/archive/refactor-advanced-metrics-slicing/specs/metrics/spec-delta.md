# Specification Delta: Metrics Refactoring and Slicing

## MODIFIED Requirements

### Requirement: Work Item Aging Calculation
THE system SHALL calculate the age of each unresolved issue in days, from its commitment start point (or creation date) to the current time.

#### Scenario: Sliced Aging Calculation
GIVEN a set of unresolved issues
AND active slicing rules (e.g., by issue type)
WHEN the aging calculation is triggered
THEN the system SHALL calculate the age for each issue
AND SHALL generate sliced fact values according to the active rules.

### Requirement: Flow Efficiency Calculation
THE system SHALL calculate active time, wait time, and efficiency percentage for completed issues.

#### Scenario: Sliced Flow Efficiency Calculation
GIVEN a set of completed issues
AND active slicing rules (e.g., by priority)
WHEN the flow efficiency calculation is triggered
THEN the system SHALL calculate active, wait, and efficiency metrics for each issue
AND SHALL generate sliced fact values according to the active rules.
