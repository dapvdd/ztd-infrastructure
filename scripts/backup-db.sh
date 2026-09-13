#!/bin/bash

set -e

PROJECT_DIR="/home/david/ztd-server"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/ztd-db_$TIMESTAMP.sql"

mkdir -p "$BACKUP_DIR"

POSTGRES_USER=$(grep '^POSTGRES_USER=' "$PROJECT_DIR/.env" | cut -d '=' -f2-)
POSTGRES_DB=$(grep '^POSTGRES_DB=' "$PROJECT_DIR/.env" | cut -d '=' -f2-)

echo "=== ZTD PostgreSQL Backup ==="
echo "Database : $POSTGRES_DB"
echo "Starting backup..."

docker exec ztd-db pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  > "$BACKUP_FILE"

echo "Backup created:"
echo "$BACKUP_FILE"

echo "Backup size:"
du -h "$BACKUP_FILE"

echo "Backup completed successfully."

echo "Cleaning up backups older than 7 days..."
find "$BACKUP_DIR" -type f -name "ztd-db_*.sql" -mtime +7 -delete

echo "Backup retention cleanup completed."
