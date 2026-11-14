# Runbook Rollback Produksi ZTD

> Sumber bukti: rehearsal P7 di staging (proyek `ztd-staging`, VPS 100.105.163.126,
> 2026-11-14) — tiga drill: rollback image backend, restore database, rollback
> konfigurasi compose/nginx. Semua terverifikasi; see
> `.superpowers/sdd/2026-11-12-ztd-release-blockers/progress.md` § P7.

## 0. Prinsip

- **Tidak ada down migration pada data produksi.** Rollback aplikasi =
  kembalikan image/config; data tetap di tempat (skema v2 bersifat aditif dan
  kompatibel dengan backend v1).
- **RTO target: < 10 menit** per skenario. Setiap langkah diverifikasi dengan
  health check sebelum dinyatakan selesai.
- Jalankan semua perintah dari direktori proyek (`/home/firza/ztd-infrastructure`
  untuk produksi; staging memakai `/home/firza/ztd-staging` dengan project `-p ztd-staging`).

## 1. Rollback image backend (release buruk)

```bash
# Sebelum deploy selalu: tandai image baik yang sedang berjalan
docker tag ztd-backend:latest ztd-backend:rollback-good

# --- saat release buruk terdeteksi (health 502/unhealthy) ---
# 1) kembalikan tag latest ke image baik
docker tag ztd-backend:rollback-good ztd-backend:latest
# 2) buat ulang container
docker compose up -d --force-recreate ztd-backend
# 3) REINSTALL wheel itsdangerous — recreate menghapus paket pip bawaan image lama
docker cp wheels/itsdangerous-2.2.0-py3-none-any.whl ztd-backend-container:/tmp/itsdangerous-2.2.0-py3-none-any.whl
docker exec <backend-container> pip install /tmp/itsdangerous-2.2.0-py3-none-any.whl
docker restart <backend-container>
# 4) verifikasi
curl -s http://127.0.0.1:8000/health          # {"status":"healthy",...}
curl -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/api/dashboard/session \
  -H 'Content-Type: application/json' -d '{}'  # 422 (bukan 500)
```

Bukti staging (P7-A2): image postgres:16 dipasang sebagai `ztd-backend:latest`
→ health `000` (koneksi ditolak); rollback ke tag `rollback-good` → health
`healthy`, login 422, wheel 2.2.0 terpasang. Catatan: nama service compose
adalah `ztd-backend` (bukan `backend`) — kesalahan pertama drill justru
membuktikan prosedur recovery dari container terhapus (`docker compose up -d
ztd-backend` + reinstall wheel) bekerja.

## 2. Restore database (kerusakan data / migrasi nakal)

```bash
# Backup TERVERIFIKASI dulu (jangan pernah restore dari dump yang belum divalidasi)
docker exec ztd-db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /tmp/restore.sql
tail -n 5 /tmp/restore.sql | grep -q "PostgreSQL database dump complete" || abort

# Restore: drop, create, replay
docker exec ztd-db psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE $POSTGRES_DB"
docker exec ztd-db psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER"
docker cp /tmp/restore.sql ztd-db:/tmp/restore.sql
docker exec ztd-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /tmp/restore.sql

# Verifikasi digest data (bandingkan sebelum kejadian)
psql -t -A -c "SELECT count(*) FROM devices;"
```

Bukti staging (P7-B): dump 13.802 B dengan marker lengkap → korupsi disimulasikan
(UPDATE status, DELETE provisioning_devices, polusi temp_unit) → drop+create+replay
→ digest identik (3 devices, 2 telemetry, 1 provisioning), `temp_unit` legacy
tetap NULL.

Jika pg_dumpall/pg_basebackup tersedia, cadangan berkala via
`systemd/ztd-backup.timer` + `scripts/backup-db.sh` (retensi 7 hari) adalah jalur
utama; dump manual di atas adalah jalur cepat tanpa timer.

## 3. Rollback konfigurasi (compose / nginx)

```bash
# Sebelum mengubah config selalu:
cp docker-compose.yml /tmp/compose.bak.$(date +%s)
cp nginx/default.conf /tmp/nginx.bak.$(date +%s)

# --- saat config buruk terdeteksi ---
cp /tmp/compose.bak.<ts> docker-compose.yml
cp /tmp/nginx.bak.<ts>  nginx/default.conf
docker exec ztd-nginx nginx -t                       # wajib successful
docker exec ztd-nginx nginx -s reload
docker compose config >/dev/null && echo valid       # wajib valid
curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/   # 200
```

Bukti staging (P7-C): nginx.conf dirusak (unexpected end of file) → `nginx -t`
failed; restore file → `nginx -t successful`, reload OK, compose config valid,
HTTPS 200, keempat container healthy.

## 4. Urutan keputusan saat insiden

1. Backend unhealthy? → cek `docker logs` → kalau release baru: **§1**.
2. Data rusak/migrasi nakal? → stop Tulis baru (down backend) → **§2** → up lagi.
3. Masalah muncul setelah ubah config? → **§3**.
4. Kombinasi? → §3 (config) → §1 (image) → §2 (data) — config paling murah,
   data paling mahal, kerjakan terakhir.
5. Jangan jalankan `003_provisioning_v2.down.sql` di produksi kecuali telah
   mengekspor tabel `provisioning_*` (drop data v2; file itu sendiri memperingatkan).
