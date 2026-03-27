#!/bin/bash
# Backup PostgreSQL database to a file.
# Usage: ./backup_postgres.sh [backup_file_path]

set -e

# Load environment variables if .env exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

DB_NAME=${POSTGRES_DATABASE:-process_metrics_platform}
DB_USER=${POSTGRES_USER:-postgres}
DB_HOST=${POSTGRES_HOST:-localhost}
DB_PORT=${POSTGRES_PORT:-5432}

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEFAULT_BACKUP_FILE="backup_${DB_NAME}_${TIMESTAMP}.sql"
BACKUP_FILE=${1:-$DEFAULT_BACKUP_FILE}

echo "Starting backup of database ${DB_NAME} to ${BACKUP_FILE}..."

# Ensure PGPASSWORD is set from env to avoid interactive prompt
if [ -z "$POSTGRES_PASSWORD" ]; then
  echo "Error: POSTGRES_PASSWORD is not set."
  exit 1
fi

export PGPASSWORD=$POSTGRES_PASSWORD

pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -F p > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
  echo "Backup successfully created: ${BACKUP_FILE}"
else
  echo "Error occurred during backup."
  exit 1
fi
