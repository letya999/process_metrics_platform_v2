# Open-Source Preparation Plan
Date: 2026-03-27
Branch: feat/opensource-prep

## Out of Scope (Tech Debt / Manual)
- P0-1: Secret rotation (Jira token, DB passwords, SECRET_KEY, Metabase passwords) — mark as TECH_DEBT
- P1-1: git rm --cached plans/, .agents/, etc. — manual git operation, skip

---

## Tasks

### TASK 1: Caddyfile → Caddyfile.example
**File**: `Caddyfile` → rename/replace with `Caddyfile.example`

Replace ALL hardcoded values with environment variable references. The example file must be fully functional as a template.

Current hardcoded values to replace:
- IP `134.209.90.127` → `${SERVER_IP}`
- All nip.io domains:
  - `metrics.134.209.90.127.nip.io` → `metrics.${SERVER_IP}.nip.io`
  - `dagster.134.209.90.127.nip.io` → `dagster.${SERVER_IP}.nip.io`
  - `api.134.209.90.127.nip.io` → `api.${SERVER_IP}.nip.io`
  - `admin.134.209.90.127.nip.io` → `admin.${SERVER_IP}.nip.io`
- bcrypt hash `$2a$14$PhYoC4cISk0DMibmnE7ozuiPjO18h2u26BLdnJ5FbSVzh5urqYsi6` → `{$DAGSTER_BASIC_AUTH_HASH}`

Also add a comment at the top explaining each env var:
```
# Required environment variables:
#   SERVER_IP            - Your server's public IP address
#   DAGSTER_BASIC_AUTH_HASH - Generate with: caddy hash-password --plaintext YOUR_PASSWORD
```

