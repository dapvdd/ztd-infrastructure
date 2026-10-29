#!/usr/bin/env bash
# harden-nginx.sh — jalankan dari ~/ztd-infrastructure
#
# Yang diubah:
#  1. nginx/default.conf : POST/PUT/DELETE di /api/ dan semua method di
#                          /api/v1/bootstrap/ wajib basic auth. GET tetap
#                          terbuka (dashboard monitoring).
#  2. docker-compose.yml : port backend 8000 jadi 127.0.0.1:8000 (gak bisa bypass nginx dari LAN),
#                          dan mount nginx/.htpasswd ke container nginx.
#  3. nginx/.htpasswd    : dibuat baru (hash apr1), masuk .gitignore.
# Yang TIDAK diubah: kode backend, watchdog (pakai localhost:8000, tetap jalan), isi lain default.conf.
# Aman diulang. Backup otomatis: *.bak-<timestamp>. DRY_RUN=1 = cuma edit file, tanpa docker.
set -euo pipefail

DRY="${DRY_RUN:-0}"
TS="$(date +%Y%m%d-%H%M%S)"
ADMIN_USER="${ADMIN_USER:-admin}"
die() { echo "ERROR: $*" >&2; exit 1; }

[ -f docker-compose.yml ] && [ -f nginx/default.conf ] || die "jalankan dari ~/ztd-infrastructure"
command -v openssl >/dev/null || die "openssl tidak ada"
command -v python3 >/dev/null || die "python3 tidak ada"

if [ -z "${ADMIN_PASS:-}" ]; then
  read -r -s -p "Password untuk user '$ADMIN_USER': " ADMIN_PASS; echo
  read -r -s -p "Ulangi password: " ADMIN_PASS2; echo
  [ "$ADMIN_PASS" = "$ADMIN_PASS2" ] || die "password tidak sama"
fi
[ "${#ADMIN_PASS}" -ge 8 ] || die "password minimal 8 karakter"

# ---- backup ----
cp -p nginx/default.conf "nginx/default.conf.bak-$TS"
cp -p docker-compose.yml "docker-compose.yml.bak-$TS"
if [ -f nginx/.htpasswd ]; then cp -p nginx/.htpasswd "nginx/.htpasswd.bak-$TS"; fi

rollback() {
  echo ">> Rollback ke backup $TS"
  cp -p "nginx/default.conf.bak-$TS" nginx/default.conf
  cp -p "docker-compose.yml.bak-$TS" docker-compose.yml
  exit 1
}

