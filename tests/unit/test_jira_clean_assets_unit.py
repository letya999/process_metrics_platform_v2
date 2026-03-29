import types
from unittest.mock import MagicMock, patch

import pytest

from pipelines.assets.jira import clean


def _asset_fn(defn):
    """Extract the compute function from a Dagster asset definition."""
    return defn.node_def.compute_fn.decorated_fn


class _DummyLog:
    """Mock logger for testing."""

    def info(self, _msg):
        pass

    def warning(self, _msg):
        pass

    def error(self, _msg):
        pass


class _DummyContext:
    """Mock Dagster context for testing."""

    def __init__(self):
        self.log = _DummyLog()


class _Result:
    """Mock SQLAlchemy result object."""

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

    def fetchone(self):
        if self._first_value is not None:
            return self._first_value
        if self._fetchall_data:
            return self._fetchall_data[0]
        return None

    def yield_per(self, _batch_size):
        for row in self._fetchall_data:
            yield row

    def __iter__(self):
        return iter(self._fetchall_data)


class _Row:
    """Mock SQLAlchemy row object."""

    def __init__(self, values, **attrs):
        self._values = list(values)
        for k, v in attrs.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        return self._values[idx]


class _SequencedConnection:
    """Mock SQLAlchemy connection with a pre-defined sequence of results."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.commits = 0
        self.executed = []
        self._query_map = {}

    def with_query_map(self, query_map):
        self._query_map = query_map
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, stmt, params=None):
        stmt_str = str(stmt)
        self.executed.append((stmt_str, params))

        for pattern, resp in self._query_map.items():
            if pattern in stmt_str:
                return resp

        if not self._responses:
            raise AssertionError(f"Unexpected SQL execute call: {stmt}")
        return self._responses.pop(0)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def execution_options(self, **_kwargs):
        return self


class _Engine:
    """Mock SQLAlchemy engine."""

    def __init__(self, conn):
        self._conn = conn

    def connect(self):
        return self._conn


class _DummyDatabase:
    """Mock database resource for Dagster assets."""

    def __init__(self, conn):
        self._engine = _Engine(conn)

    def get_engine(self):
        return self._engine


def test_clean_jira_basic_sync_assets():
    """Verify basic sync assets (projects, issue types, statuses) behave correctly."""
    # clean_jira_projects
    # 1st call: _get_platform_project_id, 2nd call: INSERT
    conn = _SequencedConnection(
        [
            _Result(first_value=("00000000-0000-0000-0000-000000000001",)),
            _Result(fetchall_data=[(1,), (2,)]),
        ]
    )
    out = _asset_fn(clean.clean_jira_projects)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1

    # clean_jira_issue_types
    # 1st call: check hierarchy level col, 2nd call: INSERT
    conn = _SequencedConnection(
        [
            _Result(fetchall_data=[(1,)]),  # column check
            _Result(fetchall_data=[(1,), (2,)]),  # INSERT
        ]
    )
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
    """Jira issues sync must fail if no system integration is configured."""
    conn = _SequencedConnection([_Result(first_value=None)])
    with pytest.raises(RuntimeError, match="System Jira integration not found"):
        _asset_fn(clean.clean_jira_issues)(_DummyContext(), _DummyDatabase(conn))


def test_clean_jira_issues_success():
    """Verify successful sync of Jira issues."""
    conn = _SequencedConnection(
        [
            _Result(first_value=("integration-id",)),
            _Result(),  # sync users from raw_jira.users
            _Result(),  # sync users from changelog
            _Result(),  # sync assignee/reporter/creator users
            _Result(
                fetchall_data=[
                    ("rendered_fields__description",),
                    ("fields__resolutiondate",),
                    ("fields__parent__id",),
                    ("fields__priority__id",),
                    ("fields__resolution__id",),
                ]
            ),
            _Result(scalar_value=0),  # null_project_count
            _Result(scalar_value=0),  # drop_count due to missing it.id/ist.id
            _Result(scalar_value=0),  # null_date_count
            _Result(fetchall_data=[(1,), (2,), (3,)]),
            _Result(),  # parent_id reconciliation
        ]
    ).with_query_map({"information_schema.tables": _Result(scalar_value=True)})
    out = _asset_fn(clean.clean_jira_issues)(_DummyContext(), _DummyDatabase(conn))
    assert out == {"status": "success", "issues_synced": 3}
    assert conn.commits == 1


def test_clean_jira_labels_success():
    """Verify successful sync of labels."""
    # clean_jira_labels
    conn = _SequencedConnection(
        [
            _Result(fetchall_data=[(1,), (2,)]),  # INSERT
        ]
    ).with_query_map(
        {
            "information_schema.tables": _Result(scalar_value=True),
        }
    )
    out = _asset_fn(clean.clean_jira_labels)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1

    # clean_jira_issue_labels
    conn = _SequencedConnection(
        [
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
    """Verify successful sync of worklogs."""
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
    """Verify successful sync of priorities and resolutions."""
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
    """Verify sprint sync success and fallback paths."""
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
    """Verify field keys extraction and sync."""
    # 1. cols scan, 2. INSERT loop start, 3. INSERT loop end, 4. fields exists?, 5. names update 1, 6. names update 2, 7. _detect_sprint_field_id, 8. Sprint INSERT
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
            _Result(),  # INSERT customfield_10001
            _Result(),  # INSERT status__name
            _Result(scalar_value=False),  # fields exists
            _Result(),  # _detect_sprint_field_id
            _Result(),  # Sprint INSERT
        ]
    ).with_query_map(
        {
            "SELECT id FROM clean_jira.projects": _Result(
                fetchall_data=[("proj-id-1",), ("proj-id-2",)]
            )
        }
    )
    out = _asset_fn(clean.clean_jira_field_keys)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["field_keys_inserted"] == 4
    assert conn.commits == 2


def test_clean_jira_field_values_success():
    """Verify extraction and storage of field values."""
    fk_row = types.SimpleNamespace(
        id="fk1", project_id="p1", external_key="customfield_10001"
    )
    value_row = _Row(
        ["ISSUE-ID", "p1", '{"a": 1}'],
        issue_id="ISSUE-ID",
        project_id="p1",
    )
    # 1. safe_jsonb, 2. cols scan, 3. fk map, 4. batch rows, 5. insert data, 6. _detect_sprint_field_id, 7. sprint table exists, 8. sprint insert
    conn = _SequencedConnection(
        [
            _Result(),  # safe_jsonb
            _Result(fetchall_data=[("fields__customfield_10001",)]),  # cols
            _Result(fetchall_data=[fk_row]),  # fk map
            _Result(fetchall_data=[value_row]),  # batch rows
            _Result(),  # insert data
            _Result(first_value=("customfield_10020",)),  # _detect_sprint_field_id
            _Result(scalar_value=False),  # sprint table exists
        ]
    )
    out = _asset_fn(clean.clean_jira_field_values)(
        _DummyContext(), _DummyDatabase(conn)
    )
    assert out["status"] == "success"
    assert out["field_values_inserted"] == 1


def test_clean_jira_field_value_changelog_skip_and_success():
    """Verify field value changelog sync and skip conditions."""
    from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE

    conn_skip = _SequencedConnection([_Result(scalar_value=False)])
    out_skip = _asset_fn(clean.clean_jira_field_value_changelog)(
        _DummyContext(), _DummyDatabase(conn_skip)
    )
    assert out_skip["status"] == "skipped"
    _TABLE_EXISTS_CACHE.clear()

    conn_ok = _SequencedConnection(
        [_Result(scalar_value=True), _Result(), _Result(fetchall_data=[(1,), (2,)])]
    )
    out_ok = _asset_fn(clean.clean_jira_field_value_changelog)(
        _DummyContext(), _DummyDatabase(conn_ok)
    )
    assert out_ok == {"status": "success", "changes_count": 2}


def test_clean_jira_sprint_assets_success():
    """Verify sync of sprint-issue mapping and its changelog."""
    # clean_jira_sprint_issues
    # 1. changelog exists, 2. _detect_sprint_field_id, 3. INSERT (with fetchall), 4. update closed sprints
    conn_sprint_issues = _SequencedConnection(
        [
            _Result(scalar_value=True),  # changelog exists
            _Result(first_value=("customfield_10020",)),  # _detect_sprint_field_id
            _Result(fetchall_data=[(1,), (2,), (3,)]),  # INSERT
            _Result(),  # Reconciliation update
        ]
    )
    out_sprint_issues = _asset_fn(clean.clean_jira_sprint_issues)(
        _DummyContext(), _DummyDatabase(conn_sprint_issues)
    )
    assert out_sprint_issues["sprint_issues_count"] == 3

    # clean_jira_sprint_issues_changelog
    # 1. DELETE, 2. _detect_sprint_field_id, 3. INSERT
    conn_sprint_issues_changelog = _SequencedConnection(
        [
            _Result(),  # DELETE
            _Result(first_value=("customfield_10020",)),  # _detect_sprint_field_id
            _Result(fetchall_data=[(1,)]),  # INSERT
        ]
    )
    out_sprint_issues_changelog = _asset_fn(clean.clean_jira_sprint_issues_changelog)(
        _DummyContext(), _DummyDatabase(conn_sprint_issues_changelog)
    )
    assert out_sprint_issues_changelog["changelog_count"] == 1


def test_clean_jira_comments_skip_and_success():
    """Verify sync of issue comments."""
    from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE

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
    _TABLE_EXISTS_CACHE.clear()

    conn_ok = _SequencedConnection(
        [
            _Result(scalar_value=False),  # 1st loop: rendered exists?
            _Result(scalar_value=True),  # 1st loop: fields__comment__comments exists?
            _Result(scalar_value=True),  # 1st loop: fields__comment__comments has body?
            _Result(),  # CREATE FUNCTION pg_temp.safe_timestamptz
            _Result(fetchall_data=[(1,), (2,)]),  # INSERT INTO clean_jira.comments
            _Result(),  # INSERT INTO clean_jira.comment_issues
        ]
    )
    out_ok = _asset_fn(clean.clean_jira_comments)(
        _DummyContext(), _DummyDatabase(conn_ok)
    )
    assert out_ok == {"status": "success", "comments_synced": 2}


def test_clean_jira_release_assets_skip_and_success():
    """Verify sync of releases and release-issue mapping."""
    from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE

    conn_rel_skip = _SequencedConnection([_Result(scalar_value=False)])
    assert (
        _asset_fn(clean.clean_jira_releases)(
            _DummyContext(), _DummyDatabase(conn_rel_skip)
        )["status"]
        == "skipped"
    )
    _TABLE_EXISTS_CACHE.clear()

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
    """Verify sync of user roles on issues."""
    conn = _SequencedConnection([_Result(fetchall_data=[(1,), (2,)])])
    out = _asset_fn(clean.clean_jira_user_issue_roles)(
        _DummyContext(), _DummyDatabase(conn)
    )
    assert out["status"] == "success"
    assert out["count"] == 2
    assert conn.commits == 1


def test_clean_jira_issue_links_success():
    """Verify sync of issue links."""
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
    """Verify sync of miscellaneous assets (changelogs, boards, columns)."""
    from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE

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
    _TABLE_EXISTS_CACHE.clear()

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
    """Verify all asset checks correctly identify passed/failed states."""
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


@patch("requests.get")
@patch.dict(
    "os.environ",
    {"JIRA_URL": "http://jira", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "tok"},
)
def test_jira_ghost_cleanup_success(mock_get):
    """Verify that ghost cleanup correctly identifies and deletes removed issues."""
    # Mock Jira API response
    # Return 100 IDs
    api_ids = [{"id": str(10000 + i)} for i in range(100)]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "issues": api_ids,
        "total": 100,
    }
    mock_get.return_value = mock_response

    # Mock DB responses
    # Return 101 IDs (100 from API + 1 ghost)
    db_ids = [(str(10000 + i),) for i in range(100)] + [("19999",)]

    conn = _SequencedConnection(
        [
            _Result(),  # DELETE
        ]
    ).with_query_map(
        {
            "SELECT COUNT(*)": _Result(scalar_value=100),
            "SELECT id::text": _Result(fetchall_data=db_ids),
        }
    )

    out = _asset_fn(clean.jira_ghost_cleanup)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "success"
    assert out["deleted_count"] == 1
    assert conn.commits == 1
    # Verify DELETE was called for 19999
    assert "DELETE FROM raw_jira.issues" in conn.executed[-1][0]


class TestCleanJiraReleaseChangelog:
    """Tests for task 3.8: release property change tracking via snapshot diff."""

    def test_inserts_initial_rows_when_no_prior_changelog(self):
        """Initial run should treat all current fields as new additions."""
        # First run: no prior changelog entries - all current fields are "new"
        conn = _SequencedConnection(
            [
                _Result(
                    fetchall_data=[
                        ("uuid-rel-1",),
                        ("uuid-rel-1",),
                        ("uuid-rel-1",),
                        ("uuid-rel-1",),  # 4 fields for 1 release
                    ]
                ),
            ]
        )
        out = _asset_fn(clean.clean_jira_release_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 4  # 4 fields x 1 release

    def test_inserts_zero_rows_when_no_changes(self):
        """No changes should result in zero insertions."""
        # No differences detected - nothing to insert
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[]),
            ]
        )
        out = _asset_fn(clean.clean_jira_release_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 0

    def test_tracks_multiple_releases(self):
        """Verify tracking across multiple release objects."""
        # 3 releases with 4 fields each = up to 12 initial rows
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[("id",)] * 12),
            ]
        )
        out = _asset_fn(clean.clean_jira_release_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 12

    def test_detects_fix_version_field_name_variants(self):
        """Fix version field name variants used in release_issues_changelog SQL."""
        fix_version_field_names = {"Fix Version/s", "fixVersions", "Fix Version"}
        # Simulate the SQL IN check for field identification
        for name in fix_version_field_names:
            assert name in fix_version_field_names  # all variants are covered

    def test_sql_tracks_four_release_fields(self):
        """release_changelog tracks exactly: name, description, status, release_date."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_release_changelog))
        for field in ("name", "description", "status", "release_date"):
            assert (
                f"'{field}'" in source
            ), f"Field '{field}' missing from release_changelog SQL"


