# Implementation Tasks: Seed Generic Long Metric Store Foundation

1.  **Script Infrastructure**:
    *   [ ] Create `scripts/seed_metric_store.py` with SQLAlchemy connection logic from `.env`.
    *   [ ] Set up logging and error handling for the seeding script.
2.  **Metadata Seeding (Static)**:
    *   [ ] Seed `metrics.grains` with static codes (`issue`, `sprint`, `week`, `day`, `release`).
    *   [ ] Seed `metrics.definitions` with 8 core metric groups (velocity, lead_time, throughput, cfd, backlog_growth, ttm, aging, flow_efficiency).
    *   [ ] Seed `metrics.calculations` with 18 atomic calc codes with correct FK to grains and definitions.
    *   [ ] Seed `metrics.units` with global defaults (project_id=NULL) for story_points, issues, days, hours, percent.
3.  **Dimension Seeding (Dynamic)**:
    *   [ ] Generate `metrics.dim_dates` for 2024-2030 (ISO week, month, quarter, year).
    *   [ ] Populate `metrics.dim_projects` from `clean_jira.projects` (sync current projects).
4.  **Rule Initialization**:
    *   [ ] Seed default `metrics.slice_rules` for "By Issue Type" and "By Priority" targeting all definitions.
    *   [ ] Infer `metrics.commitment_rules` by scanning `clean_jira.board_columns` for "In Progress" and "Done" patterns.
5.  **Validation & Testing**:
    *   [ ] Run the script and verify row counts in all target tables.
    *   [ ] Verify the `metrics.v_facts` view can perform basic joins without errors.
    *   [ ] Document usage in `README.md` or as a `make` command.
