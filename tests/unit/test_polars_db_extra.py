from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from pipelines.utils.polars_db import execute_sql, read_table, write_fact_values


def test_read_table_fallback_to_pandas():
    mock_engine = MagicMock()
    mock_engine.url = "postgresql://user:pass@host/db"

    # Mock pl.read_database_uri to fail
    with patch("polars.read_database_uri", side_effect=Exception("Driver Error")):
        with patch("pandas.read_sql") as mock_read_sql:
            import pandas as pd

            mock_read_sql.return_value = pd.DataFrame(
                {"col1": [1, 2], "col2": ["a", "b"]}
            )

            res = read_table(mock_engine, "SELECT * FROM table")
            assert res.height == 2
            assert "col1" in res.columns


def test_write_fact_values_empty_input():
    mock_engine = MagicMock()
    # Should return 0 immediately
    res = write_fact_values(pl.DataFrame(), mock_engine, [], [], 0, 0)
    assert res == 0


def test_write_fact_values_missing_columns():
    mock_engine = MagicMock()
    df = pl.DataFrame({"wrong_col": [1]})
    with pytest.raises(
        ValueError, match="DataFrame is missing required fact_values columns"
    ):
        write_fact_values(df, mock_engine, ["m1"], ["p1"], 1, 2)


def test_write_fact_values_drops_auto_cols():
    mock_engine = MagicMock()
    # DataFrame with all None in auto cols
    df = pl.DataFrame(
        {
            "metric_id": ["m1"],
            "project_agg_id": ["p1"],
            "time_id": [1],
            "value": [10.0],
            "id": [None],
            "created_at": [None],
        }
    )

    # Mock context manager for engine.begin()
    _ = mock_engine.begin.return_value.__enter__.return_value

    with patch("pandas.DataFrame.to_sql") as mock_to_sql:
        write_fact_values(df, mock_engine, ["m1"], ["p1"], 1, 1)
        # Verify to_sql was called (it means it reached the point after dropping columns)
        assert mock_to_sql.called


def test_execute_sql():
    mock_engine = MagicMock()
    execute_sql(mock_engine, "DROP TABLE test")
    mock_engine.connect.assert_called_once()
