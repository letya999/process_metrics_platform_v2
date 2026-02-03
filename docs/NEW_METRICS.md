# New Performance Metrics

This document describes the newly added performance metrics in the Process Metrics Platform v2.

## Overview

Four new metric categories have been added to provide comprehensive insights into team performance and project health:

1. **Throughput** - Issues completed per week
2. **Cumulative Flow Diagram (CFD)** - Daily status distribution
3. **Backlog Health** - Backlog size, age, and staleness
4. **Time to Market** - Creation to release duration

## 1. Throughput Metrics

### Description
Throughput measures the number of issues completed over time, aggregated by week.

### Key Metrics
- **Weekly Throughput**: Number of issues completed per week by type
- **Average Lead Time**: Average lead time for completed issues
- **Throughput Trends**: Min, max, and average weekly throughput

### Data Tables
- `metrics.fact_throughput` - Weekly throughput facts
- `metrics.fact_throughput_aggregates` - Summary statistics
- `metrics.mv_throughput_weekly` - View for BI tools

### Business Rules
- Issues are counted by their completion date (when they reached "Done" status)
- Weekly periods run Monday to Sunday (ISO week standard)
- Throughput is calculated per project and issue type

### Example Query
```sql
-- Get weekly throughput for a project
SELECT
    week_start_date,
    week_end_date,
    issue_type,
    issues_completed,
    avg_lead_time_days
FROM metrics.mv_throughput_weekly
WHERE project_key = 'PROJ'
ORDER BY week_start_date DESC
LIMIT 12;  -- Last 12 weeks
```

### Dagster Asset
- **Asset**: `calculate_throughput`
- **Dependencies**: `clean_jira_issues`, `clean_jira_issue_status_changelog`, `clean_jira_board_columns`
- **Refresh**: After each data sync

## 2. Cumulative Flow Diagram (CFD)

### Description
CFD shows how many issues are in each status on each day, providing visibility into workflow bottlenecks and flow patterns.

### Key Metrics
- **Daily Status Counts**: Number of issues per status per day
- **Flow Trends**: Increasing/decreasing/stable trends per status
- **Average Daily Count**: Average number of issues per status

### Data Tables
- `metrics.fact_cfd` - Daily status counts (90 days back)
- `metrics.fact_cfd_aggregates` - Summary statistics and trends
- `metrics.mv_cfd` - View for BI tools

### Business Rules
- Tracks issue status on each date over the last 90 days
- Uses status changelog to determine historical status
- Includes all statuses configured in board columns
- Excludes issues created after the observation date

### Example Query
```sql
-- Get CFD data for last 30 days
SELECT
    date,
    status_name,
    issue_count,
    column_position
FROM metrics.mv_cfd
WHERE project_key = 'PROJ'
  AND date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date, column_position;
```

### Visualization Tips
- Use stacked area chart for CFD visualization
- Order statuses by `column_position` for correct workflow sequence
- Color by `status_category` (to_do, in_progress, done)

### Dagster Asset
- **Asset**: `calculate_cumulative_flow_diagram`
- **Dependencies**: `clean_jira_issues`, `clean_jira_issue_statuses`, `clean_jira_issue_status_changelog`
- **Refresh**: After each data sync

## 3. Backlog Health Metrics

### Description
Backlog Health metrics assess the quality and manageability of the product backlog.

### Key Metrics
- **Backlog Size**: Total number of open (non-Done) issues
- **Average Age**: Average days since issue creation
- **Stale Issues**: Issues not updated for 30+ days
- **Oldest Issue**: Age of the oldest open issue
- **Backlog Growth**: New issues added in last week/month
- **Distribution**: Breakdown by issue type and priority
- **Age Distribution**: Issues grouped by age buckets

### Data Tables
- `metrics.fact_backlog_health` - Main health metrics
- `metrics.fact_backlog_distribution` - Type/priority breakdown
- `metrics.fact_backlog_age_distribution` - Age buckets
- `metrics.mv_backlog_health` - View for BI tools

### Business Rules
- Backlog includes all issues NOT in "done" status category
- Stale threshold: 30 days without updates (configurable)
- Age buckets:
  - 0-7 days (new)
  - 8-30 days (recent)
  - 31-90 days (aging)
  - 91+ days (old)

### Example Queries
```sql
-- Get overall backlog health
SELECT
    project_name,
    total_backlog_size,
    avg_age_days,
    stale_percentage,
    oldest_issue_days,
    backlog_growth_last_month
FROM metrics.mv_backlog_health
WHERE project_key = 'PROJ';

-- Get backlog distribution by type
SELECT
    issue_type,
    priority,
    issue_count,
    percentage
FROM metrics.mv_backlog_distribution
WHERE project_key = 'PROJ'
ORDER BY issue_count DESC;
```

### Health Indicators
- **Healthy Backlog**:
  - Stale percentage < 20%
  - Average age < 60 days
  - Growth rate positive but controlled
