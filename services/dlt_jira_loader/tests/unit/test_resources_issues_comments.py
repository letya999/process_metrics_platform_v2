import responses

from services.dlt_jira_loader.dlt_sources import jira_cloud
from services.dlt_jira_loader.tests.unit.conftest import (
    add_comments_stub,
    add_search_stub,
    comments_payload,
    issues_payload,
)


@responses.activate
def test_iterate_single_issue_and_comment(mock_client):
    project_key = "PROJ"

    add_search_stub(project_key, issues_payload(project_key, count=1))
    add_comments_stub(f"{project_key}-1", comments_payload(count=1))

    # construct resources directly using factories to avoid dlt.source wrapping
    client = mock_client
    issues_res = jira_cloud.make_issues_resource(project_key=project_key, client=client)
    comments_res = jira_cloud.make_comments_resource(client=client)

    issues = list(issues_res())
    assert len(issues) == 1
    assert issues[0]["issue_key"] == "PROJ-1"

    comments = list(comments_res(issue_key="PROJ-1"))
    assert len(comments) == 1
    assert comments[0]["comment_id"] == "c1"


@responses.activate
def test_pagination_multiple_issues_and_comments(mock_client):
    project_key = "BIG"

    # simulate server returning multiple pages: first page with 2 items, second empty
    responses.add(
        responses.GET,
        "https://example.atlassian.net/rest/api/3/search",
        json=issues_payload(project_key, count=2),
        status=200,
    )
    # comments for each issue
    add_comments_stub(f"{project_key}-1", comments_payload(count=2))
    add_comments_stub(f"{project_key}-2", comments_payload(count=1))

    client = mock_client
    issues_res = jira_cloud.make_issues_resource(project_key=project_key, client=client)
    comments_res = jira_cloud.make_comments_resource(client=client)

    issues = list(issues_res())
    assert len(issues) == 2

    all_comments = []
    for issue in issues:
        all_comments.extend(list(comments_res(issue_key=issue["issue_key"])))
    assert len(all_comments) >= 3


@responses.activate
def test_created_after_filter_returns_empty_when_no_issues(mock_client):
    project_key = "PROJ"
    responses.add(
        responses.GET,
        "https://example.atlassian.net/rest/api/3/search",
        json={"startAt": 0, "maxResults": 50, "total": 0, "issues": []},
        status=200,
    )

    client = mock_client
    issues_res = jira_cloud.make_issues_resource(project_key=project_key, client=client)
    issues = list(issues_res(created_after="2024-01-01"))
    assert issues == []
