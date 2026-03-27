# Proposal: Production and OSS Hardening Baseline

## Why
The platform has gaps that block reliable production operation and open-source readiness: missing auth on integration/project CRUD APIs, non-scalable in-memory admin sessions, fragile validation command behavior, mutable image tags, and inconsistent OSS docs placeholders.

## What Changes
1. Enforce bearer-auth protection on integrations/projects API routes.
2. Replace in-memory admin token store with stateless signed tokens (no Redis, no extra DB).
3. Make `make validate` deterministic and fail-fast by adding a concrete validation runner script.
4. Pin mutable container tags (Metabase) to explicit versions in compose files.
5. Replace OSS placeholders (`your-org`) in README/SECURITY with concrete guidance.
6. Add policy checks (script + pre-commit + CI) for known regressions: missing validation script wiring, mutable tags, and placeholder links.
7. Keep `Caddyfile` unchanged in this change set per maintainer decision.
8. Keep Dagster runtime topology changes out of scope for now per maintainer decision.

## Impact
- Improves API security posture for data-management endpoints.
- Removes horizontal-scaling bottleneck caused by process-local admin sessions.
- Makes local/CI validation behavior transparent and actionable.
- Improves reproducibility of deployments and OSS onboarding quality.
