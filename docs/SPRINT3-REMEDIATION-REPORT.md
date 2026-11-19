# Sprint 3 Remediation Report — F-01 through F-16

**Date:** 2026-11-12
**Branches:** `sprint3-remediation/edge-integration` (infrastructure), `sprint3-remediation/edge-dashboard` (dashboard)
**Baselines preserved:** infra tip `7931ffb` (contains earlier `8ec49007`), dashboard tip `26ee5f6` (contains earlier `6b6977cd`)

---

## Verdict: PARTIAL

All 16 findings are remediated **in code with passing tests** on the remediation
branches. Nothing is pushed, merged, deployed, or restarted. The verdict is
PARTIAL — not READY — because four acceptance gates require environments this
Windows dev host cannot provide (real PostgreSQL, real Mosquitto container, real
Linux systemd, real TLS handshake). Those gates have static/config-level
evidence plus documented runbooks, not runtime evidence.

---

## Commits

### Infrastructure (`sprint3-remediation/edge-integration`)
| Commit | Finding | Summary |
|---|---|---|
| `a60d76e` | F-01 | Bootstrap installs and starts Agent V2 from generated script |
| `b4b2f29` | F-02, F-09 | Non-secret `hub_config` in manifest; agent validates + commits hash after apply |
| `a8e4c8f` | F-03 | `httpx` declared in agent runtime requirements |
| `e2e44b8` | F-04, F-05 | BFF session boundary for dashboard provisioning |
| `79d850d` | F-04, F-05 | nginx routes `/api/dashboard/` to the backend |
| `fa96156` | F-06 | nginx TLS termination, HTTPS redirect, cert mounts; auth forwarding verified |
| `16e2f92` | F-07 | Authenticated MQTT with per-topic ACLs, no host port exposure |
| `86b15c0` | F-08 | Fresh-DB init applies provisioning v2 schema, with drift guard |
| `3a006c7` | F-12–F-15 | TLS trust env, dual-CWD test imports, entropy docs, non-interactive hardening |

### Dashboard (`sprint3-remediation/edge-dashboard`)
| Commit | Finding | Summary |
|---|---|---|
| `a60b9a3` | F-04, F-05, F-10, F-11 | Dashboard uses BFF session; monitoring identity aligned; dead helpers wired |

---

## Resolution matrix

