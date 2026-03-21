from dagster import Definitions

from pipelines.definitions import defs


def test_dagster_definitions_load():
    """Verify that Dagster definitions load correctly."""
    assert isinstance(defs, Definitions)

    # Check that some key assets are present
    asset_names = [a.key.to_user_string() for a in defs.assets]
    assert "metrics_lead_time" in asset_names or any(
        "lead_time" in n for n in asset_names
    )

    # Check resources
    assert "database" in defs.resources
