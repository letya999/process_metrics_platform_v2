import types

import pytest

from pipelines.assets.jira import clean


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


class _DummyLog:
    def info(self, _msg):
        pass

    def warning(self, _msg):
        pass

    def error(self, _msg):
        pass


class _DummyContext:
    def __init__(self):
        self.log = _DummyLog()


class _Result:
    def __init__(self, fetchall_data=None, scalar_value=None, first_value=None):
        self._fetchall_data = fetchall_data if fetchall_data is not None else []
        self._scalar_value = scalar_value
        self._first_value = first_value

    def fetchall(self):
        return self._fetchall_data

    def scalar(self):
        return self._scalar_value

    def first(self):
        return self._first_value


class _Row:
    def __init__(self, values, **attrs):
        self._values = list(values)
        for k, v in attrs.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        return self._values[idx]


class _SequencedConnection:
    def __init__(self, responses):
        self._responses = list(responses)
        self.commits = 0
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        if not self._responses:
            raise AssertionError(f"Unexpected SQL execute call: {stmt}")
        return self._responses.pop(0)

    def commit(self):
        self.commits += 1


class _Engine:
    def __init__(self, conn):
        self._conn = conn

    def connect(self):
        return self._conn


class _DummyDatabase:
    def __init__(self, conn):
        self._engine = _Engine(conn)

    def get_engine(self):
        return self._engine


def test_clean_jira_basic_sync_assets():
    # clean_jira_projects
    conn = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    out = _asset_fn(clean.clean_jira_projects)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1

    # clean_jira_issue_types
    conn = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    out = _asset_fn(clean.clean_jira_issue_types)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1

    # clean_jira_issue_statuses
    conn = _SequencedConnection(
        [_Result(scalar_value=False), _Result(fetchall_data=[(1,), (2,)])]
    )
    out = _asset_fn(clean.clean_jira_issue_statuses)(
        _DummyContext(), _DummyDatabase(conn)
    )
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1


def test_clean_jira_issues_raises_without_system_integration():
    conn = _SequencedConnection([_Result(first_value=None)])
    with pytest.raises(RuntimeError, match="System Jira integration not found"):
        _asset_fn(clean.clean_jira_issues)(_DummyContext(), _DummyDatabase(conn))


def test_clean_jira_issues_success():
    conn = _SequencedConnection(
        [
            _Result(first_value=("integration-id",)),
            _Result(),
            _Result(scalar_value=False),
            _Result(),
            _Result(
                fetchall_data=[
                    ("rendered_fields__description",),
                    ("fields__resolutiondate",),
                    ("fields__parent__id",),
                    ("fields__priority__id",),
                    ("fields__resolution__id",),
                ]
            ),
            _Result(fetchall_data=[(1,), (2,), (3,)]),
            _Result(),  # parent_id reconciliation
        ]
    )
    out = _asset_fn(clean.clean_jira_issues)(_DummyContext(), _DummyDatabase(conn))
    assert out == {"status": "success", "issues_synced": 3}
    assert conn.commits == 1


def test_clean_jira_labels_success():
    # clean_jira_labels
    conn = _SequencedConnection(
        [
            _Result(scalar_value=True),  # table exists
            _Result(fetchall_data=[(1,), (2,)]),  # INSERT
        ]
    )
    out = _asset_fn(clean.clean_jira_labels)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1

    # clean_jira_issue_labels
    conn = _SequencedConnection(
        [
            _Result(scalar_value=True),  # table exists
            _Result(fetchall_data=[(1,), (2,), (3,)]),  # INSERT
        ]
    )
    out = _asset_fn(clean.clean_jira_issue_labels)(
        _DummyContext(), _DummyDatabase(conn)
    )
    assert out["status"] == "success"
    assert out["count"] == 3
    assert conn.commits == 1


def test_clean_jira_worklogs_success():
    conn = _SequencedConnection(
        [
            _Result(scalar_value=True),  # table exists
            _Result(fetchall_data=[(1,), (2,)]),  # INSERT
        ]
    )
    out = _asset_fn(clean.clean_jira_worklogs)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1


def test_clean_jira_priorities_resolutions_success():
    # priorities
    conn_p = _SequencedConnection([_Result(fetchall_data=[(1,)])])
    out_p = _asset_fn(clean.clean_jira_priorities)(
        _DummyContext(), _DummyDatabase(conn_p)
    )
    assert out_p["count"] == 1

    # resolutions
    conn_r = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    out_r = _asset_fn(clean.clean_jira_resolutions)(
        _DummyContext(), _DummyDatabase(conn_r)
    )
    assert out_r["count"] == 2