- **Warning Signs**:
  - Stale percentage > 30%
  - Average age > 90 days
  - Negative growth (shrinking backlog may indicate lack of planning)

### Dagster Asset
- **Asset**: `calculate_backlog_health`
- **Dependencies**: `clean_jira_issues`, `clean_jira_issue_statuses`, `clean_jira_field_values`
- **Refresh**: After each data sync

## 4. Time to Market (TTM) Metrics

### Description
Time to Market measures the duration from idea/creation to production release for features and epics.

### Key Metrics
- **Time to Market**: Days from creation to release
- **TTM Percentiles**: P50 (median), P90 for benchmarking
- **Release Cadence**: Frequency and regularity of releases
- **Average Gap**: Days between consecutive releases

### Data Tables
- `metrics.fact_time_to_market` - Per-issue TTM
- `metrics.fact_ttm_aggregates` - Summary statistics
- `metrics.fact_release_cadence` - Release frequency
- `metrics.mv_time_to_market` - View for BI tools

### Business Rules
- Focuses on high-level items: Epics, Stories, Features
- Release date determined by (in priority):
  1. Actual release date from fix_versions
  2. First entry to "Done" status
  3. Issue resolved_at date
- Release cadence calculated from last 180 days

### Example Queries
```sql
-- Get recent TTM for features
SELECT
    issue_key,
    issue_type,
    created_at,
    released_at,
    time_to_market_days,
    time_to_market_hours
FROM metrics.mv_time_to_market
WHERE project_key = 'PROJ'
  AND released_at >= CURRENT_DATE - INTERVAL '6 months'
ORDER BY released_at DESC;

-- Get TTM aggregates by type
SELECT
    issue_type,
    total_issues,
    avg_ttm_days,
    median_ttm_days,
    p90_ttm_days
FROM metrics.fact_ttm_aggregates
WHERE project_id = '...'
ORDER BY avg_ttm_days;

-- Get release cadence
SELECT
    project_name,
    total_releases,
    avg_days_between_releases,
    releases_per_month
FROM metrics.mv_release_cadence
WHERE project_key = 'PROJ';
```

### Benchmarks
- **Fast TTM**: < 30 days (for stories/features)
- **Average TTM**: 30-90 days
- **Slow TTM**: > 90 days
- **Good Release Cadence**: 2-4 releases per month

### Dagster Asset
- **Asset**: `calculate_time_to_market`
- **Dependencies**: `clean_jira_issues`, `clean_jira_releases`, `clean_jira_release_issues`
- **Refresh**: After each data sync

## Implementation Details

### Calculation Engine
All new metrics use **Python/Polars** for calculation:
- Fast, memory-efficient DataFrame operations
- Debuggable and testable business logic
- Located in `pipelines/calculations/`

### Architecture
```
Raw Data (clean_jira.*)
    ↓
Polars Calculations (pipelines/calculations/)
    ↓
Fact Tables (metrics.fact_*)
    ↓
SQL Views (metrics.mv_*)
    ↓
BI Tools (Metabase, Grafana)
```

### Migration
- **Migration**: `0012_add_new_performance_metrics.py`
- Creates all necessary fact tables
- Run with: `alembic upgrade head`

### Dagster Orchestration
All new metrics are Dagster assets that:
1. Read from `clean_jira` schema
2. Calculate metrics using Polars
3. Write to `metrics.fact_*` tables
4. Automatically update SQL views

## Usage in Metabase

### Recommended Dashboards

#### 1. Throughput Dashboard
- **Line Chart**: Weekly throughput over time
- **Bar Chart**: Throughput by issue type
- **Metric**: Average weekly throughput

#### 2. CFD Dashboard
- **Stacked Area Chart**: Daily status counts
- **Table**: Status trends (increasing/decreasing/stable)

#### 3. Backlog Health Dashboard
- **Metric Cards**: Total size, stale %, avg age
- **Pie Chart**: Distribution by type
- **Bar Chart**: Age distribution buckets
- **Trend**: Backlog growth over time

#### 4. Time to Market Dashboard
- **Histogram**: TTM distribution
- **Line Chart**: Median TTM over time
- **Metric**: P90 TTM
- **Bar Chart**: Release cadence

## Troubleshooting

### No Throughput Data
- Check that issues have completion dates
- Verify board "Done" column configuration
- Review status changelog data

### Empty CFD
- Ensure issues have status history
- Check date range (default: 90 days back)
- Verify issue_statuses table is populated

### Missing Backlog Health
- Check that open issues exist (not all "done")
- Verify issue_statuses categories are correct

### No TTM Data
- Ensure high-level issues (Epics/Stories) exist
- Check release data in `clean_jira.releases`
- Verify issues have resolved_at or release dates

## Future Enhancements

Potential additions:
- **Throughput**: Predictable throughput bands (confidence intervals)
- **CFD**: Automated bottleneck detection
- **Backlog Health**: Priority aging (high-priority old issues)
- **TTM**: Feature complexity correlation
- **All**: Slice by team, epic, or custom fields