| # | Finding (severity) | Resolution | Key files | Test evidence |
|---|---|---|---|---|
| F-01 | Bootstrap never installed Agent V2 (P0) | Generated script now writes `/etc/ztd/agent.env`, enables `ztd-agent-v2` systemd unit, guarded by `[ -z "$ZTD_DEVICE_ID" ]` | `apps/api/src/routes/bootstrap.py` | `test_bootstrap_v2.py::TestBootstrapInstallsAgentV2` — 7 tests (env fields, unit enable, guard, no legacy touch, `bash -n` syntax — bash-subprocess skipped on Windows) |
| F-02 | Unsafe manifest contract; Monitoring secrets in manifests (P0) | New `HubConfig` StrictModel: `hub_id, server_url, mqtt_host, mqtt_port` ONLY. `Manifest.hub_config: HubConfig \| None`, built from 4 non-secret env vars; partial config → None | `apps/api/src/provisioning/schemas.py`, `routes.py` | `TestScenario19_ManifestHubConfig` — includes-when-env-set, omits-when-unset, **never-contains-secrets** (asserts `SHOULD-NOT-APPEAR` probe env values absent) |
| F-03 | Missing agent runtime deps incl. httpx (P0) | `httpx>=0.27,<0.29` added; loop imports guarded | `apps/agent/requirements.txt` | `TestScenario21_AgentRequirements` (declared + importable) |
| F-04 | Provisioning admin token exposed to browser JS (P0) | BFF: `POST/GET/DELETE /api/dashboard/session` + `ANY /api/dashboard/v2/provisioning/{path}`. Admin bearer injected **server-side**; cookie `ztd_session` (itsdangerous HMAC, HttpOnly, SameSite=strict, 8 h TTL); fail-closed 503 | `apps/api/src/routes/dashboard_bff.py`, `main.py`; `ztd-dashboard/src/api/dashboardSessionApi.js` (new), `provisioningApi.js` (repointed, `credentials:'include'`, no auth header) | 14 BFF tests incl. `test_admin_token_never_in_any_response_body`, `test_proxy_requires_session`, `test_upstream_receives_admin_bearer`; dashboard: `provisioningApi.test.mjs` asserts BFF prefix + no Authorization header; `dashboardSessionApi.test.mjs` 6 tests |
| F-05 | Dashboard provisioning workflow unusable (P1) | Full login/logout/session-check state machine in `DeploymentsView.vue` (session gate, login form, logout, explicit 401/503 messages); `bffRequiredNotice` wired; `provisioningApi` sends cookie credentials | `ztd-dashboard/src/views/DeploymentsView.vue` | `monitoringStatus.test.mjs` (notice is actionable login message, no token mention); `dashboardSessionApi.test.mjs`; Vue template asserts in `HomeView/DeploymentsView` tests still pass |
| F-06 | nginx TLS/auth misintegration; bearer over plaintext HTTP (P1) | Port 80 → 301 HTTPS (ACME path excepted); 443 ssl listener (TLSv1.2/1.3, HSTS); v2 location forwards `Authorization $http_authorization`; `/api/dashboard/` blanks it; compose publishes 443, mounts certs + v2 snippet | `nginx/default.conf`, `docker-compose.yml`, `nginx/provisioning-v2.location.conf` (existing) | `test_nginx_config.py` — 10 tests (TLS listener, 301, cert paths, protocol versions, v2 forwards auth, BFF blanks auth, compose 443 + mounts) |
| F-07 | MQTT anonymous + exposed (P1) | `allow_anonymous false`, `password_file`, `acl_file` (backend rw `#`; gateway pattern write own status/sensors, read own config; dashboard read-only telemetry); ports `expose` only (no host publish); authenticated healthcheck | `mosquitto/mosquitto.conf`, `mosquitto/acl` (new), `README-mqtt-auth.md` (new runbook), `docker-compose.yml` | `test_mosquitto_config.py` — 11 tests (anonymous false, files wired + mounted, ACL rules, ports not on 0.0.0.0, healthcheck creds, ESP compatibility doc exists) |
| F-08 | Migration 003 missing from fresh init (P1) | `postgres/init/02-provisioning-v2.sql` (byte-identical copy of 003 up) runs on first boot; drift guard pins equality | `postgres/init/02-provisioning-v2.sql` (new) | 3 tests in `test_provisioning_postgres.py` (exists, byte-identical to migration, creates all 4 v2 tables). Real-DB tests skip without `ZTD_TEST_POSTGRES_URL` |
| F-09 | HubBrain config written unvalidated; hash persisted before apply (P2) | `_apply_hubbrain_config` merges manifest addressing + env secrets, `validate_hub_config` BEFORE write, atomic tmp+replace; loop applies FIRST, persists `manifest_hash` only on success | `apps/agent/agent_v2.py` | `TestScenario20_FailedApplyPreservesState` — failed apply leaves old hash/revision; `test_validate_blocks_secrets_missing` |
| F-10 | Dashboard monitoring identity fields misaligned (P2) | `hubIdDisplay` reads `device.hub_config?.hub_id` first (Task 2 schema echo), falls back `monitoring_hub_id`, `hub_id` | `ztd-dashboard/src/utils/monitoringStatus.mjs` | `monitoringStatus.test.mjs` — priority, fallbacks, em-dash cases |
| F-11 | Dead UI utilities (P2) | `monitoringStateTone` + `bffRequiredNotice` + `hubIdDisplay` wired into `DeploymentsView.vue` (session badge tone, login-notice message, manifest grid hub row); imports live | `ztd-dashboard/src/views/DeploymentsView.vue` | All helper tests pass; Vue tests unaffected; no unused imports remain from monitoringStatus |
| F-12 | TLS trust for private VPS addresses (P2) | `ZTD_TLS_CA_BUNDLE` env → httpx `verify` on every loop call; missing file fails fast; verify stays ON (never False); IP-SAN requirement documented in-code | `apps/agent/agent_v2.py` | `TestScenario22_AgentTlsTrust` — 4 tests (contract: no verify=False, env consumed, SAN documented) |
| F-13 | Integration-test import portability (P2) | `test_sprint3_integration.py` resolves `agent_v2` by explicit path + `apps.agent` shim, so pytest collects from repo root AND `apps/api` with no env vars | `apps/api/tests/test_sprint3_integration.py` | Verified: 177→183 pass from both CWDs, zero `PYTHONPATH` needed |
| F-14 | Credential hashing assumptions (P3) | `MIN_CREDENTIAL_ENTROPY_BITS = 128` constant (used by token_guard); in-code review note: SHA-256 acceptable for server-GENERATED 256-bit passwords, KDF REQUIRED if ever human passwords; existing credentials unaffected | `apps/api/src/provisioning/auth.py` | `test_hardening_contracts.py` — constant defined/used, hash backward-compatible (SHA-256 pin) |
| F-15 | nginx hardening not automation-safe (P3) | `NONINTERACTIVE=1` (or no TTY) + missing `ADMIN_PASS` → `die2` **exit 2** before any file touch; interactive prompt unchanged | `scripts/harden-nginx.sh` | Real bash subprocess: exit 2 + ADMIN_PASS message + zero file mutations in scratch dir; env-pass mode proceeds (DRY_RUN) |
| F-16 | Dashboard index/stat-cache inconsistency (P3) | Resolved non-destructively: Phase-1 audit re-ran `git status`/diff on all 49 paths — 0 content mismatches; stat-cache self-heals on next write; command documented below, no git history ops | (no source change) | Audit record in acceptance review; `git status` clean on dash worktree now |