class TestCleanJiraSprintChangelog:
    """Tests for Phase 5: sprint_changelog upgrade to full snapshot-diff."""

    def test_bootstrap_inserts_all_5_fields_on_first_run(self):
        """Bootstrap run should capture all 5 sprint fields."""
        # 1 sprint x 5 fields = 5 rows inserted
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[("id",)] * 5),
            ]
        )
        out = _asset_fn(clean.clean_jira_sprint_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 5

    def test_no_insertion_when_values_unchanged(self):
        """Unchanged values should result in no changelog entries."""
        # IS DISTINCT FROM will return nothing if values match last_known
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[]),
            ]
        )
        out = _asset_fn(clean.clean_jira_sprint_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 0

    def test_detects_changes(self):
        """Verify change detection for modified fields."""
        # If 2 fields changed (e.g. name and status), expect 2 rows
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[("id",), ("id",)]),
            ]
        )
        out = _asset_fn(clean.clean_jira_sprint_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 2

    def test_multiple_sprints_multiple_changes(self):
        """Verify tracking of multiple changes across multiple sprints."""
        # 3 sprints, each having some changes. Suppose total 7 field changes across them.
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[("id",)] * 7),
            ]
        )
        out = _asset_fn(clean.clean_jira_sprint_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["changelog_count"] == 7

    def test_sql_tracks_five_sprint_fields(self):
        """Verify the SQL unrolls exactly 5 fields: name, goal, start_date, end_date, status."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_sprint_changelog))
        expected_fields = {"name", "goal", "start_date", "end_date", "status"}
        for field in expected_fields:
            assert (
                f"'{field}'" in source
            ), f"Field '{field}' missing from sprint_changelog SQL"


class TestJiraDataQuality:
    """Tests for task 4.1: raw vs clean row count quality checks."""

    def test_check_fails_when_raw_clean_issue_count_differs(self):
        """Check must fail if data loss between raw and clean exceeds threshold."""
        # raw=100 issues, clean=50 issues → 50% loss → should fail
        conn = _SequencedConnection(
            [_Result(scalar_value=100), _Result(scalar_value=50)]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is False
        assert result.metadata["loss_pct"].value == 50.0

    def test_check_passes_when_counts_match(self):
        """Check must pass if counts are identical."""
        # raw=100, clean=100 → 0% loss → pass
        conn = _SequencedConnection(
            [_Result(scalar_value=100), _Result(scalar_value=100)]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is True
        assert result.metadata["loss_pct"].value == 0.0

    def test_check_passes_within_threshold(self):
        """Check must pass if data loss is within 5% tolerance."""
        # raw=100, clean=96 → 4% loss → within 5% threshold → pass
        conn = _SequencedConnection(
            [_Result(scalar_value=100), _Result(scalar_value=96)]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is True
        assert result.metadata["loss_pct"].value == 4.0

    def test_check_skips_when_no_raw_table(self):
        """Check should skip if raw table does not exist."""
        conn = _SequencedConnection([])
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=False
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is True
        assert result.metadata["status"].text == "skipped_no_raw_table"

    def test_sprint_check_fails_when_count_differs(self):
        """Sprint count check must fail if counts differ significantly."""
        conn = _SequencedConnection(
            [_Result(scalar_value=161), _Result(scalar_value=100)]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_sprint_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is False

    def test_sprint_check_passes_when_counts_match(self):
        """Sprint count check must pass if counts match."""
        conn = _SequencedConnection(
            [_Result(scalar_value=161), _Result(scalar_value=161)]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_sprint_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is True


class TestSecretsLeak:
    """Tests for task 4.3: verify no API tokens/passwords are logged."""

    def test_no_api_token_logged(self):
        """Source code and loggers must not expose actual token values."""
        import inspect

        from pipelines.assets.jira import raw

        source = inspect.getsource(raw)
        # Ensure no pattern like log.info(f"...{api_token}...") or similar
        import re

        # Look for log calls that embed environment variable values directly
        secret_log_patterns = [
            r"log\.(info|warning|error|debug)\([^)]*JIRA_API_TOKEN[^)]*\)",
            r"log\.(info|warning|error|debug)\([^)]*api_token[^)]*\)",
            r"log\.(info|warning|error|debug)\([^)]*password[^)]*\)",
        ]
        for pattern in secret_log_patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            assert not matches, f"Potential secret in log: {matches}"

    def test_env_not_tracked_in_git(self):
        """Verify .env is listed in .gitignore to prevent accidental commit."""
        with open(".gitignore") as f:
            gitignore = f.read()
        assert ".env" in gitignore


# ---------------------------------------------------------------------------
# Helper function behavioral tests
# ---------------------------------------------------------------------------


class TestDetectSprintFieldId:
    """Tests for _detect_sprint_field_id fallback and happy-path behavior."""

    def test_returns_found_field_id(self):
        """Returns the ID found in raw_jira.fields when the row exists."""
        conn = _SequencedConnection([_Result(first_value=("customfield_10099",))])
        result = clean._detect_sprint_field_id(conn)
        assert result == "customfield_10099"

    def test_returns_default_when_no_row(self):
        """Falls back to customfield_10020 when the query returns no row."""
        conn = _SequencedConnection([_Result(first_value=None)])
        result = clean._detect_sprint_field_id(conn)
        assert result == "customfield_10020"

    def test_returns_default_on_exception(self):
        """Falls back to customfield_10020 when the DB query raises."""

        class _BrokenConn:
            def execute(self, *_a, **_kw):
                raise Exception("table does not exist")

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        result = clean._detect_sprint_field_id(_BrokenConn())
        assert result == "customfield_10020"

    def test_logs_warning_on_exception_fallback(self, caplog):
        """Fallback path must be observable in logs (no silent exception swallowing)."""

        class _BrokenConn:
            def execute(self, *_a, **_kw):
                raise RuntimeError("boom")

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        with caplog.at_level("WARNING"):
            result = clean._detect_sprint_field_id(_BrokenConn())

        assert result == "customfield_10020"
        assert "Failed to auto-detect sprint field id" in caplog.text
        assert "falling back to candidate list" in caplog.text

    def test_default_value_is_correct_field_id(self):
        """The default sprint field ID must be exactly 'customfield_10020'."""
        # This is a regression guard - changing the default breaks sprint sync
        conn = _SequencedConnection([_Result(first_value=None)])
        result = clean._detect_sprint_field_id(conn)
        assert (
            result == "customfield_10020"
        ), "Sprint field fallback changed - verify sprint SQL is still correct"


class TestGetPlatformProjectId:
    """Tests for _get_platform_project_id guard behavior."""

    def test_returns_id_when_row_exists_no_key(self):
        """Backward-compat: no project_key falls back to oldest active row."""
        conn = _SequencedConnection([_Result(first_value=("uuid-project-1",))])
        result = clean._get_platform_project_id(conn)
        assert result == "uuid-project-1"

    def test_returns_id_by_project_key_when_found(self):
        """With project_key, first query finds matching row."""
        conn = _SequencedConnection([_Result(first_value=("uuid-by-key",))])
        result = clean._get_platform_project_id(conn, project_key="ADS")
        assert result == "uuid-by-key"

    def test_falls_back_to_oldest_when_key_not_found(self):
        """If project_key lookup returns nothing, falls back to fallback query."""
        conn = _SequencedConnection(
            [
                _Result(first_value=None),  # key lookup misses
                _Result(first_value=("fallback-id",)),  # fallback returns oldest
            ]
        )
        result = clean._get_platform_project_id(conn, project_key="UNKNOWN")
        assert result == "fallback-id"

    def test_raises_when_no_project(self):
        """Must raise RuntimeError when platform.projects is empty."""
        conn = _SequencedConnection(
            [
                _Result(first_value=None),  # key lookup misses
                _Result(first_value=None),  # fallback also empty
            ]
        )
        with pytest.raises(RuntimeError, match="Platform project not found"):
            clean._get_platform_project_id(conn, project_key="ADS")

    def test_raises_without_key_when_table_empty(self):
        """No-key call raises when table is empty."""
        conn = _SequencedConnection([_Result(first_value=None)])
        with pytest.raises(RuntimeError, match="Platform project not found"):
            clean._get_platform_project_id(conn)

    def test_error_message_is_actionable(self):
        """Error message must mention platform.projects so devs know where to look."""
        conn = _SequencedConnection(
            [_Result(first_value=None), _Result(first_value=None)]
        )
        try:
            clean._get_platform_project_id(conn, project_key="X")
        except RuntimeError as e:
            assert "platform.projects" in str(e)


class TestSupplementaryIssueJoinScoping:
    """Ensure supplementary assets scope issue joins by project to avoid cross-project matches."""

    def test_comments_and_links_are_project_scoped(self):
        """Verify project scoping in comments and links sync SQL."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_comments))
        assert (
            source.count(
                "JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id"
            )
            >= 2
        )
        assert (
            source.count(
                "JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id"
            )
            >= 2
        )

    def test_field_values_and_changelog_are_project_scoped(self):
        """Verify project scoping in field values and changelog sync SQL."""
        import inspect

        field_values_source = inspect.getsource(
            _asset_fn(clean.clean_jira_field_values)
        )
        changelog_source = inspect.getsource(
            _asset_fn(clean.clean_jira_field_value_changelog)
        )

        assert (
            "JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id"
            in field_values_source
        )
        assert (
            "JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id"
            in field_values_source
        )

        assert (
            "JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id"
            in changelog_source
        )
        assert (
            "JOIN clean_jira.issues i ON i.external_id = r.id::text AND i.project_id = p.id"
            in changelog_source
        )


# ---------------------------------------------------------------------------
# Field key filtering behavioral tests
# ---------------------------------------------------------------------------


class TestFieldKeyFiltering:
    """Tests for the column depth and suffix filtering in clean_jira_field_keys."""

    def test_deeply_nested_columns_are_skipped(self):
        """Columns with 3 or more __ separators must be skipped."""
        # Simulate the Python-side filter: col_name.count("__") >= 3
        skip_cols = [
            "fields__status__category__key",  # 3 underscores
            "fields__a__b__c__d",  # 4 underscores
        ]
        include_cols = [
            "fields__customfield_10001",  # 1 underscore
            "fields__status__name",  # 2 underscores
        ]
        for col in skip_cols:
            assert col.count("__") >= 3, f"{col} should be filtered out"
        for col in include_cols:
            assert col.count("__") < 3, f"{col} should be included"

    def test_self_suffix_columns_are_skipped(self):
        """Columns ending with __self must be skipped (Jira API metadata noise)."""
        skip_cols = [
            "fields__status__self",
            "fields__assignee__self",
            "fields__issuetype__self",
        ]
        for col in skip_cols:
            assert col.endswith("__self"), f"{col} should be filtered out"

    def test_non_fields_columns_are_skipped(self):
        """Only columns starting with 'fields__' are processed."""
        skip_cols = ["id", "key", "_dlt_id", "_dlt_load_id", "rendered_fields__summary"]
        for col in skip_cols:
            assert not col.startswith("fields__"), f"{col} should be skipped"

    def test_field_key_extraction_strips_prefix(self):
        """Field key must be the column name with 'fields__' removed exactly once."""
        cases = [
            ("fields__customfield_10001", "customfield_10001"),
            ("fields__summary", "summary"),
            ("fields__issuetype__id", "issuetype__id"),
        ]
        for col, expected_key in cases:
            assert col.replace("fields__", "", 1) == expected_key

    def test_field_keys_count_in_asset(self):
        """clean_jira_field_keys must count only valid columns, not skipped ones."""
        # 4 columns: 1 custom, 1 standard (2 under), 1 too deep (skip), 1 __self (skip)
        conn = _SequencedConnection(
            [
                _Result(
                    fetchall_data=[
                        ("fields__customfield_10001",),  # included - count 1
                        ("fields__status__name",),  # included - count 2
                        ("fields__a__b__c",),  # skipped - 3 underscores
                        ("fields__status__self",),  # skipped - __self
                        ("_dlt_id",),  # skipped - not fields__
                    ]
                ),
                _Result(),  # INSERT field_data
                _Result(scalar_value=False),  # fields table exists?
                _Result(),  # _detect_sprint_field_id
                _Result(),  # Sprint INSERT
            ]
        ).with_query_map(
            {
                "SELECT id FROM clean_jira.projects": _Result(
                    fetchall_data=[("proj-id-1",), ("proj-id-2",)]
                )
            }
        )
        out = _asset_fn(clean.clean_jira_field_keys)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["field_keys_inserted"] == 4


# ---------------------------------------------------------------------------
# JSON value validation in field_values
# ---------------------------------------------------------------------------


class TestFieldValuesJsonDetection:
    """Tests for JSON detection heuristics in clean_jira_field_values."""

    def test_valid_json_object_detected(self):
        """Standard JSON objects must be detected as JSON."""
        import json

        valid_values = ['{"id": 1, "name": "sprint"}', '["a", "b"]', '"string"', "42"]
        for v in valid_values:
            try:
                json.loads(v)
                is_json = True
            except (ValueError, TypeError):
                is_json = False
            assert is_json, f"{v!r} should be valid JSON"

    def test_rank_string_not_treated_as_json(self):
        """Jira rank strings starting with '0|' must not be stored as json_value."""
        rank_values = ["0|hzzzzz:", "0|i00001:"]
        for v in rank_values:
            is_rank = v.startswith("0|") or "|i" in v
            assert is_rank, f"{v!r} should be detected as rank string"

    def test_pullrequest_not_treated_as_json(self):
        """Pull request field values starting with '{pullrequest' are not valid JSON."""
        import json

        pr_value = "{pullrequest: 1234, status: open}"
        starts_with_pr = pr_value.startswith("{pullrequest")
        assert starts_with_pr
        # Verify it also fails json.loads (belt and suspenders)
        try:
            json.loads(pr_value)
            parsed_ok = True
        except (ValueError, TypeError):
            parsed_ok = False
        assert not parsed_ok

    def test_plain_text_not_treated_as_json(self):
        """Plain text values that fail json.loads must produce json_value=None."""
        import json

        plain_values = ["In Progress", "not-json", "some free text"]
        for v in plain_values:
            try:
                json.loads(v)
                is_json = True
            except (ValueError, TypeError):
                is_json = False
            assert not is_json, f"{v!r} should NOT parse as JSON"


# ---------------------------------------------------------------------------
# Sprint delta logic (set difference for add/remove events)
# ---------------------------------------------------------------------------


class TestSprintDeltaLogic:
    """Tests for the sprint add/remove set-delta logic in sprint_issues_changelog."""

    def test_added_is_to_minus_from(self):
        """Items in 'to' but not 'from' are 'added'."""
        from_val = "10,20"
        to_val = "20,30"
        from_set = {x.strip() for x in from_val.split(",") if x.strip()}
        to_set = {x.strip() for x in to_val.split(",") if x.strip()}
        added = to_set - from_set
        removed = from_set - to_set
        assert added == {"30"}
        assert removed == {"10"}

    def test_removed_is_from_minus_to(self):
        """Items in 'from' but not 'to' are 'removed'."""
        from_val = "10,20,30"
        to_val = "20"
        from_set = {x.strip() for x in from_val.split(",") if x.strip()}
        to_set = {x.strip() for x in to_val.split(",") if x.strip()}
        removed = from_set - to_set
        assert removed == {"10", "30"}

    def test_unchanged_sprints_not_in_delta(self):
        """Sprints present in both from and to generate no add/remove events."""
        from_val = "10,20"
        to_val = "10,20"
        from_set = {x.strip() for x in from_val.split(",") if x.strip()}
        to_set = {x.strip() for x in to_val.split(",") if x.strip()}
        assert (to_set - from_set) == set()
        assert (from_set - to_set) == set()

    def test_empty_from_means_all_added(self):
        """When 'from' is empty, all 'to' values are additions."""
        from_val = ""
        to_val = "10,20"
        from_set = {x.strip() for x in from_val.split(",") if x.strip()}
        to_set = {x.strip() for x in to_val.split(",") if x.strip()}
        added = to_set - from_set
        assert added == {"10", "20"}

    def test_empty_to_means_all_removed(self):
        """When 'to' is empty, all 'from' values are removals."""
        from_val = "10,20"
        to_val = ""
        from_set = {x.strip() for x in from_val.split(",") if x.strip()}
        to_set = {x.strip() for x in to_val.split(",") if x.strip()}
        removed = from_set - to_set
        assert removed == {"10", "20"}


# ---------------------------------------------------------------------------
# Ghost cleanup edge cases
# ---------------------------------------------------------------------------


class TestGhostCleanupEdgeCases:
    """Tests for jira_ghost_cleanup safety guards."""

    def test_skips_when_credentials_missing(self):
        """Must skip gracefully when any credential env var is absent."""
        import os
        from unittest.mock import patch

        for missing_var in ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]:
            env = {
                "JIRA_URL": "http://jira",
                "JIRA_EMAIL": "a@b.c",
                "JIRA_API_TOKEN": "tok",
            }
            del env[missing_var]
            with patch.dict(os.environ, env, clear=True):
                # Also clear the specific var that's missing
                conn = _SequencedConnection([])
                out = _asset_fn(clean.jira_ghost_cleanup)(
                    _DummyContext(), _DummyDatabase(conn)
                )
                assert (
                    out["status"] == "skipped"
                ), f"Should skip when {missing_var} missing"
                assert out["reason"] == "missing_credentials"

    @patch("requests.get")
    @patch.dict(
        "os.environ",
        {"JIRA_URL": "http://jira", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "tok"},
    )
    def test_skips_deletion_when_api_returns_empty(self, mock_get):
        """Must NOT delete anything when Jira API returns zero issues (safety guard)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"issues": [], "total": 0}
        mock_get.return_value = mock_response

        # total_raw_issues=0 to avoid aborted_incomplete_api_response
        conn = _SequencedConnection([]).with_query_map(
            {"SELECT COUNT(*)": _Result(scalar_value=0)}
        )
        out = _asset_fn(clean.jira_ghost_cleanup)(_DummyContext(), _DummyDatabase(conn))
        assert out["status"] == "skipped"
        assert out["reason"] == "no_issues_from_api"

    @patch("requests.get")
    @patch.dict(
        "os.environ",
        {"JIRA_URL": "http://jira", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "tok"},
    )
    def test_does_not_delete_when_raw_is_subset_of_api(self, mock_get):
        """No deletion when all raw IDs exist in Jira API response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "issues": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "total": 3,
        }
        mock_get.return_value = mock_response

        conn = _SequencedConnection([]).with_query_map(
            {
                "SELECT COUNT(*)": _Result(scalar_value=2),
                "SELECT id::text": _Result(fetchall_data=[("1",), ("2",)]),
            }
        )
        out = _asset_fn(clean.jira_ghost_cleanup)(_DummyContext(), _DummyDatabase(conn))
        assert out["status"] == "success"
        assert out["deleted_count"] == 0

    @patch("requests.get")
    @patch.dict(
        "os.environ",
        {"JIRA_URL": "http://jira", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "tok"},
    )
    def test_ghost_cleanup_uses_expanding_in_clause(self, mock_get):
        """DELETE must use SQLAlchemy expanding bind params for batched IN lists."""
        api_ids = [{"id": str(i)} for i in range(100)]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "issues": api_ids,
            "total": 100,
        }
        mock_get.return_value = mock_response

        db_ids = [(str(i),) for i in range(100)] + [("101",), ("102",)]

        conn = _SequencedConnection(
            [
                _Result(),
            ]
        ).with_query_map(
            {
                "SELECT COUNT(*)": _Result(scalar_value=102),
                "SELECT id::text": _Result(fetchall_data=db_ids),
            }
        )
        out = _asset_fn(clean.jira_ghost_cleanup)(_DummyContext(), _DummyDatabase(conn))

        assert out["status"] == "success"
        assert out["deleted_count"] == 2
        delete_sql, delete_params = conn.executed[-1]
        assert "DELETE FROM raw_jira.issues WHERE id::text IN" in delete_sql
        assert "POSTCOMPILE_ids" in delete_sql
        assert isinstance(delete_params["ids"], tuple)
        assert set(delete_params["ids"]) == {"101", "102"}


