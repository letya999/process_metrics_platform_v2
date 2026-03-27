---
name: streamlit-admin-ui
description: Streamlit admin UI patterns. UI calls FastAPI only - never direct DB. API_BASE uses Docker service DNS (hardcoded http://app:8000/api/v1).
triggers:
  - "streamlit"
  - "admin ui"
  - "bi/"
  - "admin page"
  - "admin-ui"
context:
  - agent.md
  - .agents/skills/08-platform-layer.md
---

# Skill: Streamlit Admin UI

The `bi/` module and Streamlit admin-ui service. See also installed marketplace skill `developing-with-streamlit`.

---

## Current State (as of 2026-03-27)

The Streamlit admin-ui is partially implemented:

| Component | State |
|---|---|
| `bi/provider_base.py` | Complete — defines `BIProvider` Protocol |
| `bi/registry.py` | Complete — provider registry |
| `bi/main.py` | Stub — entry point defined |
| `bi/providers/` | EMPTY — no implementations yet |
| `Dockerfile.streamlit` | Exists — can build |
| `docker-compose.yml` admin-ui service | Configured |

The admin-ui currently surfaces basic functionality. Before adding features, check what `app/api/admin.py` already exposes via FastAPI — the Streamlit UI calls the FastAPI API, not the DB directly.

---

## Architecture: UI → API → DB

```
Streamlit UI
    ↓ HTTP requests
FastAPI /api/v1/admin/*
    ↓ AsyncSession
platform.* and metrics.* tables
```

Never connect Streamlit directly to PostgreSQL. All data flows through the FastAPI API.

---

## Adding a New Page

```python
# bi/pages/my_page.py
import streamlit as st
import httpx

API_BASE = "http://app:8000/api/v1"  # Docker service DNS — always hardcoded, not an env var


def render_my_page(token: str):
    st.title("My Page")

    # Fetch data from FastAPI
    resp = httpx.get(
        f"{API_BASE}/my-endpoint",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()

    st.dataframe(data)
```

Register in `bi/main.py`:
```python
import streamlit as st
from bi.pages.my_page import render_my_page

token = st.session_state.get("token")
if not token:
    # Show login form
    ...
else:
    render_my_page(token)
```

---

## Session State for Auth

```python
# Login flow
if "token" not in st.session_state:
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            resp = httpx.post(f"{API_BASE}/admin/login",
                json={"username": username, "password": password})
            if resp.status_code == 200:
                st.session_state["token"] = resp.json()["token"]
                st.rerun()
            else:
                st.error("Invalid credentials")
```

---

## Implementing a BIProvider

```python
# bi/providers/my_bi_provider.py
from bi.provider_base import BIProvider


class MyBIProvider(BIProvider):
    """Provider for MyBI system."""

    def connect(self, config: dict) -> None:
        self._client = MyBIClient(
            url=config["url"],
            token=config["token"],
        )

    def create_dashboard(self, name: str, config: dict) -> str:
        dashboard = self._client.dashboards.create(name=name, **config)
        return dashboard.id

    def sync_metrics(self, metrics: list[dict]) -> None:
        for metric in metrics:
            self._client.metrics.upsert(metric)
```

Register in `bi/registry.py`:
```python
from bi.providers.my_bi_provider import MyBIProvider

PROVIDERS = {
    "metabase": MetabaseProvider,  # when implemented
    "my_bi": MyBIProvider,
}
```

---

## Environment Variables for Streamlit

```env
# API_BASE is NOT configured via env var — it uses Docker service DNS (http://app:8000/api/v1)
# and is hardcoded in each page file. Only override if running outside Docker.
STREAMLIT_SERVER_PORT=8501
STREAMLIT_THEME_BASE=light
```

---

## Metabase vs Streamlit

| | Metabase | Streamlit Admin UI |
|---|---|---|
| Purpose | End-user BI dashboards | Admin configuration |
| Users | Managers, stakeholders | Platform admins only |
| Data access | `metrics.v_facts` directly | Via FastAPI |
| Customization | SQL-based | Python code |

Do not duplicate metric visualization in Streamlit — that's Metabase's job. Streamlit is for configuration (slice rules, commitment rules, unit bindings, etc.).

---

## Marketplace Skill Reference

For Streamlit component patterns, state management, caching:
```
/developing-with-streamlit  (streamlit/agent-skills@developing-with-streamlit)
```
