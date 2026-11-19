# Sprint 5 — Permission matrix (source of truth for RBAC implementation)

Legend: PUBLIC = no auth; USER = any authenticated dashboard session (ADMIN|VIEWER);
ADMIN = authenticated + role=ADMIN; 403 = authenticated VIEWER gets Forbidden.
Agent paths use their own credentials and are NEVER dashboard-session-gated.

| # | Endpoint / asset | Path | Old guard | New guard | Viewer | Notes |
|---|---|---|---|---|---|---|
| 1 | Login | POST /api/auth/login | — | PUBLIC + rate-limit + CSRF | n/a | session rotation on success |
| 2 | Logout | POST /api/auth/logout | — | USER (or anon→401? no: logout tolerates anon, revokes nothing) | ok | revokes server-side |
| 3 | Me | GET /api/auth/me | — | USER | ok | returns role |
| 4 | Change own password | POST /api/auth/change-password | — | USER | ok | revokes other sessions |
| 5 | List users | GET /api/auth/users | — | ADMIN | 403 | |
| 6 | Create user | POST /api/auth/users | — | ADMIN | 403 | no public signup |
| 7 | Update user (role/active) | PATCH /api/auth/users/{id} | — | ADMIN | 403 | last-admin protection |
| 8 | Reset password | POST /api/auth/users/{id}/reset-password | — | ADMIN | 403 | revokes target sessions |
| 9 | Revoke sessions | POST /api/auth/users/{id}/revoke-sessions | — | ADMIN | 403 | |
| 10 | Audit events | GET /api/auth/audit-events | — | ADMIN | 403 | |
| 11 | Devices read | GET /api/v1/devices[/...] | nginx htpasswd (method-based) | USER (backend-enforced) | ok read | nginx layer retired later |
| 12 | Summary/metrics/telemetry/logs | GET /api/v1/... | nginx htpasswd | USER | ok read | |
| 13 | Device config (MQTT desired-state) | POST /api/v1/devices/{id}/config | nginx htpasswd | ADMIN | 403 | mutation |
| 14 | Device delete | DELETE /api/v1/devices/{id} | nginx htpasswd | ADMIN | 403 | mutation |
| 15 | Module catalog | GET /api/v1/modules | nginx htpasswd | USER | ok read | catalog is public data but read requires session |
| 16 | Bootstrap V1 script | POST /api/v1/bootstrap/raspberry | nginx htpasswd all-methods | ADMIN (backend) | 403 | V2 BFF is the UI path |
| 17 | BFF login (legacy) | POST /api/dashboard/session | htpasswd inside BFF | DEPRECATED → kept until cutover; forwards to central users DB if htpasswd missing? NO — kept as-is (isolated) | — | Phase 6 retires it |
| 18 | BFF proxy (provisioning via cookie) | ANY /api/dashboard/v2/provisioning/* | BFF session cookie | BFF session cookie (unchanged) + role check: ADMIN-only mutations via backend role | 403 on mutation | proxy injects admin bearer |
| 19 | BFF bootstrap download | POST /api/dashboard/bootstrap/raspberry | BFF session + CSRF | BFF session + CSRF + role check ADMIN | 403 | |
| 20 | Provisioning device auth | POST/GET /api/v2/provisioning/register|status|manifest | device HTTP Basic | UNCHANGED (device protocol) | never dashboard-gated |
| 21 | Provisioning admin ops | POST /api/v2/provisioning/devices, PUT /modules/{n} | admin bearer | admin bearer UNCHANGED + BFF proxy gated by ADMIN | 403 via BFF | direct bearer calls are machine-only |
| 22 | Monitoring callbacks | PUT /api/v2/provisioning/integrations/monitoring/... | monitoring bearer | UNCHANGED | n/a | separate trust domain |
| 23 | Health | GET /health | public | PUBLIC | n/a | watchdog needs it |
| 24 | Root/docs/openapi | GET /, /docs, /openapi.json | public | PUBLIC (docs disabled in prod release? verify) | n/a | low risk |
| 25 | MQTT ws | /mqtt (websocket) | ztd-dashboard mqtt user | UNCHANGED | n/a | |
| 26 | Users UI (new) | /users (SPA route) | — | frontend ADMIN-only nav + backend 403s | hidden | backend is authority |

## Effective-permission review of legacy GETs (spec requirement)
- GET /api/v1/devices/{id}/metrics|telemetry|logs — read-only: VIEWER ok.
- GET /api/v1/modules — read-only catalog: VIEWER ok.
- No mutating GETs found in the app (device config is POST; assignments are PUT/DELETE via BFF).
- BFF proxy forwards arbitrary methods; provisioning backend enforces its own
  auth. BFF adds: session cookie + ADMIN check on non-GET proxy methods
  (viewer mutations 403) — see BFF changes in this sprint.

## Enforcement points
1. Backend FastAPI dependencies (authoritative): 401/403 as above.
2. nginx: auth_basic REMOVED for /api/ once central auth is live (Phase 6);
   until then nginx layer stays but backend no longer depends on it.
3. Frontend: route guards + hidden controls (never authoritative).
