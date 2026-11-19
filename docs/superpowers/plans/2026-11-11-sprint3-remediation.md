# Sprint 3 Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate F-01…F-16 from the Sprint 3 acceptance review so the bootstrap→agent→manifest→HubBrain→dashboard flow is genuinely connected and tested.

**Architecture:** Fixes stay within the existing FastAPI (infrastructure) + Vue dashboard repos. New: a `hub_config` catalog channel that carries only non-secret HubBrain addressing, a BFF router inside the FastAPI app for authenticated dashboard access, TLS-aware nginx, authenticated Mosquitto, and a migration-003 init integration.

**Tech Stack:** Python 3.11/FastAPI/SQLAlchemy/httpx, Vue 3/Vite, pytest, node:test.

**Spec:** Independent Sprint 3 acceptance review (session record); findings F-01–F-16.

## Global Constraints

- READ-ONLY on production; no deploy/push/merge to shared branches.
- Baselines `8ec49007` and `6b6977cd` untouched.
- Monitoring credential issuance stays a documented manual blocker (no fake capability).
- ESP onboarding stays physical-flash; only gateway-side identity mapping.
- Admin bearer token must never reach browser JS.

## Review Focus

- Bootstrap output with Sprint 3 fields must still run clean under `bash -n` and not double-install the legacy agent.
- A manifest with `hub_config` must never contain HUB_KEY/MQTT_PASS; tests pin this.
- BFF must fail closed when `ZTD_DASHBOARD_SESSION_SECRET` is absent/short.
- nginx v2 location must forward the Authorization header (unlike the legacy `/api/` block).
- Fresh-DB path must apply both `01-schema.sql` AND migration 003.

---

### Task 1 (F-01): Bootstrap installs Agent V2

**Files:**
- Modify: `apps/api/src/routes/bootstrap.py` (`_BODY`)
- Test: `apps/api/tests/test_bootstrap_v2.py`

**Interfaces:**
- Produces: a generated script that writes `/etc/ztd/agent.env` from the four Sprint 3 vars, installs `agent_v2.py` + `ztd-agent-v2.service`, enables the unit.

- [ ] Step 1: Failing tests — script references agent install block: contains `install_ztd_agent_v2`, writes `/etc/ztd/agent.env` with all four vars, runs `systemctl enable --now ztd-agent-v2`.
- [ ] Step 2: `bash -n` the generated script in a POSIX shell check (Windows: skip with reason).
- [ ] Step 3: Implement `_BODY` append section guarded by `[ -n "$ZTD_DEVICE_ID" ]`.
- [ ] Step 4: Full bootstrap tests pass.
- [ ] Step 5: Commit `fix(bootstrap): install and start Agent V2 from generated script (F-01)`.

### Task 2 (F-02, F-09): Manifest hub_config contract + validation

**Files:**
- Modify: `apps/api/src/provisioning/schemas.py` (add `HubConfig`, `Manifest.hub_config`)
- Modify: `apps/api/src/provisioning/routes.py` (`manifest()` builds hub_config from env)
- Modify: `apps/agent/agent_v2.py` (validate before write; commit hash after success)
- Test: `apps/api/tests/test_bootstrap_v2.py` (new class), `apps/api/tests/test_sprint3_integration.py`

**Interfaces:**
- Produces: `HubConfig(StrictModel)` with `hub_id, server_url, mqtt_host, mqtt_port` ONLY (no hub_key/mqtt_pass). `Manifest.hub_config: HubConfig | None`. API env: `ZTD_HUBBRAIN_HUB_ID`, `ZTD_HUBBRAIN_SERVER_URL`, `ZTD_HUBBRAIN_MQTT_HOST`, `ZTD_HUBBRAIN_MQTT_PORT`. Agent: `render_hubbrain_env` merges non-secret manifest values with secret env values (HUB_KEY, MQTT_PASS stay env-only on the Pi).

