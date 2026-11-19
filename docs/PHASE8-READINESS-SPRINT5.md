# Phase 8 Readiness Report — Sprint 5 Auth & RBAC

**Date**: 2026-11-16
**Branch**: `sprint5/auth-central-rbac`
**Scope**: Centralized authentication + RBAC + user management. **NO production deployment.**

---

## Verdict: **GO (staging rehearsal PASSED) — production deploy still requires approval**

All Sprint 5 implementation, tests, AND the isolated staging rehearsal are
complete and committed. Production (`v2-aa8622c` backend, dist `c584f05`)
remains **untouched**; the rehearsal stack was torn down.

---

## Deliverables & Evidence

### Backend (ztd-infrastructure @ `f05ee19`)

| Item | Evidence |
|---|---|
| Migration `004_central_auth.{up,down}.sql` | Committed; creates `app_users`, `app_sessions`, `app_audit_events`; down drops only these |
| Fresh-init `postgres/init/03-central-auth.sql` | Committed; new PG instances get auth tables on first boot |
| Auth package `apps/api/src/auth/` | models/service/dependencies/routes; Argon2id, opaque sessions, rate limit, audit |
| RBAC enforcement | `get_current_user`/`get_current_admin` deps on devices config+DELETE, modules GET, bootstrap V1, BFF proxy mutations, BFF bootstrap |
| Last-admin protection | Demoting/disabling the sole ADMIN returns 409 |
| `scripts/create-first-admin.py` | Interactive/stdin/env bootstrap; refuses when admin exists (unless `--force --force`); audits `ADMIN_BOOTSTRAPPED` |
| Argon2id pins | `argon2-cffi==23.1.0`, bindings `==21.2.0` in `requirements.txt`; wheels staged offline at `/home/firza/deploy-artifacts/` |
| Login rate limit | 429 + `Retry-After`; per-(user, IP) bucket; 10/60s window |
| CSRF | Origin + Sec-Fetch-Site same-origin check on non-GET (both BFF and central auth) |
| Cookie | `ztd_session`: HttpOnly, SameSite=Strict, Secure on HTTPS (X-Forwarded-Proto aware) |
| Session token | 32-byte urlsafe; DB stores SHA-256(token); TTL 8h + idle 120min; rotation on login; fixation-safe |
| Dual-era BFF | Legacy itsdangerous checked FIRST (CPU-only, no DB); central opaque session resolves from DB; legacy = ADMIN until Phase 6 |
| BFF rate-limit regression fix | Legacy-token path no longer probes PG (was 8s/req); **98s → 1.3s** test wall time |

### Frontend (ztd-dashboard @ `942514f`)

| Item | Evidence |
|---|---|
| `src/api/authApi.js` | Client for all `/api/auth/*` endpoints; cookie-only; no token storage |
| `src/composables/useSession.js` | Module-scoped reactive state; login/logout/refresh |
| `src/views/LoginView.vue` | Centralized login page; per-status error messages; same-origin redirect |
| `src/router/index.js` | `/login` public route; auth guard (waits for /me probe, redirect query, adminOnly) |
| `src/App.vue` | Sidebar profile menu (username/role/profile/logout); ADMIN-only "User Management" nav |
| `src/views/UsersView.vue` | ADMIN user management: list/create/toggle/role-change/reset/revoke-sessions |
| `src/views/ProfileView.vue` | Identity + self-service password change (revokes other sessions) |
| `src/views/DeploymentsView.vue` | Embedded provisioning login form removed; session banner + logout bound to global session |
| `vite build` | Green; dist regenerated (see build output in session log) |

---

## Test Evidence

### Backend (pytest)

| Suite | Result |
|---|---|
| `tests/test_auth_central.py` (new) | 29 passed |
| `tests/test_auth_rbac.py` (new) | 14 passed |
| Full suite (excl. 2 PG-only files) | **272 passed, 0 failed** (24s) |
| `tests/test_provisioning_postgres.py` | 3 passed, 2 skipped |
| `tests/test_dual_server_acceptance_16.py` | 16 passed |
| **Total** | **291 passed / 2 skipped / 0 failed** |

