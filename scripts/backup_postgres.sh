#!/bin/bash
# =============================================================================
# PostgreSQL Backup Script
# =============================================================================

set -euo pipefail

# Конфигурация
BACKUP_DIR="/opt/backups/postgres"
CONTAINER_NAME="postgres"
# Используем переменные окружения, если они установлены, иначе дефолтные
DB_NAME="${POSTGRES_DB:-process_metrics}"
DB_USER="${POSTGRES_USER:-postgres}"
RETENTION_DAYS=14

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"

# Создаём директорию если не существует
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL backup..."

# Создаём backup
# Используем docker exec для выполнения pg_dump внутри контейнера
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

# Проверяем размер
if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup created: $BACKUP_FILE ($BACKUP_SIZE)"
else
    echo "[$(date)] Error: Backup file not created!"
    exit 1
fi

# Удаляем старые backup (старше RETENTION_DAYS)
echo "[$(date)] Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Cleanup completed"

# Показываем список текущих резервных копий
echo "[$(date)] Current backups:"
ls -lh "$BACKUP_DIR"

echo "[$(date)] Backup process finished successfully!"