- [ ] Step 1: Failing tests — API returns `hub_config` when env set, omits when unset; manifest never contains `hub_key`/`mqtt_pass` keys; agent validates before write; manifest_hash only persisted after successful `_apply_hubbrain_config` (failed write keeps old hash).
- [ ] Step 2: Implement schema + route env-driven block.
- [ ] Step 3: Agent: `_apply_hubbrain_config` calls `hubbrain_adapter.validate_hub_config` on merged dict; only on success update state hash. Reorder save_state.
- [ ] Step 4: All tests pass.
- [ ] Step 5: Commit `feat(provisioning): non-secret hub_config in manifest; agent validates + commits hash after apply (F-02, F-09)`.

### Task 3 (F-03): Agent runtime dependencies

**Files:**
- Modify: `apps/agent/requirements.txt`

- [ ] Step 1: Failing test in `test_sprint3_integration.py` — parse requirements.txt, assert `httpx` and `paho-mqtt` present.
- [ ] Step 2: Add `httpx>=0.27,<0.29` to `apps/agent/requirements.txt`.
- [ ] Step 3: Pass + commit `fix(agent): add httpx runtime dependency (F-03)`.

### Task 4 (F-04, F-05, F-10, F-11): BFF session auth + dashboard alignment

**Files:**
- Create: `apps/api/src/routes/dashboard_bff.py` (login: POST body user+pass → nginx htpasswd file check via `ZTD_DASHBOARD_HTPASSWD` path env + issue signed session cookie; logout; `GET /api/dashboard/v2/provisioning/*` proxies to provisioning logic with admin bearer injected server-side)
- Modify: `apps/api/src/main.py` (include router)
- Modify: `nginx/default.conf` + `nginx/provisioning-v2.location.conf` (v2 location forwards Authorization; new `/api/dashboard/` location proxies to BFF)
- Modify: `ztd-dashboard/src/api/dashboardSessionApi.js` (create: login/logout/me)
- Modify: `ztd-dashboard/src/api/provisioningApi.js` (all calls go through BFF path `/api/dashboard/v2/provisioning`, send credentials: 'include', no Authorization header)
- Modify: `ztd-dashboard/src/utils/monitoringStatus.mjs` (`hubIdDisplay` reads `device.hub_id` from manifest hub_config echo in device status; align field names)
- Modify: `ztd-dashboard/src/views/DeploymentsView.vue` (wire `monitoringStateTone`, `bffRequiredNotice` into real UI states; remove dead imports or connect them)
- Test: `apps/api/tests/test_dashboard_bff.py` (new), `ztd-dashboard/tests/provisioningApi.test.mjs` (update paths), `ztd-dashboard/tests/monitoringStatus.test.mjs` (align field)

**Interfaces:**
- Produces: BFF endpoints `POST /api/dashboard/session`, `DELETE /api/dashboard/session`, `GET /api/dashboard/session` (me), `ANY /api/dashboard/v2/provisioning/{path}`. Session cookie `ztd_session`, HMAC-signed (itsdangerous), `HttpOnly; SameSite=Strict; Secure` (Secure flag only when `ZTD_COOKIE_SECURE=1`). Server-side env: `ZTD_DASHBOARD_HTPASSWD` (path), `ZTD_PROVISIONING_ADMIN_TOKEN` (already exists). `hubIdDisplay(device)` reads `device.hub_config?.hub_id ?? device.monitoring_hub_id ?? '—'`.

- [ ] Step 1: Failing BFF tests: login with valid htpasswd creds → 200 + Set-Cookie; wrong creds → 401; no htpasswd file configured → 503 fail-closed; proxied GET without session → 401; with session → 200 and upstream Authorization header is `Bearer <admin token>`; cookie flags correct; browser-visible surface has no admin token (assert `ZTD_PROVISIONING_ADMIN_TOKEN` never appears in any response body).
- [ ] Step 2: Implement BFF router; fail-closed if secret <32 chars or htpasswd missing.
- [ ] Step 3: nginx: v2 location forwards Authorization; add `/api/dashboard/` location (no basic auth, proxy to backend).
- [ ] Step 4: Dashboard client changes + test updates.
- [ ] Step 5: All Python + JS tests pass.
- [ ] Step 6: Commit `feat(security): BFF session boundary for dashboard provisioning (F-04, F-05); align monitoring identity fields (F-10, F-11)`.

