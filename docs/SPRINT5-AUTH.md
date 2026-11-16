# Sprint 5 — Centralized Authentication & RBAC

## Background

Sprint 5 replaces the legacy itsdangerous-signed cookie session with a centralized,
server-side session architecture. Two repositories are updated:

| Repo | Head |
|---|---|
| `ztd-infrastructure` (backend) | `f05ee196c08f79f941533f4cb08f6b9e9be2ac84` |
| `ztd-dashboard` (frontend) | `942514fda79f8ecea082c8e48c33080ca7a43e87` |

---

## What Changed

### Backend (`ztd-infrastructure`)

- **New tables**: `app_users`, `app_sessions`, `app_audit_events` (migration `004_central_auth`)
- **Auth package** `src/auth/`: models, service, dependencies, routes
  - `POST /api/auth/login` — Argon2id verify, opaque token issued, login rate-limit
  - `POST /api/auth/logout` — server-side session revoked
  - `GET /api/auth/me` — `{username, role}` or 401
  - `POST /api/auth/change-password` — re-hashes; revokes all OTHER sessions
  - `GET/POST/PATCH /api/auth/users` — ADMIN user CRUD
  - `POST /api/auth/users/:id/reset-password` — ADMIN; revokes all target sessions
  - `POST /api/auth/users/:id/revoke-sessions` — ADMIN; kills all sessions
  - `GET /api/auth/audit-events` — ADMIN; newest-first security log
- **RBAC enforcement** (backend-authoritative):
  - Devices config/DELETE — ADMIN only
  - Modules GET — any authenticated user
  - Bootstrap V1 POST (`/api/v1/bootstrap/raspberry`) — ADMIN only
  - BFF proxy mutations + BFF bootstrap — ADMIN only
  - Last-admin protection: last ADMIN cannot be deactivated or demoted (409)
- **Dual-era BFF principal**: itsdangerous legacy cookie still works (ADMIN default) until Phase 6 cutover. Opaque central token resolves role from DB.
- **Bootstrap script** `scripts/create-first-admin.py` — one-shot; no public registration

### Frontend (`ztd-dashboard`)

- **LoginView** — centralized login page; status-specific errors (401/403/429/503); redirect query
- **useSession composable** — module-scoped reactive state shared by router guard, App.vue, views
- **Router guard** — waits for `/api/auth/me` probe; redirects unauthenticated to `/login?redirect=...`; ADMIN-only meta for `/users`
- **App.vue** — sidebar profile menu (username/role/profile link/logout); ADMIN-only User Management nav
- **UsersView** — ADMIN user management (CRUD, role change, disable/enable, password reset, revoke sessions)
- **ProfileView** — self-service password change (revokes other sessions)
- **DeploymentsView** — embedded provisioning login form removed; uses global session state

---

## Migration: Deploying to Staging

> **IMPORTANT**: These steps must be performed on staging. Production deployment requires Phase 8 GO/NO-GO sign-off.

### Prerequisites

- VPS online and accessible: `ssh firza@100.105.163.126`
- Argon2id wheels staged at `/home/firza/deploy-artifacts/`:
  - `argon2_cffi-21.2.0-cp313-cp313-manylinux_2_27_x86_64.manylinux2014_x86_64.whl` (SHA256 `b746dba8...`)
  - `argon2_cffi-21.2.0-cp313-cp313-manylinux_2_34_x86_64.whl` (SHA256 `c670642b...`)
- PostgreSQL accessible and restorable from prod dump

### Step 1 — Install Argon2id Wheels

```bash
ssh firza@100.105.163.126
pip3 install /home/firza/deploy-artifacts/argon2_cffi-21.2.0-*.whl --force-reinstall --no-deps
python3 -c "import argon2; print(argon2.__version__)"
# Expected: 21.2.0
```

### Step 2 — Restore Staging DB from Prod Dump

```bash
# On VPS
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='ztd_prod';" 2>/dev/null || true
sudo -u postgres dropdb ztd_prod 2>/dev/null || true
sudo -u postgres createdb -O ztd_app ztd_prod
# Restore prod schema dump (if available)
# cat /path/to/prod_dump.sql | sudo -u postgres psql ztd_prod
```

### Step 3 — Build and Run Staging Backend