**F-16 operator note:** if the staleness reappears: `git update-index --refresh`
(or `git status` after any write op). No `git reset`/`checkout` needed; content
was never divergent.

---

## Test evidence summary

| Suite | Command (CWD) | Result |
|---|---|---|
| Infra full suite | `python -m pytest apps\api\tests -q` from infra root (no env vars needed) | **183 passed, 3 skipped** (2 opt-in real-PostgreSQL + 1 `bash -n` on Windows) |
| Dashboard full suite | `node --test "tests/*.test.mjs"` from `ztd-dashboard` | **168 passed, 0 failed** (baseline 138 → sprint3 156 → +12 new) |
| Baseline integrity | infra at `8ec49007`, dash at `6b6977cd` | Untouched (branch history shows them in ancestry; no rewrites) |

New tests added: ~60 (bootstrap v2, hub_config contract, BFF 14, nginx 10,
mosquitto 11, F-08 drift 3, TLS trust 4, hardening 6, dashboard session 6 +
identity 5 + client 2).

### Falsification against original Sprint 3 code
Each remediation was written TDD-first: the failing state was observed before
implementation — bootstrap tests failed on missing `install_ztd_agent_v2`
section; manifest tests failed on missing `hub_config`; BFF tests failed with
module-absent (13 failed / 1 passed) then on apr1 verification (401s) then on
proxy 500; nginx tests failed 7 on TLS; mosquitto tests failed 8; F-08 tests
failed 3; F-15 exited 1 before the fix. All now pass — meaning the new tests
**fail against the original code** by construction.

---

## End-to-end runtime trace (design + unit-level evidence)

1. **Bootstrap (Pi operator)** — admin fills form → `POST /api/v1/bootstrap/raspberry`
   (behind basic auth + now TLS) → generated script writes
   `/etc/ztd/agent.env` (device identity, PROVISIONING_URL, MONITORING_HUB_ID,
   MONITORING_URL), enables `ztd-agent-v2` (F-01).
2. **Agent registration** — `agent_v2.run_agent_loop` POSTs `/register` with
   device Basic auth over TLS (verify per `ZTD_TLS_CA_BUNDLE`, F-12) →
   poll `/status` → on APPROVED fetch `/manifest`.
