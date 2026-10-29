#!/bin/bash
# Backup PostgreSQL ztd-db. Lokasi project = folder di atas scripts/ (tanpa hardcode user/path).
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
BACKUP_FILE="$BACKUP_DIR/ztd-db_$TIMESTAMP.sql"
TMP_FILE="$BACKUP_FILE.partial"

mkdir -p "$BACKUP_DIR"
trap 'rm -f "$TMP_FILE"' EXIT

POSTGRES_USER="$(grep '^POSTGRES_USER=' "$PROJECT_DIR/.env" | cut -d '=' -f2-)"
POSTGRES_DB="$(grep '^POSTGRES_DB=' "$PROJECT_DIR/.env" | cut -d '=' -f2-)"
[ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_DB" ] || { echo "POSTGRES_USER/POSTGRES_DB kosong di .env" >&2; exit 1; }

echo "=== ZTD PostgreSQL Backup ==="
echo "Database : $POSTGRES_DB"

docker exec ztd-db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$TMP_FILE"

# dump yang kosong atau tanpa penutup pg_dump = gagal, jangan disimpan
[ -s "$TMP_FILE" ] || { echo "Backup gagal: hasil dump kosong." >&2; exit 1; }
tail -n 5 "$TMP_FILE" | grep -q "PostgreSQL database dump complete" || { echo "Backup gagal: dump terpotong (tanpa penutup pg_dump)." >&2; exit 1; }

mv "$TMP_FILE" "$BACKUP_FILE"
trap - EXIT
chmod 600 "$BACKUP_FILE"

echo "Backup dibuat : $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
find "$BACKUP_DIR" -type f -name "ztd-db_*.sql" -mtime +"$RETENTION_DAYS" -delete
echo "Retensi $RETENTION_DAYS hari diterapkan. Selesai."
