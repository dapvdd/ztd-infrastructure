#!/usr/bin/env bash
# install-backup.sh — jalankan dari ~/ztd-infrastructure
#
# Memperbaiki backup DB harian yang di repo hardcode /home/david:
#  1. scripts/backup-db.sh  : ditulis ulang, lokasi project dihitung dari posisi script (bukan hardcode),
#                             dump ditulis ke file sementara lalu dipindah (dump gagal/kosong = gak ada file sampah).
#  2. systemd service+timer : dipasang di /etc/systemd/system untuk user yang menjalankan script ini.
#  3. Menjalankan satu backup sekarang dan memverifikasi hasilnya.
# Aman diulang. Backup file lama: *.bak-<timestamp>.
set -euo pipefail

TS="$(date +%Y%m%d-%H%M%S)"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SKIP_SYSTEMCTL="${SKIP_SYSTEMCTL:-0}"
SUDO="${SUDO-sudo}"
die() { echo "ERROR: $*" >&2; exit 1; }

[ -f docker-compose.yml ] && [ -f .env ] || die "jalankan dari ~/ztd-infrastructure (harus ada docker-compose.yml dan .env)"
grep -q '^POSTGRES_USER=' .env && grep -q '^POSTGRES_DB=' .env || die ".env belum punya POSTGRES_USER / POSTGRES_DB"

PROJECT_DIR="$(pwd)"
RUN_USER="$(id -un)"
mkdir -p scripts backups

# ---- 1. backup-db.sh ----
[ -f scripts/backup-db.sh ] && cp -p scripts/backup-db.sh "scripts/backup-db.sh.bak-$TS"
cat > scripts/backup-db.sh <<'BACKUP'
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
BACKUP
chmod +x scripts/backup-db.sh

# ---- 2. unit systemd ----
UNIT_SERVICE="$(cat <<UNIT
[Unit]
Description=ZTD PostgreSQL Backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/backup-db.sh
UNIT
)"
UNIT_TIMER="$(cat <<'UNIT'
[Unit]
Description=Run ZTD PostgreSQL Backup Daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
UNIT
)"

for f in ztd-backup.service ztd-backup.timer; do
  [ -f "$SYSTEMD_DIR/$f" ] && $SUDO cp -p "$SYSTEMD_DIR/$f" "$SYSTEMD_DIR/$f.bak-$TS" || true
done
printf '%s\n' "$UNIT_SERVICE" | $SUDO tee "$SYSTEMD_DIR/ztd-backup.service" >/dev/null
printf '%s\n' "$UNIT_TIMER"   | $SUDO tee "$SYSTEMD_DIR/ztd-backup.timer"   >/dev/null

# supaya file backup tidak ikut ke git
touch .gitignore
grep -qxF "backups/" .gitignore || echo "backups/" >> .gitignore

if [ "$SKIP_SYSTEMCTL" = "1" ]; then echo "[SKIP_SYSTEMCTL] unit ditulis ke $SYSTEMD_DIR, systemd tidak disentuh."; exit 0; fi

$SUDO systemctl daemon-reload
$SUDO systemctl enable --now ztd-backup.timer

# ---- 3. jalankan satu backup sekarang & verifikasi ----
echo ">> Menjalankan satu backup lewat systemd..."
if ! $SUDO systemctl start ztd-backup.service; then
  echo "GAGAL. Log:"; journalctl -u ztd-backup.service -n 20 --no-pager || true
  echo "Penyebab umum: user '$RUN_USER' belum masuk grup docker (cek: groups)."; exit 1
fi

LATEST="$(ls -t backups/ztd-db_*.sql 2>/dev/null | head -1 || true)"
[ -n "$LATEST" ] && [ -s "$LATEST" ] || die "service sukses tapi file backup tidak ada/kosong"
echo
echo "PASS  backup berhasil: $LATEST ($(du -h "$LATEST" | cut -f1))"
echo "PASS  jumlah tabel di dump: $(grep -c '^CREATE TABLE' "$LATEST")"
echo; echo "Timer aktif:"; systemctl list-timers ztd-backup.timer --no-pager | head -3