### Task 5 (F-06): nginx TLS + auth forwarding verification

**Files:**
- Modify: `nginx/default.conf` (TLS server block on 443 with cert paths env-overridable, http→https redirect; keep port 80 server for redirect + ACME)
- Modify: `docker-compose.yml` (nginx ports 80+443; mount cert dir; mount `provisioning-v2.location.conf`)
- Test: `apps/api/tests/test_nginx_config.py` (new: parse and assert TLS block, redirect, Authorization forwarding, v2 location mounted)

- [ ] Step 1: Failing config tests (static assertions on the conf files).
- [ ] Step 2: Implement TLS server block + compose mounts.
- [ ] Step 3: Tests pass; commit `feat(nginx): TLS termination and Authorization forwarding for provisioning v2 (F-06)`.

### Task 6 (F-07): MQTT authentication

**Files:**
- Modify: `mosquitto/mosquitto.conf` (auth plugin config, per-topic ACLs)
- Create: `mosquitto/acl_file` (device write-only to its own topics; backend read-all; dashboard read-only telemetry topics)
- Modify: `docker-compose.yml` (mosquitto env for users, remove anonymous, keep 1883 internal + 9001 ws via nginx only)
- Modify: `nginx/default.conf` (`/mqtt` stays for dashboard)
- Test: `apps/api/tests/test_mosquitto_config.py` (new: static config assertions: `allow_anonymous false`, acl_file present, listener not published to host by default)

- [ ] Step 1: Failing config tests.
- [ ] Step 2: Implement mosquitto auth (password_file + acl_file; backend user; device user pattern documented for firmware `secrets.h`).
- [ ] Step 3: Tests pass; commit `feat(mqtt): authenticated MQTT with per-topic ACLs (F-07)`.

### Task 7 (F-08): Fresh-DB migration integration

**Files:**
- Create: `postgres/init/02-provisioning-v2.sql` (contents = 003 up migration)
- Modify: `docker-compose.yml` (no change needed; init dir already mounted)
- Test: `apps/api/tests/test_provisioning_postgres.py` (extend: fresh-init path applies both files)

- [ ] Step 1: Failing test — assert `02-provisioning-v2.sql` exists and equals `003_provisioning_v2.up.sql` content (drift guard).
- [ ] Step 2: Create the init file.
- [ ] Step 3: Pass; commit `fix(db): apply provisioning v2 schema on fresh init (F-08)`.

### Task 8 (F-12–F-16): Small fixes

**Files:**
- Modify: `apps/agent/agent_v2.py` (TLS: `verify=...` from `ZTD_TLS_CA_BUNDLE`, document IP-SAN cert requirement)
- Modify: `apps/api/tests/test_sprint3_integration.py` (imports: local `apps` package shim or conftest sys.path fix — make single-CWD collection work)
- Modify: `apps/api/src/provisioning/auth.py` (comment + constant `MIN_CREDENTIAL_ENTROPY_BITS`; no behavior change to existing hashes)
- Modify: `scripts/harden-nginx.sh` (non-interactive env-only mode, exit 2 if ADMIN_PASS unset and `NONINTERACTIVE=1`)
- Modify: `apps/api/src/routes/bootstrap.py` (cache-control already set; no change)
- Dashboard: run `git update-index --refresh` in a throwaway clone to document resolution (F-16) — NO, READ-ONLY rule: instead document the command in remediation report; the stat-cache self-heals on next write operation.

- [ ] Step 1: Failing/adjusted tests per item (TLS env consumed by agent loop via httpx `verify`; test collection works from repo root AND `apps/api`; harden-nginx `NONINTERACTIVE=1` fails with exit 2 when no password).
- [ ] Step 2: Implement.
- [ ] Step 3: Full suites pass; commit `fix: TLS trust env, test portability, credential-entropy docs, non-interactive hardening (F-12–F-15)`.

### Task 9: End-to-end runtime trace + remediation report

- [ ] Step 1: Run full pytest + node:test suites; capture outputs.
- [ ] Step 2: Compose the resolution matrix F-01–F-16 with file refs and test evidence.
- [ ] Step 3: Commit `docs: Sprint 3 remediation report`.
