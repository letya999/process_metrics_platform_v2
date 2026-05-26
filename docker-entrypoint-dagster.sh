#!/bin/bash
set -e

# Keep runtime dagster.yaml in sync with image version.
if [ ! -f "${DAGSTER_HOME}/dagster.yaml" ] || ! cmp -s /opt/dagster/app/dagster.yaml "${DAGSTER_HOME}/dagster.yaml"; then
    echo "Syncing dagster.yaml to ${DAGSTER_HOME}"
    cp /opt/dagster/app/dagster.yaml "${DAGSTER_HOME}/dagster.yaml"
fi

# Execute the command
exec "$@"
