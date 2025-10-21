import responses

from services.dlt_jira_loader.dlt_sources import jira_cloud


@responses.activate
def test_sprints_resource_iteration(mock_client):
    # sprints endpoint uses agile API path; simulate a simple response
    board_id = 42
    responses.add(
        responses.GET,
        f"https://example.atlassian.net/rest/agile/1.0/board/{board_id}/sprint",
        json={
            "startAt": 0,
            "maxResults": 50,
            "values": [{"id": 1, "name": "S1", "state": "active"}],
        },
        status=200,
    )

    client = mock_client
    sprints_res = jira_cloud.make_sprints_resource(client=client)
    sprints = list(sprints_res(board_id=board_id))
    assert len(sprints) == 1
    assert sprints[0]["sprint_id"] == 1


@responses.activate
def test_releases_and_boards_resources_iteration(mock_client):
    project_key = "PROJ"
    # stub versions endpoint
    responses.add(
        responses.GET,
        f"https://example.atlassian.net/rest/api/3/project/{project_key}/versions",
        json=__import__(
            "services.dlt_jira_loader.tests.unit.conftest", fromlist=[""]
        ).versions_payload(project_key, count=2),
        status=200,
    )
    # stub boards endpoint
    responses.add(
        responses.GET,
        "https://example.atlassian.net/rest/agile/1.0/board",
        json=__import__(
            "services.dlt_jira_loader.tests.unit.conftest", fromlist=[""]
        ).boards_payload(project_key),
        status=200,
    )

    client = mock_client
    releases_res = jira_cloud.make_releases_resource(client=client)
    boards_res = jira_cloud.make_boards_resource(client=client, project_key=project_key)

    releases = list(releases_res(project_key))
    assert len(releases) == 2
    assert releases[0]["release_id"] is not None

    boards = list(boards_res())
    assert len(boards) == 1
    assert boards[0]["board_id"] == 11
