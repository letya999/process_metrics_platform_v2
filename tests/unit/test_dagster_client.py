"""Unit tests for Dagster GraphQL client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dagster_client import DagsterClient


def test_dagster_client_uses_default_url_from_env(monkeypatch):
    monkeypatch.delenv("DAGSTER_GRAPHQL_URL", raising=False)
    client = DagsterClient()
    assert client.graphql_url == "http://localhost:3000/graphql"


def test_dagster_client_respects_custom_url():
    client = DagsterClient("http://dagster:3000/graphql")
    assert client.graphql_url == "http://dagster:3000/graphql"


@pytest.mark.asyncio
async def test_trigger_job_posts_expected_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"launchRun": {"__typename": "ok"}}}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("app.services.dagster_client.httpx.AsyncClient") as async_client_cls:
        async_client_cls.return_value.__aenter__.return_value = mock_client
        client = DagsterClient("http://dagster/graphql")
        result = await client.trigger_job("jira_sync_job", {"k": "v"})

    assert result["data"]["launchRun"]["__typename"] == "ok"
    assert mock_client.post.call_count == 1
    args = mock_client.post.call_args
    assert args.args[0] == "http://dagster/graphql"
    assert args.kwargs["timeout"] == 30.0
    assert args.kwargs["json"]["variables"]["executionParams"]["selector"][
        "jobName"
    ] == ("jira_sync_job")
    assert args.kwargs["json"]["variables"]["executionParams"]["runConfigData"] == {
        "k": "v"
    }


@pytest.mark.asyncio
async def test_get_run_status_posts_expected_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"runOrError": {"__typename": "Run"}}}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("app.services.dagster_client.httpx.AsyncClient") as async_client_cls:
        async_client_cls.return_value.__aenter__.return_value = mock_client
        client = DagsterClient("http://dagster/graphql")
        result = await client.get_run_status("run-123")

    assert result["data"]["runOrError"]["__typename"] == "Run"
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["variables"] == {"runId": "run-123"}


@pytest.mark.asyncio
async def test_list_jobs_posts_query_without_variables():
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"repositoriesOrError": {"nodes": []}}}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("app.services.dagster_client.httpx.AsyncClient") as async_client_cls:
        async_client_cls.return_value.__aenter__.return_value = mock_client
        client = DagsterClient("http://dagster/graphql")
        result = await client.list_jobs()

    assert result["data"]["repositoriesOrError"]["nodes"] == []
    assert "variables" not in mock_client.post.call_args.kwargs["json"]


@pytest.mark.asyncio
async def test_trigger_job_propagates_http_errors():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = RuntimeError("http failed")

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("app.services.dagster_client.httpx.AsyncClient") as async_client_cls:
        async_client_cls.return_value.__aenter__.return_value = mock_client
        client = DagsterClient("http://dagster/graphql")
        with pytest.raises(RuntimeError, match="http failed"):
            await client.trigger_job("jira_sync_job")


@pytest.mark.asyncio
async def test_get_run_details_posts_expected_payload():
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"runOrError": {"__typename": "Run"}}}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("app.services.dagster_client.httpx.AsyncClient") as async_client_cls:
        async_client_cls.return_value.__aenter__.return_value = mock_client
        client = DagsterClient("http://dagster/graphql")
        result = await client.get_run_details("run-1", event_limit=25)

    assert result["data"]["runOrError"]["__typename"] == "Run"
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["variables"] == {"runId": "run-1", "limit": 25}
