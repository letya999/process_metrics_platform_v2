#!/bin/bash
set -e

# Ensure dagster.yaml exists in DAGSTER_HOME
if [ ! -f "${DAGSTER_HOME}/dagster.yaml" ]; then
    echo "Copying dagster.yaml to ${DAGSTER_HOME}"
    cp /opt/dagster/app/dagster.yaml "${DAGSTER_HOME}/dagster.yaml"
fi

# Execute the command
exec "$@"