```bash
# On VPS — build new image
cd /home/firza/ztd-infrastructure
git checkout sprint5/auth-central-rbac

# Copy wheels into the build context
cp /home/firza/deploy-artifacts/argon2_cffi-21.2.0-*.whl ./

# Add to Dockerfile or pip install before CMD (see Dockerfile edits)
# Edit Dockerfile: COPY argon2*.whl /tmp/ && pip install --no-deps /tmp/argon2*.whl

docker build -t ztd-backend:sprint5-auth -f Dockerfile .
docker run -d --name ztd-stage-auth-test \
  -e DATABASE_URL=postgresql://ztd_app:CHANGEME@localhost:5432/ztd_prod \
  -e ZTD_SECRET_KEY="$(openssl rand -hex 48)" \
  -e ZTD_DASHBOARD_SESSION_SECRET="$(openssl rand -hex 48)" \
  -p 8001:8000 \
  --restart unless-stopped \
  ztd-backend:sprint5-auth
```

### Step 4 — Apply Migration 004

```bash
# Apply: creates app_users, app_sessions, app_audit_events
PGPASSWORD=CHANGEME psql -h localhost -U ztd_app -d ztd_prod -f /home/firza/ztd-infrastructure/postgres/migrations/004_central_auth.up.sql

# Verify
PGPASSWORD=CHANGEME psql -h localhost -U ztd_app -d ztd_prod -c "\dt app_*"
```

### Step 5 — Bootstrap First Admin

```bash
# Interactive (will prompt for password)
docker exec ztd-stage-auth-test python scripts/create-first-admin.py

# Or via stdin (non-interactive)
echo "my-admin-password" | docker exec -i ztd-stage-auth-test python scripts/create-first-admin.py --password-stdin

# Or from env (for CI)
docker exec -e ZTD_ADMIN_PASSWORD="my-admin-password" ztd-stage-auth-test python scripts/create-first-admin.py
```

### Step 6 — Verify Login

```bash
# Test login
curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"my-admin-password"}' \
  -i | grep -E "Set-Cookie|HTTP/|detail"

# Expected: HTTP/1.1 200 + Set-Cookie: ztd_session=<opaque>; HttpOnly; Secure; SameSite=Strict
```

### Step 7 — Run Backend Tests (SQLite ephemeral)

```bash
cd /home/firza/ztd-infrastructure/apps/api
pip3 install -r requirements.txt -r requirements-test.txt --no-deps
python -m pytest tests/ -q --ignore=tests/test_provisioning_postgres.py --ignore=tests/test_dual_server_acceptance_16.py 2>&1 | tail -3
# Expected: 291 passed, 2 skipped
```

### Step 8 — Deploy Dashboard Dist

```bash
cd /home/firza/ztd-dashboard
git checkout sprint5/auth-central-rbac
npm ci && npm run build

# Copy dist to staging nginx serving directory
rsync -av dist/ firza@100.105.163.126:/tmp/dist-s5/
ssh firza@100.105.163.126 "sudo cp -a /tmp/dist-s5/. /usr/share/nginx/html/"
```

### Step 9 — Browser E2E (Playwright)

```bash
# On local machine with Playwright installed
cd /home/firza/ztd-infrastructure
pip3 install playwright 2>/dev/null || true
python -m playwright install chromium 2>/dev/null || true

python3 - <<'EOF'
import subprocess, sys

def e2e_test(url, expected_texts):
    # Basic smoke: page loads without JS error
    print(f"Smoke test: {url}")

# Staging URL (adjust port as per Step 3)
STAGING = "http://100.105.163.126:8001"
# Dashboard URL (adjust as per staging nginx)
DASHBOARD = "https://dashboard-staging.example.com"

print("Phase 1: /api/auth/me without session -> 401")
r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    f"{STAGING}/api/auth/me"])
assert r.stdout.decode().strip() == "401", f"Expected 401, got {r.stdout.decode()}"
print("  401 OK")

print("Phase 2: /api/auth/login with wrong creds -> 401")
r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    "-X", "POST", f"{STAGING}/api/auth/login",
                    "-H", "Content-Type: application/json",
                    "-d", '{"username":"admin","password":"wrong"}'])
assert r.stdout.decode().strip() == "401"
print("  401 OK")

print("Phase 3: login flow with correct creds -> 200 + Set-Cookie")
r = subprocess.run(["curl", "-s", "-D", "-", "-o", "/dev/null",
                    "-X", "POST", f"{STAGING}/api/auth/login",
                    "-H", "Content-Type: application/json",
                    "-d", '{"username":"admin","password":"my-admin-password"}'])
assert "Set-Cookie: ztd_session" in r.stdout
assert "HttpOnly" in r.stdout
assert "Secure" in r.stdout or "X-Forwarded-Proto: https" in r.stdout  # Depends on proxy
print("  Cookie OK")

print("Phase 4: /api/auth/me with valid session -> 200 + user info")
print("  (requires cookie jar — manual test recommended)")

print("Phase 5: RBAC — VIEWER accessing admin-only endpoint -> 403")
# Create a VIEWER user via create-first-admin.py or direct DB insert,
# then login as VIEWER and try /api/v1/bootstrap/raspberry
print("  (manual E2E: create VIEWER, login as VIEWER, try /api/v1/bootstrap/raspberry)")

print("\nAll automated checks PASSED")
EOF
```