3. **Manifest** — server returns manifest + `hub_config`
   (hub_id, server_url, mqtt_host, mqtt_port — NO secrets, F-02).
4. **HubBrain handoff** — agent merges non-secret manifest values with
   env-secret `ZTD_HUB_KEY`/`ZTD_MQTT_PASS`, validates via
   `hubbrain_adapter.validate_hub_config`, writes `/etc/ztd/hubbrain.env`
   atomically, THEN persists new `manifest_hash` (F-09). Failed apply →
   previous state preserved.
5. **Dashboard** — user opens Deployments → `GET /api/dashboard/session`
   introspects cookie (F-04) → login form posts htpasswd creds →
   `ztd_session` HttpOnly cookie issued → provisioning calls go to
   `/api/dashboard/v2/provisioning/*` with `credentials: 'include'` and **no**
   Authorization header → BFF validates session, injects `Bearer <admin>`
   server-side, forwards in-process → response bodies never contain the token.
6. **nginx** — 80 → 301 → 443 TLS; `/api/dashboard/` blanks client
   Authorization; `/api/v2/provisioning/` forwards it (device Basic / admin
   bearer reach the backend only over TLS, F-06).
7. **MQTT** — broker refuses anonymous (F-07); backend uses `ztd-backend` user;
   gateway agents use `gw-<id>` pattern ACLs; dashboard reads telemetry via
   nginx `/mqtt` WS.
8. **Fresh DB** — postgres entrypoint runs `01-schema.sql` +
   `02-provisioning-v2.sql` on first boot → API starts with v2 tables present
   (F-08).

---

## Remaining external dependencies (documented blockers — not faked)

1. **Real PostgreSQL verification** — `test_provisioning_postgres.py` concurrency
   + downgrade tests skip without `ZTD_TEST_POSTGRES_URL`. Static drift-guard
   covers the fresh-init contract; the SQL itself was verified in the original
   acceptance review. Needs a disposable CI Postgres to execute.
2. **Real Mosquitto container verification** — ACL semantics (deny/allow
   matrix) and the authenticated healthcheck need `docker compose up ztd-mqtt`
   with an operator-generated `mosquitto/passwd`. Runbook:
   `mosquitto/README-mqtt-auth.md`. Not run here (no Docker on host).
3. **Real Linux systemd execution** — F-01's generated script and
   `ztd-agent-v2` enable need an isolated Linux VM/LXC; `bash -n` syntax check
   runs in CI, full install verification does not run on Windows.
4. **Real TLS handshake** — cert issuance (`nginx/certs/*.pem` or ACME) and an
   end-to-end HTTPS request need the VPS or a container run; config-level tests
   pass, runtime handshake unverified here.
5. **Monitoring credential issuance** — stays a manual blocker per scope:
   HUB_KEY/MQTT_PASS are issued by Monitoring operators out-of-band and set as
   Pi-side env (`ZTD_HUB_KEY`, `ZTD_MQTT_PASS`). No API endpoint fakes this.
6. **Physical ESP onboarding** — stays flash-time `secrets.h` on the gateway's
   local broker; zero-touch wireless onboarding is out of scope (documented in
   `.superpowers/sdd/progress.md` ruling and `docs/ESP_NODE_PROVISIONING.md`).

---

## Security regression results

- Full infra suite: 183 passed / 3 skipped — includes all Sprint 1–2 regression
  tests (bootstrap injection prevention, approval gates, hubbrain validation,
  ESP adapter contracts) plus the new security tests.
- Full dashboard suite: 168 passed / 0 failed — includes "page never stores or
  sends an admin bearer token" assertions across HomeView, DeploymentsView,
  ModulesView.
- Negative security tests: wrong-password login 401; unknown user 401; missing
  secret 503; short secret 503; missing htpasswd 503; no-session proxy 401;
  cross-device manifest 403; manifest blocked without approval 403/401;
  injection-safe bootstrap (shlex quoting) preserved.
- Nothing pushed, merged, deployed. Baselines intact.