The original `Caddyfile` content (for reference - DO NOT TOUCH the actual Caddyfile since it's tracked, just create Caddyfile.example as a new file alongside it):
Read the existing `Caddyfile` and produce `Caddyfile.example` with substitutions applied.

Also add to `.env.example` the new variable:
```
# Caddy reverse proxy
SERVER_IP=YOUR_SERVER_IP_HERE
DAGSTER_BASIC_AUTH_HASH=<run: caddy hash-password --plaintext YOUR_PASSWORD>
```

---

### TASK 2: Fix tests/conftest.py - remove hardcoded DB password
**File**: `tests/conftest.py`

Line 253: Replace hardcoded password with environment variable:
```python
# BEFORE:
password = "woJX9+pYcU+y2JApOCcqs5HP"
db_name = "process_metrics_v2"
db_url = f"postgresql://postgres:{password}@localhost:5432/{db_name}"

# AFTER:
password = os.environ.get("POSTGRES_PASSWORD", "postgres")
db_name = os.environ.get("POSTGRES_DB", "process_metrics_v2")
db_url = f"postgresql://postgres:{password}@localhost:5432/{db_name}"
```

Make sure `import os` is present at the top of conftest.py.

---

### TASK 3: Replace internal Jira keys in test files
**Files**:
- `tests/validation/test_velocity_incident_regression.py`
- Any other test files referencing TWAD, TWMOB

Replace all real project keys with generic placeholders:
- `TWAD` → `PROJ`
- `TWMOB` → `PROJ2`
- `TWAD-436` → `PROJ-436`, `TWAD-438` → `PROJ-438`, etc. (keep issue numbers, change prefix)
- Sprint names like "ADS 24", "ADS 25" etc → "SPRINT 24", "SPRINT 25"
- Any reference to `neuralab.atlassian.net` → `your-org.atlassian.net`
- Any reference to `twinby.com` emails → `example.com`

Search all tracked Python files for: TWAD, TWMOB, neuralab, twinby, a.letyushev

---

### TASK 4: Remove diagnostic scripts with internal references
**Directory**: `scripts/`

DELETE (git rm) the following diagnostic/one-off scripts that contain internal project keys or are specific to internal incidents:
- `scripts/compare_sprints_velocity_with_db.py` — hardcoded `'TWAD'`
- `scripts/reconcile_ads_24_28_issue_level.py` — internal ADS incident
- `scripts/check_db_schema.py` — hardcoded `'TWMOB'`, `'TWAD'`
- `scripts/jira_ads_24_28_sprintreport.json` — real Jira data
- `scripts/jira_ads_24_28_sprintreport_current.json` — real Jira data
- `scripts/investigate_rules.py` — diagnostic
- `scripts/diagnose_slicing.py` — diagnostic
- `scripts/dump_clean_jira_schema.py` — diagnostic
- `scripts/dump_metrics.py` — diagnostic
- `scripts/fix_slice_rules.py` — diagnostic
- `scripts/simulate_velocity.py` — diagnostic

Keep operational scripts:
- `scripts/deploy.sh`
- `scripts/backup_postgres.sh`
- `scripts/generate_secrets.py`
- `scripts/setup_metabase.py`
- `scripts/verify_setup.sh`
- `scripts/run_validation.py`
- `scripts/lint_local.py`
- `scripts/add_missing_schema_comments.py`

For any script you're unsure about: if it contains `TWAD`, `TWMOB`, `neuralab`, `twinby`, or a hardcoded database URL with real credentials — delete it.

---

### TASK 5: Fix \restrict session tokens in SQL schema files
**Files**:
- `db/schemas/raw_jira_schema.sql`
- `db/schemas/metrics_schema.sql`
- `db/schemas/clean_jira_schema.sql`

Remove lines starting with `\restrict` — these are pg_dump session fingerprints and should not be in tracked schema files.

---

### TASK 6: Fix migration - system user password hash
**File**: `db/migrations/versions/0004_add_system_user.py`

Find the INSERT for system@metrics.local user. Replace `password_hash = 'system'` (plaintext) with a proper bcrypt hash of a non-guessable string, e.g.:
```python
# Use bcrypt hash of 'system-account-no-login' with cost 12
# Hash: $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGnvospkrfauScnWBuPMjZNv/em
```

Or better: add a comment explaining this is a service account and set `is_active = false` so no login is possible regardless of the hash. Check the ORM model to see if there's an `is_active` field.

---

### TASK 7: Create LICENSE file (MIT)
**File**: `LICENSE` (create at repo root)

Create a proper MIT License file. Copyright holder: use generic "process-metrics-platform contributors" (do NOT use personal name or company name). Year: 2024-2026.

```
MIT License

Copyright (c) 2024-2026 process-metrics-platform contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

### TASK 8: Create CONTRIBUTING.md
**File**: `CONTRIBUTING.md` (create at repo root)

Cover:
1. Prerequisites (Python 3.11+, Docker, make)
2. Local setup steps (clone, .env, docker compose up, migrations)
3. Running tests: `make test`
4. Code style: ruff, mypy, `make lint`
5. Branch naming: `feature/`, `bugfix/`, `hotfix/`
6. Commit message format: Conventional Commits (feat, fix, refactor, docs, test, chore)
7. PR process: fork → branch → tests pass → PR to main
8. No AI attribution in commits

Keep it concise — max 80-100 lines.

---

### TASK 9: Create SECURITY.md
**File**: `SECURITY.md` (create at repo root)

Standard vulnerability disclosure policy:
- Supported versions table (latest release)
- How to report: open a GitHub Security Advisory (not a public issue)
- Response timeline: acknowledge within 48h, fix within 30 days
- What NOT to do: no public disclosure before fix

---

### TASK 10: Translate bi/README.md to English
**File**: `bi/README.md`

The entire file (55 lines) is in Russian. Translate all content to English preserving all technical structure, code examples, paths, and commands exactly. Only translate the natural language text (headers, descriptions, instructions, comments).

---

### TASK 11: Translate Russian comments in source files
**Files to fix**:

1. `docker-compose.simple.yml` — all Russian inline comments (e.g., `# НЕ открываем порт наружу!` → `# Do not expose port externally!`)
2. `streamlit_admin/app.py` — Russian UI strings in `help=` parameters and any other user-visible text (e.g., `help="Фильтр данных по проекту."` → `help="Filter data by project."`)
3. `scripts/backup_postgres.sh` — any Russian comments

Search for Cyrillic characters: pattern `[а-яА-ЯёЁ]` across all .py, .yaml, .yml, .sh files.

---

### TASK 12: Fix README.md
**File**: `README.md`

Issues to fix:
1. **Encoding**: The file appears UTF-16 encoded. Re-save as UTF-8 (no BOM). Preserve all content exactly.
2. **Broken links**: Remove or replace these two links since docs/ directory doesn't exist:
   - `[Read the Simple Deployment Guide](docs/SIMPLE_DEPLOY_GUIDE.md)` → change to reference `CONTRIBUTING.md` or just remove the link
   - `[Audit Report](docs/AUDIT_REPORT.md)` → remove this line
3. **Placeholder GitHub URL**: `https://github.com/your-org/process-metrics-platform-v2.git` — leave as-is (it's a template placeholder, acceptable for open-source release)
4. **License badge**: Update `[![License](LICENSE)]` link to point to actual `LICENSE` file
5. **Version badges**:
   - FastAPI badge: check pyproject.toml and update from `0.109` to actual minimum version
   - Dagster badge: check pyproject.toml and update from `1.6` to actual minimum version

Read pyproject.toml to get actual version constraints before updating badges.

---

### TASK 13: Fix silent error handling in metrics API
**File**: `app/api/metrics.py`

Lines 223, 313, 387 — bare `except Exception:` that returns empty results silently.

Replace each instance:
```python
# BEFORE:
except Exception:
    return LeadTimeResponse(items=[], total_count=0)

# AFTER:
except Exception:
    logger.exception("Failed to query lead time metrics")
    raise HTTPException(status_code=500, detail="Internal error querying metrics")
```

Apply same pattern to velocity and throughput endpoints. Make sure `logger` is imported (check if it's already defined in the file). Make sure `HTTPException` is imported from fastapi.

---

### TASK 14: Fix .env.example weak password placeholder
**File**: `.env.example`

Find `MB_ADMIN_PASSWORD=strong_password_123!` and replace with `MB_ADMIN_PASSWORD=<CHANGE_ME_GENERATE_STRONG_PASSWORD>`.

Also review all other example values — any that look like real passwords should use `<CHANGE_ME_...>` format.

---

### TASK 15: Pin metabase Docker image version
**File**: `docker-compose.simple.yml`

Find `metabase/metabase:latest` and replace with a specific pinned version, e.g. `metabase/metabase:v0.51.4` (use the latest stable release as of early 2026).

---

### TASK 16: Add SERVER_IP and DAGSTER_BASIC_AUTH_HASH to docker-compose
**File**: `docker-compose.simple.yml`

If there are any remaining hardcoded IPs or domain names in docker-compose.simple.yml (e.g., in CORS_ALLOWED_ORIGINS or similar), replace them with `${SERVER_IP}` references consistent with the Caddyfile.example approach.

---

## Execution Order

Run tasks in this order to avoid conflicts:
1. Task 2 (conftest.py - high priority security)
2. Task 3 (test file internal refs)
3. Task 4 (delete diagnostic scripts)
4. Task 1 (Caddyfile.example)
5. Task 5 (SQL \restrict)
6. Task 6 (migration password hash)
7. Task 7 (LICENSE)
8. Task 8 (CONTRIBUTING.md)
9. Task 9 (SECURITY.md)
10. Task 10 (bi/README.md translation)
11. Task 11 (Russian comments)
12. Task 12 (README.md fixes)
13. Task 13 (metrics API error handling)
14. Task 14 (.env.example)
15. Task 15 (metabase pin)
16. Task 16 (docker-compose SERVER_IP)

## Notes
- Do NOT add authentication to public API endpoints (P4-1) — this requires architectural discussion
- Do NOT git rm or change .gitignore — manual operation
- Do NOT rotate any secrets — tech debt, manual operation
- For every file modified: read it first, then make minimal targeted changes
- English only in all output (code, comments, docs)
- No emojis, no AI attribution
