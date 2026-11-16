# Phase 8 Readiness Report — Sprint 5 Auth & RBAC

**Date**: 2026-11-16
**Branch**: `sprint5/auth-central-rbac`
**Scope**: Centralized authentication + RBAC + user management. **NO production deployment.**

---

## Verdict: **GO (staging) — NO-GO (production)**

All Sprint 5 implementation and test work is complete and committed. Staging
rehearsal remains before any production cut-over. The production system
(`v2-aa8622c` backend, dist `c584f05` dashboard) is **untouched**.

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

## Staging Rehearsal Plan (next action)

1. Build new image `ztd-backend:sprint5-auth` from branch head with staged wheels.
2. Spin ephemeral PG container; restore prod-schema dump; apply `004_central_auth.up.sql`.
3. Run `create-first-admin.py` in the container; verify `200` + `Set-Cookie: ztd_session=...; HttpOnly; SameSite=Strict`.
4. Browser E2E (Playwright) against isolated HTTPS staging endpoint:
   - unauthenticated → `/login`
   - wrong creds → 401 message
   - correct creds → dashboard, session cookie set
   - VIEWER account: all restricted buttons hidden; direct API POST → 403
   - ADMIN account: full access
   - change-password → other sessions revoked
5. Re-run `004_central_auth.down.sql` then `.up.sql` (idempotence + reversibility).
6. Tear down staging containers.

**No production deploy is triggered by this sprint.**

---

## Known Limitations (staging-only, pre-cutover)

- Legacy htpasswd users default to ADMIN in the BFF; this disappears in Phase 6.
- nginx `auth_basic` remains in front of `/api/v1/bootstrap/` and non-GET `/api/`
  until Phase 6; the browser will not be prompted because the dashboard uses the
  central session, but direct curl to those paths still needs HTTP Basic or the
  BFF proxy.
- Argon2 wheels are pinned and staged offline — a new host requires copying
  `/home/firza/deploy-artifacts/*.whl` or internet access at build time.

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

## Phase 6 Cutover Prerequisites (recorded, not executed)

- Migrate htpasswd `operator` account to central DB with the same password (or
  force reset on first login).
- Remove `ZTD_DASHBOARD_SESSION_SECRET` and `ZTD_DASHBOARD_HTPASSWD` env vars.
- Remove nginx `auth_basic` from `/api/v1/bootstrap/` and non-GET `/api/`.
- Remove the legacy branch in `_current_user` (itsdangerous path).
- Verify all admin workflows once against the production stack.
