from datetime import datetime

import polars as pl

from pipelines.calculations import quality as logic


def test_calculate_defect_density_basic():
    sprints = pl.DataFrame(
        {"id": ["S1"], "project_id": ["P1"], "start_date": [datetime(2024, 1, 1)]}
    )
    sprint_issues = pl.DataFrame(
        {"issue_id": ["I1", "I2", "I3"], "sprint_id": ["S1", "S1", "S1"]}
    )
    issues = pl.DataFrame(
        {"id": ["I1", "I2", "I3"], "issue_type_id": ["T1", "T2", "T2"]}
    )
    issue_types = pl.DataFrame({"id": ["T1", "T2"], "name": ["Bug", "Story"]})

    result = logic.calculate_defect_density(
        sprints, sprint_issues, issues, issue_types, "Bug", "Story"
    )

    assert result[0, "density_ratio"] == 0.5  # 1 bug / 2 stories


def test_calculate_backflow_rate_basic():
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1", "I1"], "sprint_id": ["S1", "S1"]})
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["I1", "I1"],
            "from_status_id": ["TODO", "INPROG"],
            "to_status_id": ["INPROG", "TODO"],
            "changed_at": [datetime(2024, 1, 5), datetime(2024, 1, 6)],
        }
    )
    board_columns = pl.DataFrame(
        {
            "id": ["C1", "C2"],
            "board_id": ["B1", "B1"],
            "name": ["To Do", "In Progress"],
            "status_ids": [["TODO"], ["INPROG"]],
            "position": [0, 1],
        }
    )

    result = logic.calculate_backflow_rate(
        sprints, sprint_issues, status_changelog, board_columns
    )

    # 2 transitions total, 1 backward (INPROG -> TODO)
    assert result[0, "backflow_pct"] == 50.0


def test_calculate_backflow_rate_no_backward_transitions():
    """All forward transitions → backflow_pct = 0."""
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
            "end_date": [datetime(2024, 1, 14)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    # status_changelog: forward transition only (pos 1 → pos 2)
    cl = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "from_status_id": ["TODO"],
            "to_status_id": ["INPROG"],
            "changed_at": [datetime(2024, 1, 5)],
        }
    )
    # board_columns: TODO=pos1, INPROG=pos2
    bc = pl.DataFrame(
        {
            "id": ["BC1", "BC2"],
            "board_id": ["B1", "B1"],
            "name": ["To Do", "In Progress"],
            "position": [1, 2],
            "status_id": ["TODO", "INPROG"],
        }
    )
    result = logic.calculate_backflow_rate(sprints, sprint_issues, cl, bc)
    assert result[0, "backflow_pct"] == 0.0


def test_calculate_defect_density_zero_denominator():
    """Zero denominator type → ratio=0.0 without exception."""
    sprints = pl.DataFrame(
        {
            "id": ["S1"],
            "project_id": ["P1"],
            "name": ["Sprint 1"],
            "start_date": [datetime(2024, 1, 1)],
        }
    )
    sprint_issues = pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
    issues = pl.DataFrame(
        {"id": ["I1"], "project_id": ["P1"], "issue_type_id": ["BUG_TYPE"]}
    )
    issue_types = pl.DataFrame({"id": ["BUG_TYPE"], "name": ["Bug"]})
    result = logic.calculate_defect_density(
        sprints, sprint_issues, issues, issue_types, "Bug", "Story"
    )
    assert result[0, "density_ratio"] == 0.0  # no Stories → denominator=0 → 0.0
