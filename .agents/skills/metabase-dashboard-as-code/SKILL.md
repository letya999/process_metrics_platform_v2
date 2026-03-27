---
name: metabase-dashboard-as-code
description: Metabase dashboard-as-code workflow for programmatic cards, charts,
  dashboard layout, and unified dashboard filters. Use when updating or creating
  BI packs under /bi and provisioning to Metabase.
vm0_secrets:
  - METABASE_TOKEN
  - MB_ADMIN_EMAIL
  - MB_ADMIN_PASSWORD
---

# Metabase Dashboard-as-Code

Use this skill when you need to manage Metabase programmatically as code:

- create/update cards (questions) from JSON specs
- create/update dashboards and place cards by layout
- define dashboard filters and apply them consistently to all cards
- validate all pack cards by executing real queries in Metabase
- deploy updates idempotently to dev/prod Metabase instances

## Scope

This project stores BI as code in:

```text
bi/
  main.py
  verify_metabase_pack.py
  providers/metabase/provider.py
  packs/metabase/<pack_name>/
    cards/*.json
    dashboards/*.json
    collections.json
```

## Authentication

Use one of two modes:

1. API key mode (preferred): `METABASE_API_KEY`
2. Session mode: `MB_ADMIN_EMAIL` + `MB_ADMIN_PASSWORD`

Base URL is `METABASE_URL`.

## Card Spec Contract

Each card JSON must include:

- `key` (stable pack key)
- `name` (human-readable card name)
- `query` (native SQL)

Optional:

- `description`
- `display`
- `collection`
- `visualization_settings`
- `template_tags` (override inferred `{{tag}}` metadata)

### SQL Template Variables

For dashboard filters, use Metabase native vars:

- `[[ AND project_key = {{project_key}} ]]`
- `[[ AND full_date >= {{date_from}} ]]`
- `[[ AND full_date <= {{date_to}} ]]`

Provider auto-generates `template-tags` for detected `{{...}}` variables.

## Dashboard Spec Contract

Each dashboard JSON must include:

- `name`
- `layout` (array)

Each layout item must include:

- `card_key`
- `row`, `col`, `size_x`, `size_y`

Optional dashboard filters:

```json
"filters": [
  { "id": "project_key", "name": "Project Key", "slug": "project_key", "type": "category", "template_tag": "project_key" },
  { "id": "date_from", "name": "Date From", "slug": "date_from", "type": "date/single", "template_tag": "date_from" },
  { "id": "date_to", "name": "Date To", "slug": "date_to", "type": "date/single", "template_tag": "date_to" }
]
```

Provider behavior:

- builds dashboard `parameters` from `filters`
- builds `parameter_mappings` for each dashcard using `template_tag`
- ensures unified filters are applied across all cards unless overridden

## Runbook

### 1. Provision pack

```bash
python -m bi.main --provider metabase --pack process_metrics_v1
```

### 2. Validate all cards execute

```bash
python bi/verify_metabase_pack.py --provider metabase --pack process_metrics_v1 --url "$METABASE_URL"
```

### 3. UI smoke check

Open dashboard URL and verify:

- top filters are visible
- charts render successfully
- filter changes affect all mapped cards

## Production Workflow

1. Update `cards/*.json` and `dashboards/*.json` in Git.
2. Run local provisioning + `verify_metabase_pack.py`.
3. Deploy to prod and rerun provisioning.
4. Run validation against prod Metabase URL.

Because provisioning is idempotent (upsert by names/keys), this is safe for repeated deploys.

## Common Pitfalls

- Using dropped relations (for this project prefer `metrics.v_facts` and current schema objects).
- Forgetting `{{template_var}}` in SQL while defining dashboard filters.
- Manually relying on Metabase numeric IDs in pack files.
- Skipping pack validation before prod rollout.

## Definition of Done

- `python -m bi.main ...` succeeds
- `python bi/verify_metabase_pack.py ...` returns `PACK VALIDATION OK`
- Dashboard opens in UI with working filters and charts
