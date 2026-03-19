# Velocity Jira Alignment Plan

## Goal

Align platform velocity metrics with Jira Cloud Velocity Chart semantics for TWAD,
starting with ADS sprints 24-28 as acceptance baseline and then scaling to all projects.

## Scope

- Metric: `velocity` (`velocity_planned_sp`, `velocity_completed_sp`, counts variants)
- Pipeline path:
  - `pipelines/assets/metrics/velocity.py`
  - `pipelines/calculations/velocity.py`
- Validation baseline:
  - `sprints_velocity.md` (provided by user)
  - Jira board-level sprint report exports for ADS 24-28

## Semantic Contract (Target)

1. Board-specific calculation only (respect board mapping/filter assumptions).
2. Plan/Commitment = estimates of issues in sprint at sprint start snapshot.
3. Fact/Completed = estimates of issues in Done at sprint end snapshot.
4. Done is defined by right-most board column mapping.
5. Sub-tasks are excluded.
6. Velocity chart reporting should use completed sprints only.

## Implemented in current iteration

1. Done status detection switched to board mapping first:
   - right-most board column statuses are primary source
   - fallback to "done" column name and status category only when mapping is insufficient
2. Velocity asset now processes completed sprints only:
   - `s.complete_date IS NOT NULL`
3. Velocity asset fallback sprint membership now uses active links only:
   - `clean_jira.sprint_issues.is_active = true`

## Remaining work (next iterations)

### Phase 1 - Golden dataset and deterministic acceptance

1. Create issue-level golden fixtures for ADS 24-28:
   - commitment set
   - completed set
   - SP at sprint start/end
   - removed/added markers
2. Add automated tests that assert:
   - sprint-level plan/fact exact match
   - issue-level membership exact match

Acceptance:
- 100% match for ADS 24-28 fixtures.

### Phase 2 - Time-aware membership hardening

1. Split commitment computation into explicit states:
   - membership at start
   - membership at end
2. Remove ambiguous fallback behavior for missing changelog rows:
   - emit diagnostics/confidence flags
   - do not silently infer from current state when historical evidence is absent

Acceptance:
- no unresolved "inferred without evidence" rows for ADS 24-28.

### Phase 3 - Estimate snapshot hardening

1. Enforce strict SP snapshot-at-time logic:
   - if historical value is unavailable, mark as low confidence
2. Expose count of low-confidence issues in metadata and quality checks.

Acceptance:
- deterministic SP provenance for every issue included in plan/fact.

### Phase 4 - Quality gates before fact write

1. Add pre-write checks:
   - done mapping resolvable
   - membership timeline consistency
   - estimate snapshot completeness threshold
2. Fail metric write on critical inconsistencies.

Acceptance:
- bad source states are blocked from writing incorrect fact rows.

### Phase 5 - Rollout and backfill

1. Run old/new comparison in parallel for 2-3 cycles.
2. Backfill historical velocity facts with new algorithm.
3. Switch downstream dashboards/API to aligned facts.

Acceptance:
- stable parity with Jira for acceptance sprints and explainable deltas outside baseline.

## Risks and mitigations

1. Incomplete historical changelog:
   - Mitigation: confidence flags + explicit exclusions from strict parity set.
2. Board configuration drift over time:
   - Mitigation: snapshot board mapping per sprint window where possible.
3. Backfill performance:
   - Mitigation: project-batched recomputation and bounded time windows.

## Operational checklist

1. Recalculate velocity facts after deployment:
   - run `calculate_velocity` asset
2. Re-run sprint comparison script:
   - `python scripts/compare_sprints_velocity_with_db.py`
3. Verify ADS 24-28 diff report and investigate remaining mismatches.