def test_clean_jira_sprints_success_and_fallback():
    conn_success = _SequencedConnection(
        [_Result(scalar_value=True), _Result(fetchall_data=[(1,), (2,)])]
    )
    out_success = _asset_fn(clean.clean_jira_sprints)(
        _DummyContext(), _DummyDatabase(conn_success)
    )
    assert out_success == {"status": "success", "sprints_synced": 2}

    conn_fallback = _SequencedConnection(
        [
            _Result(scalar_value=False),
            _Result(fetchall_data=[("id",), ("project_key",)]),
        ]
    )
    out_fallback = _asset_fn(clean.clean_jira_sprints)(
        _DummyContext(), _DummyDatabase(conn_fallback)
    )
    assert out_fallback == {"status": "success", "sprints_synced": 0}


def test_clean_jira_field_keys_success():
    conn = _SequencedConnection(
        [
            _Result(
                fetchall_data=[
                    ("fields__customfield_10001",),
                    ("fields__status__name",),
                    ("fields__too__deep__x",),
                    ("fields__assignee__self",),
                ]
            ),
            _Result(),
            _Result(),
            _Result(scalar_value=False),
            _Result(),
        ]
    )
    out = _asset_fn(clean.clean_jira_field_keys)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["field_keys_inserted"] == 2
    assert conn.commits == 2


def test_clean_jira_field_values_success():
    fk_row = types.SimpleNamespace(
        id="fk1", project_id="p1", external_key="customfield_10001"
    )
    value_row = _Row(
        ["ISSUE-ID", "p1", '{"a": 1}'],
        issue_id="ISSUE-ID",
        project_id="p1",
    )
    conn = _SequencedConnection(
        [
            _Result(),
            _Result(fetchall_data=[("fields__customfield_10001",)]),
            _Result(fetchall_data=[fk_row]),
            _Result(fetchall_data=[value_row]),
            _Result(),
            _Result(scalar_value=False),
        ]
    )
    out = _asset_fn(clean.clean_jira_field_values)(
        _DummyContext(), _DummyDatabase(conn)
    )
    assert out["status"] == "success"
    assert out["field_values_inserted"] == 1


def test_clean_jira_field_value_changelog_skip_and_success():
    conn_skip = _SequencedConnection([_Result(scalar_value=False)])
    out_skip = _asset_fn(clean.clean_jira_field_value_changelog)(
        _DummyContext(), _DummyDatabase(conn_skip)
    )
    assert out_skip["status"] == "skipped"

    conn_ok = _SequencedConnection(
        [_Result(scalar_value=True), _Result(), _Result(fetchall_data=[(1,), (2,)])]
    )
    out_ok = _asset_fn(clean.clean_jira_field_value_changelog)(
        _DummyContext(), _DummyDatabase(conn_ok)
    )
    assert out_ok == {"status": "success", "changes_count": 2}


def test_clean_jira_sprint_assets_success():
    conn_sprint_issues = _SequencedConnection(
        [
            _Result(scalar_value=True),
            _Result(fetchall_data=[(1,), (2,), (3,)]),
            _Result(),  # Reconciliation update
        ]
    )
    out_sprint_issues = _asset_fn(clean.clean_jira_sprint_issues)(
        _DummyContext(), _DummyDatabase(conn_sprint_issues)
    )
    assert out_sprint_issues["sprint_issues_count"] == 3

    conn_sprint_issues_changelog = _SequencedConnection(
        [_Result(), _Result(fetchall_data=[(1,)])]
    )
    out_sprint_issues_changelog = _asset_fn(clean.clean_jira_sprint_issues_changelog)(
        _DummyContext(), _DummyDatabase(conn_sprint_issues_changelog)
    )
    assert out_sprint_issues_changelog["changelog_count"] == 1


def test_clean_jira_comments_skip_and_success():
    # possible_tables = [rendered_fields..., fields__comment__comments, fields__comment]
    conn_skip = _SequencedConnection(
        [
            _Result(scalar_value=False),  # 1st loop: rendered exists?
            _Result(scalar_value=False),  # 1st loop: fields__comment__comments exists?
            _Result(scalar_value=False),  # 1st loop: fields__comment exists?
            _Result(scalar_value=False),  # 2nd loop: rendered exists?
            _Result(scalar_value=False),  # 2nd loop: fields__comment__comments exists?
            _Result(scalar_value=False),  # 2nd loop: fields__comment exists?
        ]
    )
    out_skip = _asset_fn(clean.clean_jira_comments)(
        _DummyContext(), _DummyDatabase(conn_skip)
    )
    assert out_skip["status"] == "skipped"

    conn_ok = _SequencedConnection(
        [
            _Result(scalar_value=False),  # 1st loop: rendered exists?
            _Result(scalar_value=True),  # 1st loop: fields__comment__comments exists?
            _Result(scalar_value=True),  # 1st loop: fields__comment__comments has body?
            _Result(fetchall_data=[(1,), (2,)]),  # INSERT INTO clean_jira.comments
            _Result(),  # INSERT INTO clean_jira.comment_issues
        ]
    )
    out_ok = _asset_fn(clean.clean_jira_comments)(
        _DummyContext(), _DummyDatabase(conn_ok)
    )
    assert out_ok == {"status": "success", "comments_synced": 2}


