# Orchestrator

Small utility that registers and deploys Prefect flows for `dlt_jira_loader` via the Prefect REST API.

Usage:

1. Build image:

```bash
docker build -t orchestrator:test .
```

2. Run (with `PREFECT_API_URL` set):

```bash
docker run --rm -e PREFECT_API_URL=http://prefect-server:4200/api orchestrator:test
```