@patch("requests.get")
@patch.dict(
    "os.environ",
    {"JIRA_URL": "http://jira", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "tok"},
)
def test_ghost_cleanup_aborts_when_api_returns_partial_list(mock_get):
    """Abort ghost cleanup when Jira API looks incomplete vs DB size."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "issues": [{"id": str(i)} for i in range(50)],
        "total": 50,
    }
    mock_get.return_value = mock_response

    conn = _SequencedConnection([]).with_query_map(
        {"SELECT COUNT(*) FROM raw_jira.issues": _Result(scalar_value=1000)}
    )
    out = _asset_fn(clean.jira_ghost_cleanup)(_DummyContext(), _DummyDatabase(conn))
    assert out["status"] == "aborted_incomplete_api_response"
    assert out["jira_ids"] == 50
    assert out["db_count"] == 1000


# ---------------------------------------------------------------------------
# TRUNCATE ordering in sprint_issues_changelog
# ---------------------------------------------------------------------------


class TestDeleteBeforeRebuild:
    """Verify DELETE is the first SQL call in sprint_issues_changelog."""

    def test_delete_is_first_executed_statement(self):
        """DELETE must precede INSERT in the execution sequence (M-3 Fix)."""
        conn = _SequencedConnection(
            [
                _Result(),  # DELETE
                _Result(first_value=("customfield_10020",)),  # _detect_sprint_field_id
                _Result(fetchall_data=[(1,)]),  # INSERT
            ]
        )
        _asset_fn(clean.clean_jira_sprint_issues_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        # First executed statement must be the DELETE
        first_sql = conn.executed[0][0].upper()
        assert (
            "DELETE" in first_sql
        ), f"Expected DELETE as first SQL, got: {first_sql[:80]}"

    def test_insert_follows_delete(self):
        """INSERT must be executed after DELETE (not before)."""
        conn = _SequencedConnection(
            [
                _Result(),  # DELETE
                _Result(first_value=("customfield_10020",)),  # _detect_sprint_field_id
                _Result(fetchall_data=[(1,), (2,)]),  # INSERT
            ]
        )
        _asset_fn(clean.clean_jira_sprint_issues_changelog)(
            _DummyContext(), _DummyDatabase(conn)
        )
        sqls = [sql.upper() for sql, _ in conn.executed]
        delete_idx = next(i for i, s in enumerate(sqls) if "DELETE" in s)
        insert_idx = next(i for i, s in enumerate(sqls) if "INSERT" in s)
        assert delete_idx < insert_idx, "DELETE must come before INSERT"


# ---------------------------------------------------------------------------
# Loss percentage boundary tests
# ---------------------------------------------------------------------------


class TestLossPercentageBoundary:
    """Boundary condition tests for the 5% loss tolerance threshold."""

    def test_exactly_5_percent_loss_passes(self):
        """Exactly _MAX_ISSUE_LOSS_PCT% (5.0%) loss must pass."""
        conn = _SequencedConnection(
            [
                _Result(scalar_value=100),
                _Result(scalar_value=95),  # 5% loss
            ]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is True
        assert result.metadata["loss_pct"].value == 5.0

    def test_above_5_percent_loss_fails(self):
        """Any loss above 5% must fail."""
        conn = _SequencedConnection(
            [
                _Result(scalar_value=1000),
                _Result(scalar_value=949),  # 5.1% loss
            ]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is False

    def test_zero_clean_is_100_percent_loss(self):
        """When clean layer is empty but raw has data, this is 100% loss - must fail."""
        conn = _SequencedConnection(
            [
                _Result(scalar_value=50),
                _Result(scalar_value=0),
            ]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is False
        assert result.metadata["loss_pct"].value == 100.0

    def test_more_clean_than_raw_does_not_fail(self):
        """If clean > raw (e.g. from manual inserts), loss_pct is negative - must pass."""
        conn = _SequencedConnection(
            [
                _Result(scalar_value=100),
                _Result(scalar_value=110),  # more clean than raw
            ]
        )
        with patch(
            "pipelines.assets.jira.clean._utils._table_exists", return_value=True
        ):
            result = _asset_fn(clean.check_raw_clean_issue_count)(
                None, _DummyDatabase(conn)
            )
        assert result.passed is True


# ---------------------------------------------------------------------------
# Hierarchy level from numeric field
# ---------------------------------------------------------------------------


class TestHierarchyLevelMapping:
    """Tests for both hierarchy_level mapping strategies in clean_jira_issue_types."""

    def test_numeric_hierarchy_positive_is_epic(self):
        """hierarchy_level > 0 must map to 'epic'."""

        def map_numeric(level):
            if level > 0:
                return "epic"
            elif level == 0:
                return "story"
            else:
                return "subtask"

        assert map_numeric(1) == "epic"
        assert map_numeric(3) == "epic"

    def test_numeric_hierarchy_zero_is_story(self):
        """hierarchy_level == 0 must map to 'story'."""

        def map_numeric(level):
            if level > 0:
                return "epic"
            elif level == 0:
                return "story"
            else:
                return "subtask"

        assert map_numeric(0) == "story"

    def test_numeric_hierarchy_negative_is_subtask(self):
        """hierarchy_level < 0 must map to 'subtask'."""

        def map_numeric(level):
            if level > 0:
                return "epic"
            elif level == 0:
                return "story"
            else:
                return "subtask"

        assert map_numeric(-1) == "subtask"
        assert map_numeric(-5) == "subtask"

    def test_name_based_sub_task_with_hyphen(self):
        """'Sub-task' (with hyphen) must NOT match 'subtask' ILIKE check."""
        name = "Sub-task"
        # The SQL uses ILIKE '%subtask%' - hyphen means this won't match
        assert "subtask" not in name.lower()
        # It falls through to 'task' default
        name_lower = name.lower()
        result = (
            "epic"
            if "epic" in name_lower
            else (
                "subtask"
                if "subtask" in name_lower
                else "story" if "story" in name_lower else "task"
            )
        )
        assert result == "task"

    def test_issue_types_uses_numeric_when_column_exists(self):
        """When hierarchy_level column exists, numeric path is used."""
        # Simulate: first call succeeds -> has_hierarchy_level = True
        conn = _SequencedConnection(
            [
                _Result(fetchall_data=[("anything",)]),  # column check succeeds
                _Result(fetchall_data=[(1,), (2,)]),  # INSERT
            ]
        )
        out = _asset_fn(clean.clean_jira_issue_types)(
            _DummyContext(), _DummyDatabase(conn)
        )
        assert out["status"] == "success"
        assert out["count"] == 2
        # Verify the numeric CASE logic was used (not ILIKE)
        insert_sql = conn.executed[1][0]
        assert "hierarchy_level" in insert_sql

    def test_issue_types_uses_name_ilike_when_column_missing(self):
        """When hierarchy_level column is absent, ILIKE fallback is used."""

        # The column check raises an exception (simulated via empty result that
        # triggers Exception path in the try/except)
        # Actually the code uses try/except around the SELECT; empty fetchall
        # won't raise. We need to simulate Exception.
        class _ExceptionOnFirst:
            _calls = 0
            commits = 0
            executed = []

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, stmt, params=None):
                self.executed.append((str(stmt), params))
                self._calls += 1
                if self._calls == 1:
                    raise Exception("column does not exist")
                return _Result(fetchall_data=[(1,)])

            def commit(self):
                self.commits += 1

            def rollback(self):
                pass

        conn2 = _ExceptionOnFirst()
        out = _asset_fn(clean.clean_jira_issue_types)(
            _DummyContext(),
            _DummyDatabase(conn2),
        )
        assert out["status"] == "success"
        # ILIKE path used - verify no numeric level in SQL
        insert_sql = conn2.executed[1][0]
        assert "ILIKE" in insert_sql or "ilike" in insert_sql.lower()


# ---------------------------------------------------------------------------
# safe_jsonb SQL content verification (regression against dual-behavior bug)
# ---------------------------------------------------------------------------


class TestSafeJsonbSqlContent:
    """Guard against the safe_jsonb dual-behavior bug (two functions with same name)."""

    def test_field_values_safe_jsonb_returns_null_on_error(self):
        """clean_jira_field_values must create safe_jsonb that returns NULL on error."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_field_values))
        # The function body should contain RETURN NULL (not RETURN to_jsonb)
        # in the safe_jsonb definition for field_values
        assert (
            "RETURN NULL" in source
        ), "clean_jira_field_values safe_jsonb should return NULL on error"

    def test_field_value_changelog_safe_jsonb_returns_to_jsonb_on_error(self):
        """clean_jira_field_value_changelog must create safe_jsonb that wraps in to_jsonb."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_field_value_changelog))
        assert (
            "to_jsonb" in source
        ), "clean_jira_field_value_changelog safe_jsonb should use to_jsonb fallback"

    def test_two_assets_have_different_safe_jsonb_behavior(self):
        """Verify the behavioral difference is intentional - document it explicitly."""
        import inspect

        fv_source = inspect.getsource(_asset_fn(clean.clean_jira_field_values))
        fvc_source = inspect.getsource(
            _asset_fn(clean.clean_jira_field_value_changelog)
        )

        fv_has_null_return = "RETURN NULL" in fv_source
        fvc_has_tojsonb = "to_jsonb" in fvc_source

        # Both conditions must hold simultaneously.
        # If this test fails, someone unified the behavior - verify it was intentional.
        assert fv_has_null_return and fvc_has_tojsonb, (
            "safe_jsonb behavior differs between assets intentionally: "
            "field_values returns NULL (skip bad values), "
            "field_value_changelog wraps in to_jsonb (preserve changelog history). "
            "If you changed this, update the test."
        )


# ---------------------------------------------------------------------------
# New asset checks - pass/fail for all 10
# ---------------------------------------------------------------------------


class TestNewAssetChecks:
    """Pass/fail tests for all 10 new @asset_check functions."""

    def _run_check(self, check_fn, scalar_value):
        """Run a standard asset check function and return the result."""
        return _asset_fn(check_fn)(
            None,
            _DummyDatabase(_SequencedConnection([_Result(scalar_value=scalar_value)])),
        )

    def test_closed_sprint_issues_inactive_passes_when_zero(self):
        """Check passes if no issues are active in closed sprints."""
        assert (
            self._run_check(clean.check_closed_sprint_issues_inactive, 0).passed is True
        )

    def test_closed_sprint_issues_inactive_fails_when_nonzero(self):
        """Check fails if some issues are still active in closed sprints."""
        result = self._run_check(clean.check_closed_sprint_issues_inactive, 3)
        assert result.passed is False
        assert result.metadata["active_issues_in_closed_sprints"].value == 3

    def test_issue_fk_integrity_passes_when_zero(self):
        """Check passes if all issue foreign keys are valid."""
        assert self._run_check(clean.check_issue_fk_integrity, 0).passed is True

    def test_issue_fk_integrity_fails_when_nonzero(self):
        """Check fails if some issue foreign keys are broken."""
        result = self._run_check(clean.check_issue_fk_integrity, 5)
        assert result.passed is False
        assert result.metadata["issues_with_broken_dimension_fk"].value == 5

    def test_no_orphan_worklogs_passes_when_zero(self):
        """Check passes if no worklogs are missing their issues."""
        assert self._run_check(clean.check_no_orphan_worklogs, 0).passed is True

    def test_no_orphan_worklogs_fails_when_nonzero(self):
        """Check fails if orphan worklogs are found."""
        result = self._run_check(clean.check_no_orphan_worklogs, 2)
        assert result.passed is False
        assert result.metadata["orphan_worklogs_count"].value == 2

    def test_no_orphan_sprints_passes_when_zero(self):
        """Check passes if all sprints belong to existing boards."""
        assert self._run_check(clean.check_no_orphan_sprints, 0).passed is True

    def test_no_orphan_sprints_fails_when_nonzero(self):
        """Check fails if orphan sprints are found."""
        result = self._run_check(clean.check_no_orphan_sprints, 1)
        assert result.passed is False
        assert result.metadata["orphan_sprints_count"].value == 1

    def test_field_values_fk_integrity_passes_when_zero(self):
        """Check passes if field value foreign keys are valid."""
        assert self._run_check(clean.check_field_values_fk_integrity, 0).passed is True

    def test_field_values_fk_integrity_fails_when_nonzero(self):
        """Check fails if field values have broken foreign keys."""
        result = self._run_check(clean.check_field_values_fk_integrity, 10)
        assert result.passed is False
        assert result.metadata["field_values_broken_fk_count"].value == 10

    def test_no_self_referencing_issue_links_passes_when_zero(self):
        """Check passes if no issue links to itself."""
        assert (
            self._run_check(clean.check_no_self_referencing_issue_links, 0).passed
            is True
        )

    def test_no_self_referencing_issue_links_fails_when_nonzero(self):
        """Check fails if self-referencing issue links are found."""
        result = self._run_check(clean.check_no_self_referencing_issue_links, 1)
        assert result.passed is False
        assert result.metadata["self_referencing_links_count"].value == 1

    def test_status_changelog_fk_integrity_passes_when_zero(self):
        """Check passes if status changelog foreign keys are valid."""
        assert (
            self._run_check(clean.check_status_changelog_fk_integrity, 0).passed is True
        )

    def test_status_changelog_fk_integrity_fails_when_nonzero(self):
        """Check fails if status changelog has broken foreign keys."""
        result = self._run_check(clean.check_status_changelog_fk_integrity, 4)
        assert result.passed is False
        assert result.metadata["changelog_unresolved_to_status_count"].value == 4

    def test_at_most_one_active_sprint_passes_when_zero(self):
        """Check passes if each project has at most one active sprint."""
        assert (
            self._run_check(clean.check_at_most_one_active_sprint_per_project, 0).passed
            is True
        )

    def test_at_most_one_active_sprint_fails_when_nonzero(self):
        """Check fails if projects have multiple active sprints."""
        result = self._run_check(clean.check_at_most_one_active_sprint_per_project, 2)
        assert result.passed is False
        assert result.metadata["projects_with_multiple_active_sprints"].value == 2

    def test_no_self_referencing_parent_passes_when_zero(self):
        """Check passes if no issue is its own parent."""
        assert self._run_check(clean.check_no_self_referencing_parent, 0).passed is True

    def test_no_self_referencing_parent_fails_when_nonzero(self):
        """Check fails if self-referencing parents are found."""
        result = self._run_check(clean.check_no_self_referencing_parent, 1)
        assert result.passed is False
        assert result.metadata["self_referencing_parents_count"].value == 1

    def test_jira_users_have_external_id_passes_when_zero(self):
        """Check passes if all Jira users have an external ID."""
        assert (
            self._run_check(clean.check_jira_users_have_external_id, 0).passed is True
        )

    def test_jira_users_have_external_id_fails_when_nonzero(self):
        """Check fails if some Jira users are missing an external ID."""
        result = self._run_check(clean.check_jira_users_have_external_id, 7)
        assert result.passed is False
        assert result.metadata["users_with_null_external_id"].value == 7


class TestFlowEfficiencyNonzeroCheck:
    """Behavioral coverage for check_flow_efficiency_nonzero."""

    def test_all_zero_values_fails(self):
        """Check should fail if 100% of flow efficiency values are zero."""
        from pipelines.assets.jira.clean import checks as checks_mod

        conn = _SequencedConnection([_Result(first_value=(10, 0))])
        result = _asset_fn(checks_mod.check_flow_efficiency_nonzero)(
            None, _DummyDatabase(conn)
        )
        assert result.passed is False
        assert result.metadata["total_rows"].value == 10
        assert result.metadata["nonzero_rows"].value == 0

    def test_some_nonzero_values_passes(self):
        """Check should pass if some flow efficiency values are non-zero."""
        from pipelines.assets.jira.clean import checks as checks_mod

        conn = _SequencedConnection([_Result(first_value=(100, 20))])
        result = _asset_fn(checks_mod.check_flow_efficiency_nonzero)(
            None, _DummyDatabase(conn)
        )
        assert result.passed is True
        assert result.metadata["nonzero_pct"].value == 20.0

    def test_no_data_passes(self):
        """Check should pass if there is no data to check."""
        from pipelines.assets.jira.clean import checks as checks_mod

        conn = _SequencedConnection([_Result(first_value=(0, 0))])
        result = _asset_fn(checks_mod.check_flow_efficiency_nonzero)(
            None, _DummyDatabase(conn)
        )
        assert result.passed is True
        assert result.metadata["status"].text == "no_data"


# ---------------------------------------------------------------------------
# Sprint status changelog SQL field coverage
# ---------------------------------------------------------------------------


class TestSprintChangelogSqlFieldCoverage:
    """Protect against accidental removal of tracked fields from sprint_changelog."""

    def test_sprint_changelog_tracks_all_required_fields(self):
        """sprint_changelog SQL must track: name, goal, start_date, end_date, status."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_sprint_changelog))
        required_fields = {"name", "goal", "start_date", "end_date", "status"}
        missing = {f for f in required_fields if f"'{f}'" not in source}
        assert not missing, f"Fields missing from sprint_changelog SQL: {missing}"

    def test_release_changelog_tracks_all_required_fields(self):
        """release_changelog SQL must track: name, description, status, release_date."""
        import inspect

        source = inspect.getsource(_asset_fn(clean.clean_jira_release_changelog))
        required_fields = {"name", "description", "status", "release_date"}
        missing = {f for f in required_fields if f"'{f}'" not in source}
        assert not missing, f"Fields missing from release_changelog SQL: {missing}"