# ---- 1. nginx config ----
cat > nginx/default.conf <<'NGINX'
server {
    listen       80;
    server_name  _;

    # ZTD backend API (FastAPI on ztd-backend:8000, same docker network).
    # GET/HEAD/OPTIONS terbuka untuk dashboard monitoring; method yang mengubah data wajib login.
    location /api/ {
        limit_except GET HEAD OPTIONS {
            auth_basic           "ZTD Admin";
            auth_basic_user_file /etc/nginx/.htpasswd;
        }

        proxy_pass http://ztd-backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization     "";
        proxy_connect_timeout 5s;
        proxy_send_timeout    60s;
        proxy_read_timeout    60s;
    }

    # API docs (preserved from 6fed070)
    location /docs {
        proxy_pass http://ztd-backend:8000/docs;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /openapi.json {
        proxy_pass http://ztd-backend:8000/openapi.json;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # MQTT over WebSocket (preserved from 6fed070)
    location /mqtt {
        proxy_pass http://ztd-mqtt:9001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }

    # Leftover backup / editor files must never be served (e.g. index.html.bak).
    location ~* \.(bak|backup|old|orig|save|swp|swo|tmp)$ {
        return 404;
    }

    # SPA static frontend
    location / {
        root   /usr/share/nginx/html;
        index  index.html;
        try_files $uri $uri/ /index.html;
    }
}
NGINX

# ---- 2. htpasswd (password lewat stdin, bukan argv, biar gak muncul di ps) ----
printf '%s:%s\n' "$ADMIN_USER" "$(printf '%s' "$ADMIN_PASS" | openssl passwd -apr1 -stdin)" > nginx/.htpasswd
chmod 644 nginx/.htpasswd   # worker nginx (bukan root) harus bisa baca; isinya cuma hash
touch .gitignore
for pat in "nginx/.htpasswd" "nginx/.htpasswd.bak-*"; do
  grep -qxF "$pat" .gitignore || echo "$pat" >> .gitignore
done

# ---- 3. docker-compose.yml ----
python3 - <<'PY' || rollback
import re, sys

path = "docker-compose.yml"
lines = open(path).read().split("\n")

def fail(msg):
    print("ERROR compose: " + msg, file=sys.stderr)
    sys.exit(2)

def block(name):
    start = next((i for i, l in enumerate(lines) if re.match(rf"^  {re.escape(name)}:\s*$", l)), None)
    if start is None:
        return None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        l = lines[j]
        if l.lstrip().startswith("#") or not l.strip():
            continue
        if re.match(r"^\S", l) or re.match(r"^  \S", l):
            end = j
            break
    return start, end

# nginx: tambah mount .htpasswd
s, e = block("ztd-nginx")
if s is None:
    fail("service ztd-nginx tidak ketemu")
seg = lines[s:e]
if any(".htpasswd" in l for l in seg):
    print("compose: mount .htpasswd sudah ada")
else:
    idx = next((i for i, l in enumerate(seg) if re.search(r"\./nginx/default\.conf:", l)), None)
    if idx is None:
        fail("baris mount ./nginx/default.conf di ztd-nginx tidak ketemu. Tambahkan manual: - ./nginx/.htpasswd:/etc/nginx/.htpasswd:ro")
    prefix = re.match(r"^(\s*-\s*)", seg[idx]).group(1)
    seg.insert(idx + 1, f"{prefix}./nginx/.htpasswd:/etc/nginx/.htpasswd:ro")
    lines[s:e] = seg
    print("compose: mount .htpasswd ditambahkan ke ztd-nginx")

# backend: port 8000 -> 127.0.0.1
s, e = block("ztd-backend")
if s is None:
    fail("service ztd-backend tidak ketemu")
in_ports, pind, found = False, 0, False
for i in range(s + 1, e):
    l = lines[i]
    if not l.strip() or l.lstrip().startswith("#"):
        continue
    ind = len(l) - len(l.lstrip())
    if re.match(r"^\s+ports:\s*$", l):
        in_ports, pind = True, ind
        continue
    if in_ports and ind <= pind and not l.lstrip().startswith("-"):
        in_ports = False
    if not in_ports:
        continue
    m = re.match(r'^(\s*-\s*)(["\']?)([^"\'#]+?)\2\s*(#.*)?$', l)
    if not m or not m.group(3).strip().endswith(":8000"):
        continue
    found = True
    spec = m.group(3).strip()
    if spec.startswith("127.0.0.1:"):
        print("compose: port backend sudah 127.0.0.1")
        continue
    host = re.sub(r"^0\.0\.0\.0:", "", spec[: -len(":8000")])
    lines[i] = f'{m.group(1)}"127.0.0.1:{host}:8000"'
    print(f"compose: port backend {spec} -> 127.0.0.1:{host}:8000")
if not found:
    fail("mapping port '...:8000' di ztd-backend tidak ketemu (format long-syntax / tanpa ports?). Ubah manual jadi \"127.0.0.1:8000:8000\"")

open(path, "w").write("\n".join(lines))

# cetak service nginx apa adanya (buat tau dari mana frontend statis di-mount)
s, e = block("ztd-nginx")
print("\n--- service ztd-nginx sekarang ---")
print("\n".join(lines[s:e]).rstrip())
print("--- selesai ---")
PY

echo; echo "=== perubahan nginx/default.conf ==="; diff -u "nginx/default.conf.bak-$TS" nginx/default.conf || true
echo; echo "=== perubahan docker-compose.yml ==="; diff -u "docker-compose.yml.bak-$TS" docker-compose.yml || true

if [ "$DRY" = "1" ]; then echo; echo "[DRY_RUN] file sudah diedit, docker tidak disentuh."; exit 0; fi

# ---- validasi sebelum menyentuh container yang jalan ----
echo; echo ">> Validasi compose & config nginx (belum restart apa pun)..."
docker compose config -q || rollback
docker compose run --rm -T --no-deps --entrypoint nginx ztd-nginx -t || rollback

echo
read -r -p "Terapkan sekarang? nginx ke-recreate (~1 detik), backend ke-recreate (API mati beberapa detik). [y/N] " ans
if [ "$ans" != "y" ]; then
  echo "Dibatalkan, file dikembalikan."; cp -p "nginx/default.conf.bak-$TS" nginx/default.conf; cp -p "docker-compose.yml.bak-$TS" docker-compose.yml; exit 0
fi

docker compose up -d ztd-nginx ztd-backend
echo ">> Tunggu backend siap..."; sleep 8

# ---- smoke test ----
http() { curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$@" || true; }
auth() {
  local p="${ADMIN_PASS//\\/\\\\}"; p="${p//\"/\\\"}"
  printf 'user = "%s:%s"\n' "$ADMIN_USER" "$p" | curl -s -o /dev/null -w '%{http_code}' --max-time 8 -K - "$@" || true
}
LAN_IP="$(hostname -I | awk '{print $1}')"
FAILS=0
t() { # nama, harapan, hasil
  if [ "$2" = "$3" ]; then echo "PASS  $1 (=$3)"; else echo "FAIL  $1 (harap $2, dapat $3)"; FAILS=$((FAILS+1)); fi
}
t "GET  /api/v1/devices tanpa login (dashboard)"        200 "$(http http://localhost/api/v1/devices)"
t "DELETE tanpa login ditolak"                          401 "$(http -X DELETE http://localhost/api/v1/devices/__probe__)"
t "DELETE dengan login lolos nginx (device palsu=404)"  404 "$(auth -X DELETE http://localhost/api/v1/devices/__probe__)"
t "POST bootstrap tanpa login ditolak"                  401 "$(http -X POST -H 'Content-Type: application/json' -d '{}' http://localhost/api/v1/bootstrap/raspberry)"
t "backend localhost:8000 (jalur watchdog) tetap hidup" 200 "$(http http://localhost:8000/health)"
t "backend via IP LAN :8000 tertutup"                   000 "$(http http://$LAN_IP:8000/health)"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "SEMUA LOLOS. Backup: *.bak-$TS"
else
  echo "$FAILS tes gagal. Rollback: cp -p nginx/default.conf.bak-$TS nginx/default.conf && cp -p docker-compose.yml.bak-$TS docker-compose.yml && docker compose up -d ztd-nginx ztd-backend"
  exit 1
fi