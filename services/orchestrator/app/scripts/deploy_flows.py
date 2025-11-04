"""Deploy dlt_jira_loader flows via Prefect REST API."""
import os
import sys
from typing import Optional

import requests

API_URL = os.getenv("PREFECT_API_URL", "http://prefect-server:4200/api")
HEADERS = {"x-prefect-api-version": "0.8.4", "Content-Type": "application/json"}
# Store the entire service root so the `app` package is included in Prefect storage
CODE_ROOT = "/opt/prefect/services/dlt_jira_loader"


def register_flow(flow_name: str, entrypoint: str) -> str:
    """Register flow and return flow_id."""
    print(f"-> Registering flow: {flow_name}")
    r = requests.post(
        f"{API_URL}/flows/",
        json={"name": flow_name, "tags": ["jira", "etl"]},
        headers=HEADERS,
    )
    if r.status_code not in (200, 201):
        print(f"❌ Flow registration failed: {r.status_code}\n{r.text}")
        sys.exit(1)
    flow_id = r.json()["id"]
    print(f"✅ Flow registered: {flow_id}")
    return flow_id


def create_deployment(
    flow_id: str,
    deployment_name: str,
    entrypoint: str,
    schedule: Optional[dict] = None,
) -> str:
    """Create deployment with optional schedule."""
    print(f"-> Creating deployment: {deployment_name}")
    payload = {
        "name": deployment_name,
        "flow_id": flow_id,
        "work_pool_name": "default",
        # Point storage to the service root so imports like `import app.infra` resolve
        "path": CODE_ROOT,
        "entrypoint": entrypoint,
        "parameters": {},
        "tags": ["docker", "api"],
    }

    r = requests.post(f"{API_URL}/deployments/", json=payload, headers=HEADERS)
    if r.status_code not in (200, 201):
        print(f"❌ Deployment failed: {r.status_code}\n{r.text}")
        sys.exit(1)

    deployment_id = r.json()["id"]
    print(f"✅ Deployment created: {deployment_id}")

    # Add schedule if provided
    if schedule:
        r = requests.post(
            f"{API_URL}/deployments/{deployment_id}/schedules",
            json=[schedule],
            headers=HEADERS,
        )
        if r.status_code not in (200, 201):
            print(f"⚠️ Schedule failed: {r.status_code}")
        else:
            print("✅ Schedule added")

    return deployment_id


def trigger_run(deployment_id: str) -> str:
    """Trigger manual flow run."""
    print("-> Triggering manual run...")
    r = requests.post(
        f"{API_URL}/deployments/{deployment_id}/create_flow_run",
        json={},
        headers=HEADERS,
    )
    if r.status_code not in (200, 201):
        print(f"❌ Run trigger failed: {r.status_code}\n{r.text}")
        sys.exit(1)
    run_id = r.json()["id"]
    print(f"✅ Flow run started: {run_id}")
    return run_id


def main() -> None:
    """Deploy all dlt_jira_loader flows."""
    print(f"Using PREFECT API: {API_URL}")

    # 1. Main sync flow (manual)
    flow_id = register_flow("jira_sync_flow", "app/flows/jira_sync.py:jira_sync_flow")
    create_deployment(
        flow_id=flow_id,
        deployment_name="jira-sync-manual",
        entrypoint="app/flows/jira_sync.py:jira_sync_flow",
    )

    # 2. Scheduled wrapper (cron 02:00 UTC)
    flow_id = register_flow(
        "jira_sync_scheduled", "app/flows/scheduled.py:jira_sync_scheduled_wrapper"
    )
    deployment_id = create_deployment(
        flow_id=flow_id,
        deployment_name="jira-sync-scheduled",
        entrypoint="app/flows/scheduled.py:jira_sync_scheduled_wrapper",
        schedule={
            "active": True,
            "schedule": {"cron": "0 2 * * *", "timezone": "UTC"},
            "max_scheduled_runs": 50,
        },
    )

    # 3. Trigger test run
    trigger_run(deployment_id)

    print("\n🎉 All deployments registered!")


if __name__ == "__main__":
    main()