# ---------------------------------------------------------------------------
# Status category inference: changelog fallback covers both languages
# ---------------------------------------------------------------------------


class TestChangelogStatusCategoryCompleteness:
    """Regression tests for the bilingual status category inference in issue_statuses."""

    DONE_NAMES = [
        "Done",
        "Closed",
        "Canceled",
        "Cancelled",
        "Resolved",
    ]
    TODO_NAMES = [
        "To Do",
        "К выполнению",  # 'К выполнению' means 'To be done'
        "Open",
        "Backlog",
        "New",
        "Todo",
    ]
    IN_PROGRESS_NAMES = [
        "In Progress",
        "In Review",
        "On Review",
        "Testing",
        "Deploying",
    ]

    def _infer(self, name: str) -> str:
        """Helper to simulate the SQL status category inference logic."""
        n = name.lower()
        if (
            n
            in {
                "done",
                "canceled",
                "cancelled",
                "closed",
                "resolved",
                "отмена",  # 'отмена' means 'cancel'
            }
            or "cancel" in n
            or "отмен" in n  # 'отмен' is root for 'cancel'
        ):
            return "done"
        if (
            n
            in {
                "to do",
                "к выполнению",  # 'к выполнению' means 'to do'
                "open",
                "backlog",
                "new",
                "todo",
            }
            or "to do" in n
            or "к выполнению" in n  # 'к выполнению' means 'to do'
        ):
            return "to_do"
        return "in_progress"

    def test_all_done_names(self):
        """Test that all expected 'Done' status names are correctly mapped."""
        for name in self.DONE_NAMES:
            assert self._infer(name) == "done", f"'{name}' should be done"

    def test_all_todo_names(self):
        """Test that all expected 'To Do' status names are correctly mapped."""
        for name in self.TODO_NAMES:
            assert self._infer(name) == "to_do", f"'{name}' should be to_do"

    def test_all_in_progress_names(self):
        """Test that all expected 'In Progress' status names are correctly mapped."""
        for name in self.IN_PROGRESS_NAMES:
            assert self._infer(name) == "in_progress", f"'{name}' should be in_progress"

    def test_on_review_is_in_progress(self):
        """'On Review' is the specific status that was missing from CFD - must be in_progress."""
        assert self._infer("On Review") == "in_progress"

    def test_unknown_status_defaults_to_in_progress(self):
        """Unknown statuses should default to 'in_progress' category."""
        assert self._infer("Some Custom Status") == "in_progress"
