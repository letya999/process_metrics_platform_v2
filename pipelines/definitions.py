"""Dagster pipelines for Process Metrics Platform."""

from dagster import Definitions, load_assets_from_modules

from pipelines.assets import jira, metrics
from pipelines.resources.database import database_resource

# Load all assets
jira_assets = load_assets_from_modules([jira])
metrics_assets = load_assets_from_modules([metrics])

defs = Definitions(
    assets=[*jira_assets, *metrics_assets],
    resources={
        "database": database_resource,
    },
)