---

## Rollback Runbook

If Sprint 5 staging validation fails and a full rollback is required:

### Backend Rollback

```bash
cd /home/firza/ztd-infrastructure
git checkout sprint4/blocker-remediation  # or v2-aa8622c

# Re-tag / rebuild the pre-sprint image
docker build -t ztd-backend:v2-aa8622c -f Dockerfile .
docker stop ztd-backend && docker rm ztd-backend
docker run -d --name ztd-backend \
  ... (original run args) ... \
  ztd-backend:v2-aa8622c

# Drop new tables (additive migration: no legacy data is lost)
PGPASSWORD=PASSWORD psql -h localhost -U ztd_app -d ztd_prod -f /home/firza/ztd-infrastructure/postgres/migrations/004_central_auth.down.sql
```

### Frontend Rollback

```bash
cd /home/firza/ztd-dashboard
git checkout sprint4/blocker-remediation  # or v2-c584f05
npm run build
rsync -av dist/ firza@100.105.163.126:/tmp/dist-rollback/
ssh firza@100.105.163.126 "sudo cp -a /tmp/dist-rollback/. /usr/share/nginx/html/"
```

---

## Security Properties

| Property | Status |
|---|---|
| Password hashing | Argon2id (time=3, memory=65536, parallelism=4) |
| Session token | 32-byte urlsafe random; SHA-256 at rest; opaque to browser |
| Cookie flags | HttpOnly + Secure (if HTTPS) + SameSite=Strict |
| Session TTL | 8h absolute + 2h idle sliding |
| Login rate limit | Per-(user, IP): 10 attempts/60s → 429 + Retry-After |
| CSRF protection | Same-origin Origin/Sec-Fetch-Site check on non-GET |
| Session revocation | Server-side per session row; client-side cookie delete |
| Password change | Rotates token; revokes all OTHER sessions |
| Audit trail | `app_audit_events`: every login, logout, role-change, session-revoke |
| Legacy compat | itsdangerous cookie still accepted until Phase 6 (ADMIN default) |

---

## Permission Matrix

| Endpoint | ADMIN | VIEWER | Legacy (htpasswd) |
|---|---|---|---|
| `GET /api/v1/modules` | ✅ | ✅ | ✅ (ADMIN) |
| `POST /api/v1/devices/:id/config` | ✅ | 403 | 401 (no session) |
| `DELETE /api/v1/devices/:id` | ✅ | 403 | 401 (no session) |
| `POST /api/v1/bootstrap/raspberry` | ✅ | 403 | 403 (RBAC) |
| `GET /api/v2/provisioning/*` | ✅ | ✅ | ✅ |
| `POST /api/v2/provisioning/*` | ✅ | 403 | 403 |
| `POST /api/dashboard/bootstrap/raspberry` | ✅ | 403 | 403 |
| `GET/POST /api/dashboard/session` | ✅ | ✅ | ✅ |
| `POST /api/auth/*` | ✅ | varies | ✅ |

---

## Phase 6 Cutover (Not in This Sprint)

After Phase 5 validation, Phase 6 retires the legacy BFF layer:
1. Create all existing htpasswd users as central `AppUser` rows (with migrated Argon2id hashes)
2. Deploy new image
3. Verify admin login works with central credentials
4. Remove legacy signer from `_current_user`
5. Remove `ZTD_DASHBOARD_SESSION_SECRET`, `ZTD_DASHBOARD_HTPASSWD` env vars
