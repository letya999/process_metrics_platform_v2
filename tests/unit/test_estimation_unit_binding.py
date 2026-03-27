from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from dagster import build_asset_context

from pipelines.assets.metrics.estimation import calculate_estimation_metrics


@pytest.fixture
def mock_database():
    db = MagicMock()
    db.get_engine.return_value = MagicMock()
    return db


def test_calculate_estimation_metrics_uses_unit_binding(mock_database):
    # Setup dataframes
    issues_df = pl.DataFrame(
        {
            "id": ["I1"],
            "project_id": ["P1"],
            "external_key": ["K-1"],
            "type_name": ["Story"],
        }
    )
    field_keys_df = pl.DataFrame(
        [
            {
                "id": "HEURISTIC_K",
                "external_key": "customfield_10036",
                "name": "Story Points",
            },
            {
                "id": "BINDING_K",
                "external_key": "customfield_999",
                "name": "My Custom SP",
            },
        ]
    )

    # Mock read_table to return different DFs based on query
    def side_effect(eng, query, params=None):
        if "clean_jira.issues" in query:
            return issues_df
        if "clean_jira.field_keys" in query:
            return field_keys_df
        return pl.DataFrame()

    context = build_asset_context()

    with (
        patch(
            "pipelines.assets.metrics.estimation.read_table", side_effect=side_effect
        ),
        patch(
            "pipelines.assets.metrics.estimation.get_definition_id", return_value="DEF1"
        ),
        patch(
            "pipelines.assets.metrics.estimation.get_calculation_id",
            return_value="CALC1",
        ),
        patch(
            "pipelines.assets.metrics.estimation.get_project_agg_id",
            return_value="AGG1",
        ),
        patch("pipelines.assets.metrics.estimation.resolve_unit_field") as mock_resolve,
        patch(
            "pipelines.assets.metrics.estimation.estimation_logic.calculate_estimate_volatility"
        ) as mock_calc,
        patch("pipelines.assets.metrics.estimation.write_fact_values", return_value=1),
    ):
        # Scenario 1: resolve_unit_field returns a binding
        mock_resolve.return_value = {"source_field_id": "BINDING_K"}
        mock_calc.return_value = pl.DataFrame(
            {"issue_id": ["I1"], "project_id": ["P1"], "volatility": [0.5]}
        )

        calculate_estimation_metrics(context, mock_database)

        # Verify that calc was called with BINDING_K, NOT HEURISTIC_K
        args, kwargs = mock_calc.call_args
        assert args[3] == "BINDING_K"

        # Scenario 2: resolve_unit_field returns None -> fallback to heuristic
        mock_resolve.return_value = None
        calculate_estimation_metrics(context, mock_database)

        args, kwargs = mock_calc.call_args
        assert args[3] == "HEURISTIC_K"
