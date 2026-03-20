import polars as pl

from pipelines.assets.metrics import velocity


def test_done_statuses_from_velocity_commitment_rules(monkeypatch):
    boards_df = pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
    board_columns_df = pl.DataFrame(
        {
            "id": ["c1", "c2"],
            "board_id": ["b1", "b1"],
            "name": ["In Progress", "Done"],
            "status_id": ["s-in-progress", "s-done"],
            "position": [1, 2],
        }
    )

    def _load_rules(_engine, calc_code):
        if calc_code == "velocity_completed_sp":
            return [
                {
                    "commitment_rule_id": "r1",
                    "project_id": "p1",
                    "board_id": "b1",
                    "start_column_id": "c1",
                    "end_column_id": "c2",
                    "start_column_name": "In Progress",
                    "end_column_name": "Done",
                }
            ]
        return []

    monkeypatch.setattr(velocity, "load_commitment_rules_for_calc", _load_rules)
    monkeypatch.setattr(
        velocity,
        "resolve_commitment_columns",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolve_commitment_columns should not be called")
        ),
    )

    done_ids = velocity._resolve_done_status_ids_from_commitment_rules(
        object(), boards_df, board_columns_df
    )

    assert done_ids == ["s-done"]


def test_done_statuses_fallback_to_lead_time_rules_when_velocity_rules_missing(
    monkeypatch,
):
    boards_df = pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
    board_columns_df = pl.DataFrame(
        {
            "id": ["c1", "c2"],
            "board_id": ["b1", "b1"],
            "name": ["In Progress", "Done"],
            "status_id": ["s-in-progress", "s-done"],
            "position": [1, 2],
        }
    )

    def _load_rules(_engine, calc_code):
        if calc_code == "lead_time_days":
            return [
                {
                    "commitment_rule_id": "r2",
                    "project_id": "p1",
                    "board_id": "b1",
                    "start_column_id": "c1",
                    "end_column_id": "c2",
                    "start_column_name": "In Progress",
                    "end_column_name": "Done",
                }
            ]
        return []

    monkeypatch.setattr(velocity, "load_commitment_rules_for_calc", _load_rules)
    monkeypatch.setattr(
        velocity,
        "resolve_commitment_columns",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolve_commitment_columns should not be called")
        ),
    )

    done_ids = velocity._resolve_done_status_ids_from_commitment_rules(
        object(), boards_df, board_columns_df
    )

    assert done_ids == ["s-done"]
