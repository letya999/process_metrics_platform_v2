# Implementation Tasks

1. [x] Protect integrations/projects routes with admin bearer auth dependency.
2. [x] Replace `_TOKEN_STORE`-based admin sessions with stateless signed tokens.
3. [x] Add `scripts/run_validation.py` and make `make validate` fail on validation errors.
4. [x] Pin `metabase:latest` to a concrete version in compose manifests (already pinned as `v0.51.4`).
5. [x] Fix OSS placeholders in `README.md` and `SECURITY.md`.
6. [x] Add policy-check script and wire it into lint/pre-commit.
7. [x] Add CI workflow enforcing lint/tests/policy checks.
8. [x] Run targeted tests/checks and document results.
