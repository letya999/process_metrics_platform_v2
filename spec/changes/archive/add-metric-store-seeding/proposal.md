# Proposal: Seed Generic Long Metric Store Foundation

**Change ID**: add-metric-store-seeding
**Scope**: Database Seeding & Metadata Setup

## Why
The transition to the Generic Long Metric Store (GLMS) architecture requires a set of foundational metadata (grains, definitions, calculations, units) and dimension data (dates, projects) to be present in the database before metrics can be calculated and stored in the new `fact_values` table. Manually populating these tables is error-prone, and a reproducible script is needed for development, testing, and production setup.

## What Changes
1.  **New Script**: `scripts/seed_metric_store.py` - A Python script using SQLAlchemy and Polars to populate the `metrics.*` schema.
2.  **Metadata Seeding**:
    *   `metrics.grains`: Seed with `issue`, `sprint`, `week`, `day`, `release`.
    *   `metrics.definitions`: Seed with 8 metric groups (velocity, lead_time, etc.).
    *   `metrics.calculations`: Seed with 18 atomic calculation codes (e.g., `lead_time_days`, `velocity_completed_sp`).
    *   `metrics.units`: Seed global defaults for `issues`, `story_points`, `days`, `hours`, `percent`.
3.  **Dimension Seeding**:
    *   `metrics.dim_dates`: Generate calendar data for 2024-2030.
    *   `metrics.dim_projects`: Map all projects from `clean_jira.projects` to `metrics.dim_projects`.
4.  **Rule Initialization**:
    *   `metrics.slice_rules`: Initialize default rules for `By Issue Type` and `By Priority`.
    *   `metrics.commitment_rules`: Infer initial commitment points for existing boards by matching column names (e.g., "In Progress" -> start, "Done" -> end).

## Impact
*   **Database**: Populates the foundational tables in the `metrics` schema.
*   **Dagster**: Enables Dagster assets to resolve metric IDs and project IDs from the new schema.
*   **BI (Metabase)**: Provides the necessary metadata for the `v_facts` view to display correct labels and categories.
*   **Developers**: Provides a simple command to reset/initialize the metrics foundation.