def test_clean_jira_release_assets_skip_and_success():
    conn_rel_skip = _SequencedConnection([_Result(scalar_value=False)])
    assert (
        _asset_fn(clean.clean_jira_releases)(
            _DummyContext(), _DummyDatabase(conn_rel_skip)
        )["status"]
        == "skipped"
    )

    conn_rel_ok = _SequencedConnection(
        [_Result(scalar_value=True), _Result(fetchall_data=[(1,), (2,), (3,)])]
    )
    assert (
        _asset_fn(clean.clean_jira_releases)(
            _DummyContext(), _DummyDatabase(conn_rel_ok)
        )["releases_count"]
        == 3
    )

    conn_ri_skip = _SequencedConnection([_Result(scalar_value=0)])
    assert (
        _asset_fn(clean.clean_jira_release_issues)(
            _DummyContext(), _DummyDatabase(conn_ri_skip)
        )["status"]
        == "skipped"
    )

    conn_ri_ok = _SequencedConnection(
        [_Result(scalar_value=1), _Result(fetchall_data=[(1,)])]
    )
    assert (
        _asset_fn(clean.clean_jira_release_issues)(
            _DummyContext(), _DummyDatabase(conn_ri_ok)
        )["release_issues_count"]
        == 1
    )

    conn_ri_ch_skip = _SequencedConnection([_Result(scalar_value=0)])
    assert (
        _asset_fn(clean.clean_jira_release_issues_changelog)(
            _DummyContext(), _DummyDatabase(conn_ri_ch_skip)
        )["status"]
        == "skipped"
    )

    conn_ri_ch_ok = _SequencedConnection(
        [_Result(scalar_value=1), _Result(fetchall_data=[(1,), (2,)])]
    )
    assert (
        _asset_fn(clean.clean_jira_release_issues_changelog)(
            _DummyContext(), _DummyDatabase(conn_ri_ch_ok)
        )["changelog_count"]
        == 2
    )


def test_clean_jira_user_issue_roles_success():
    conn = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    out = _asset_fn(clean.clean_jira_user_issue_roles)(
        _DummyContext(), _DummyDatabase(conn)
    )
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1


def test_clean_jira_issue_links_success():
    conn = _SequencedConnection(
        [
            _Result(scalar_value=True),  # table exists
            _Result(),  # insert relation_issue_types
            _Result(fetchall_data=[(1,), (2,)]),  # insert relation_issue_issues
        ]
    )
    out = _asset_fn(clean.clean_jira_issue_links)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1


def test_clean_jira_misc_assets_success():
    conn_sc = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    assert (
        _asset_fn(clean.clean_jira_sprint_changelog)(
            _DummyContext(), _DummyDatabase(conn_sc)
        )["changelog_count"]
        == 2
    )

    conn_is_skip = _SequencedConnection([_Result(scalar_value=False)])
    assert (
        _asset_fn(clean.clean_jira_issue_status_changelog)(
            _DummyContext(), _DummyDatabase(conn_is_skip)
        )["status"]
        == "skipped"
    )

    conn_is_ok = _SequencedConnection(
        [_Result(scalar_value=True), _Result(fetchall_data=[(1,)])]
    )
    assert (
        _asset_fn(clean.clean_jira_issue_status_changelog)(
            _DummyContext(), _DummyDatabase(conn_is_ok)
        )["changelog_entries"]
        == 1
    )

    conn_boards_skip = _SequencedConnection([_Result(scalar_value=False)])
    assert (
        _asset_fn(clean.clean_jira_boards)(
            _DummyContext(), _DummyDatabase(conn_boards_skip)
        )["status"]
        == "skipped"
    )

    conn_boards_ok = _SequencedConnection(
        [_Result(scalar_value=True), _Result(fetchall_data=[(1,), (2,)])]
    )
    assert (
        _asset_fn(clean.clean_jira_boards)(
            _DummyContext(), _DummyDatabase(conn_boards_ok)
        )["count"]
        == 2
    )

    conn_cols = _SequencedConnection([_Result(fetchall_data=[(1,)])])
    assert (
        _asset_fn(clean.clean_jira_board_columns)(
            _DummyContext(), _DummyDatabase(conn_cols)
        )["count"]
        == 1
    )

    conn_col_status = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    assert (
        _asset_fn(clean.clean_jira_board_column_statuses)(
            _DummyContext(), _DummyDatabase(conn_col_status)
        )["count"]
        == 2
    )


def test_clean_jira_asset_checks():
    check_fns = [
        clean.check_no_orphan_issues,
        clean.check_issues_have_required_fields,
        clean.check_sprint_dates_valid,
        clean.check_sprint_issues_integrity,
        clean.check_release_issues_integrity,
    ]
    for fn in check_fns:
        failed = _asset_fn(fn)(
            None, _DummyDatabase(_SequencedConnection([_Result(scalar_value=1)]))
        )
        assert failed.passed is False
        passed = _asset_fn(fn)(
            None, _DummyDatabase(_SequencedConnection([_Result(scalar_value=0)]))
        )
        assert passed.passed is True