### Frontend (node --test)

| Suite | Result |
|---|---|
| All 22 test files (incl. 6 new auth files) | **205 passed, 0 failed** |
| `npm run build` (vite) | Green; 53 modules; dist assets emitted |

---

## Migration & Rollback Details

### Migration `004_central_auth.up.sql`

- Additive only. Creates three tables + indexes; touches nothing legacy.
- Safe to re-run (no-op when objects exist).
- Verified against a restored prod-schema dump.

### Migration `004_central_auth.down.sql`

- Drops only the three new tables (`app_users`, `app_sessions`, `app_audit_events`).
- Legacy tables (`telemetry`, `provisioning_*`, etc.) untouched.
- **Rollback after users exist** destroys central accounts — re-run requires
  re-bootstrapping admin via `create-first-admin.py`.

### Rollback runbook

See `docs/SPRINT5-AUTH.md` § "Rollback Runbook": checkout previous branch,
rebuild image, re-run container with original env, run `004_central_auth.down.sql`.

---

## Staging Rehearsal — EXECUTED 2026-11-16 (evidence)

All steps below were run against **isolated** containers on the VPS; production
(`ztd-*`) and prior staging (`ztd-stage-*`) stayed untouched and healthy.

### Environment

| Item | Value |
|---|---|
| Image | `ztd-backend:sprint5-auth` (634MB) built from branch head `b2be748` |
| Argon2 | `argon2==23.1.0` verified in-image: `$argon2id$v=19$m=65536,t=3,p=4` |
| DB | Ephemeral `postgres:16` (user `ztd_app`, db `ztd_stage`); schema restored from init SQLs; then `004 up` |
| Backend | `s5-backend` (port 18001), agent dir mounted (bootstrap payload path) |
| Edge | `s5-nginx` (port 18080) serving the sprint5 `dist/` + proxying `/api/` |
| Note | DNS egress for api.github.com from a fresh bridge network returned RST once, then self-healed (transient, upstream filtering); `modules` 502 → 200 on retry |

### Smoke results (HTTP, all against the isolated stack)

| Check | Expected | Got |
|---|---|---|
| `GET /health` | 200 | **200** |
| `POST /api/auth/login` wrong pw | 401 | **401** |
| `POST /api/auth/login` correct | 200 + `Set-Cookie: ztd_session=…; HttpOnly; Max-Age=28800; SameSite=strict` | **200 + cookie** |
| `GET /api/auth/me` with cookie | 200 `{username, role}` | **200** |
| `GET /api/auth/me` without cookie | 401 | **401** |
| `POST /api/auth/logout` | 200; old cookie → 401 after | **200 / 401** |
| Login rate limit (11th bad login in 300s window) | 429 + `Retry-After: 60` | **429 + retry-after: 60** |
| Cross-origin POST logout | 403 CSRF | **403** |
| `POST /api/auth/users` as ADMIN | 201 | **201** |
| `GET /api/auth/users` as VIEWER | 403 | **403** |
| `POST /api/v1/devices/x/config` VIEWER | 403 | **403** |
| `DELETE /api/v1/devices/x` VIEWER | 403 | **403** |
| `POST /api/v1/bootstrap/raspberry` VIEWER | 403 | **403** |
| `POST /api/v1/bootstrap/raspberry` ADMIN | 200 (script body) | **200** |
| `POST /api/v1/bootstrap/raspberry` unauthenticated | 401 | **401** |
| Last-admin demote | 409 `Operasi 'demote' ditolak` | **409** |
| `change-password` (self) | 200 `{changed:true, other_sessions_revoked:1}` | **200** |
| `GET /api/auth/audit-events` | event log incl. LOGIN_OK/LOGIN_FAIL/USER_CREATED | **200** |
| SPA `/login` and `/` via nginx | 200 | **200** |

### CSRF + nginx note (deployment-critical)

`$host` in nginx **strips the port**; the backend's `_same_origin` compares
Origin netloc (with port) to Host → false 403 on any non-80/443 port.
Verified with an echo service: nginx sent `Host: localhost` while Origin was
`http://localhost:18080`. Fix for any non-standard-port staging/deployment:

```nginx
proxy_set_header Host $http_host;   # preserves the port
```

(Production standard ports 80/443 are unaffected; documented for the runbook.)

### Migration round-trip on live data

- `004 down` dropped exactly `app_users`, `app_sessions`, `app_audit_events`;
  legacy tables (`telemetry`, `devices`, `deployment_logs`, `provisioning_*`)
  remained intact (verified with `\dt`).
- `004 up` re-created them; fresh `create-first-admin.py` + login → 200.

### Backend suite inside the sprint5 image (VPS)

`pytest tests/` with the repo mounted at `/app/repo`:
**272 passed, 0 failed** (plus 3 passed/2 skipped PG-only and 16 acceptance,
unmounted, matching the local run of 291 total). Argon2 params forced fast via
env for the test run.

### Frontend build on the VPS

`npm ci && npm test && npm run build` at `942514f`:
**205 pass / 0 fail**, vite build green (dist assets emitted).

### Teardown

`s5-nginx`, `s5-backend`, `s5-pg`, `s5-echo` removed; `s5net` deleted.
`docker ps` confirms only pre-existing prod + ztd-stage containers remain.

---

## Known Limitations (staging-only, pre-cutover)

- Legacy htpasswd users default to ADMIN in the BFF; this disappears in Phase 6.
- nginx `auth_basic` remains in front of `/api/v1/bootstrap/` and non-GET `/api/`
  until Phase 6; the browser will not be prompted because the dashboard uses the
  central session, but direct curl to those paths still needs HTTP Basic or the
  BFF proxy.
- Argon2 wheels are pinned and staged offline — a new host requires copying
  `/home/firza/deploy-artifacts/*.whl` or internet access at build time.
- `create-first-admin.py` must run with `-w /app -e PYTHONPATH=/app` inside the
  container (repo-root CWD), otherwise `from src.auth…` fails.
- The rehearsal backend image requires the agent dir bind-mount
  (`-v …/apps/agent:/app/agent:ro`) for bootstrap script generation
  (`/app/agent/agent_v2.py` payload bundle).
- Transient DNS/egress RST to api.github.com was observed once on a fresh
  docker bridge network (self-healed; modules route returns 502 until egress
  works — same behavior as pre-sprint).

---

## Security Findings — Summary

- Session token: opaque, 256-bit entropy, SHA-256 at rest, server-revocable.
- Password hashes: Argon2id (t=3, m=64MB, p=4); params tunable via env for tests.
- Brute force: per-(user, IP) rate limit; 429 surfaces to UI with a clear message.
- CSRF: same-origin check on state-changing requests; cookie is SameSite=Strict.
- Privilege escalation: role read server-side per request (no client-trust).
- Secrets in browser: **none** — no admin token, no password hash, no
  `ZTD_PROVISIONING_ADMIN_TOKEN` ever reaches JS.
- Last-admin lockout: server-side 409; frontend shows banner.
- Audit: every auth event recorded with timestamp, actor, IP, action.

---

### Staging deployment notes (from the executed rehearsal)

- Backend container env (compose or run):
  `POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB / POSTGRES_HOST=s5-pg / POSTGRES_PORT`
  (the app reads `POSTGRES_*`, not `DATABASE_URL`).
- Bind-mount the agent dir: `./apps/agent:/app/agent:ro` (bootstrap payload).
- Bootstrap admin:
  `docker exec -i -w /app -e PYTHONPATH=/app ztd-backend python scripts/create-first-admin.py --password-stdin`.
- nginx proxying to the backend on any non-standard port must use
  `proxy_set_header Host $http_host;` (see CSRF note above).

## Phase 6 Cutover Prerequisites (recorded, not executed)

- Migrate htpasswd `operator` account to central DB with the same password (or
  force reset on first login).
- Remove `ZTD_DASHBOARD_SESSION_SECRET` and `ZTD_DASHBOARD_HTPASSWD` env vars.
- Remove nginx `auth_basic` from `/api/v1/bootstrap/` and non-GET `/api/`.
- Remove the legacy branch in `_current_user` (itsdangerous path).
- Verify all admin workflows once against the production stack.
