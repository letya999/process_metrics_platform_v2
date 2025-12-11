"""Client for triggering Dagster jobs via GraphQL API."""

import os
from typing import Any

import httpx


class DagsterClient:
    """Client for interacting with Dagster GraphQL API."""

    def __init__(self, graphql_url: str | None = None):
        """Initialize the Dagster client.

        Args:
            graphql_url: URL of the Dagster GraphQL endpoint.
                        Defaults to DAGSTER_GRAPHQL_URL env var.
        """
        self.graphql_url = graphql_url or os.getenv(
            "DAGSTER_GRAPHQL_URL", "http://localhost:3000/graphql"
        )

    async def trigger_job(
        self, job_name: str, run_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Trigger a Dagster job.

        Args:
            job_name: Name of the job to trigger.
            run_config: Optional run configuration.

        Returns:
            Response from Dagster API with run information.
        """
        mutation = """
        mutation LaunchRun($executionParams: ExecutionParams!) {
            launchRun(executionParams: $executionParams) {
                __typename
                ... on LaunchRunSuccess {
                    run {
                        runId
                        status
                    }
                }
                ... on PythonError {
                    message
                    stack
                }
                ... on InvalidStepError {
                    invalidStepKey
                }
                ... on InvalidOutputError {
                    stepKey
                    invalidOutputName
                }
            }
        }
        """

        variables = {
            "executionParams": {
                "selector": {
                    "jobName": job_name,
                },
                "runConfigData": run_config or {},
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.graphql_url,
                json={"query": mutation, "variables": variables},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_run_status(self, run_id: str) -> dict[str, Any]:
        """Get the status of a Dagster run.

        Args:
            run_id: ID of the run to check.

        Returns:
            Response from Dagster API with run status.
        """
        query = """
        query RunStatus($runId: ID!) {
            runOrError(runId: $runId) {
                __typename
                ... on Run {
                    runId
                    status
                    startTime
                    endTime
                }
                ... on RunNotFoundError {
                    message
                }
                ... on PythonError {
                    message
                }
            }
        }
        """

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.graphql_url,
                json={"query": query, "variables": {"runId": run_id}},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def list_jobs(self) -> dict[str, Any]:
        """List all available Dagster jobs.

        Returns:
            Response from Dagster API with job information.
        """
        query = """
        query Jobs {
            repositoriesOrError {
                __typename
                ... on RepositoryConnection {
                    nodes {
                        name
                        jobs {
                            name
                            description
                        }
                    }
                }
                ... on PythonError {
                    message
                }
            }
        }
        """

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.graphql_url,
                json={"query": query},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
