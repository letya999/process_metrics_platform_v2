from services.dlt_jira_loader.app.dlt_sources.resources.boards import (
    make_boards_resource,
)


def test_boards_resource_with_values_dict():
    class C:
        def find_boards(self, project_key=None):
            return {"values": [{"id": 10, "name": "X"}]}

    res = make_boards_resource(C())
    items = list(res())
    assert items[0]["board_id"] == 10


def test_boards_resource_with_list():
    class C:
        def find_boards(self, project_key=None):
            return [{"id": 20, "name": "Y"}]

    res = make_boards_resource(C())
    items = list(res())
    assert items[0]["board_id"] == 20


def test_boards_resource_with_bad_iterable():
    class Bad:
        def find_boards(self, project_key=None):
            return 12345

    res = make_boards_resource(Bad())
    items = list(res())
    assert items == []
