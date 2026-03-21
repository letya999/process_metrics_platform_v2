from datetime import datetime, timezone

import polars as pl

from pipelines.calculations import aging as logic


def test_calculate_blocked_time_basic():
    issues = pl.DataFrame({"id": ["I1"], "project_id": ["P1"], "key": ["K1"]})
    field_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "field_key_id": ["BLOCKED", "BLOCKED"],
            "old_value": [None, "true"],
            "new_value": ["true", "false"],
            "change_time": [
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            ],
        }
    )

    result = logic.calculate_blocked_time(issues, field_changelog, "BLOCKED")

    assert result[0, "blocked_hours"] == 2.0


def test_calculate_stale_days_basic():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "project_id": ["P1"],
            "key": ["K1"],
            "status_id": ["INPROG"],
            "updated_at": [datetime(2024, 1, 5, tzinfo=timezone.utc)],
        }
    )

    result = logic.calculate_stale_days(issues, pl.DataFrame(), ["DONE"], now)

    assert result[0, "stale_days"] == 5.0
