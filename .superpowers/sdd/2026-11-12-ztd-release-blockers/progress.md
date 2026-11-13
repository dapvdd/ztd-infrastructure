# SDD ledger — ZTD Full Release Blocker Remediation Sprint (2026-11-12)

Authoritative baselines: infra `53a5bc6`, dashboard `beb86ab`.
Sprint branches: `sprint4/blocker-remediation` (both repos).
Original dashboard checkout with 48 modified files at
`Development/ztd-preserved-20261111/dashboard` — untouched.

## Phase checklist
- [x] P1 code: vite changeOrigin removed (dashboard c584f05); CSRF intact
- [x] P1 evidence: Chromium E2E vs staging nginx 8443 — 14 PASS / 0 FAIL
      (see "P1 Chromium E2E" below); frontend API sends snake_case already
- [x] P2 code: argv-leak paths removed (infra 39c83e8) — keyfile-load mechanism,
      psk-flags fallback, pip abort-before-service; suite 233/3
- [ ] P2 evidence: bash -n on Linux staging + full installer acceptance there
- [x] P5 MQTT hardening verified end-to-end in staging (infra b8f335d) — see
      evidence log "P5 MQTT" below
- [x] P4 nginx + BFF runtime validation (staging) — see "P4 runtime" below
- [ ] P6 DB migration rehearsal
- [ ] P7 rollback rehearsal
- [ ] P8 final acceptance + verdict

## Evidence log

### Recon
- Windows host: no Docker, no WSL. VirtualBox VMs exist but powered off.
- VPS: production compose RUNNING; observed read-only (see recon notes above).
- Staging plan: separate compose project on VPS — new ports/networks/volumes,
  test creds, no production contact. Rollback rehearsal uses staging data only.

### Baseline verification (before changes)
- infra: `python -m pytest apps/api/tests -q` → 231 passed, 3 skipped
- dashboard: `node --test tests/*.test.mjs` → 174 pass, 0 fail
- `git status` clean on both sprint worktrees before first commit

### Commits
- dashboard `c584f05` fix(vite): preserve browser Host/Origin through dev proxy
  (P1 code fix; CSRF/disabled-origin checks preserved)
- infra `39c83e8` fix(installer): argv secret leak removal, keyfile workflow
- infra `a459f0b` fix(nginx): provisioning snippet under 443 via /etc/nginx/snippets
- infra `f392451` fix(compose): service-internal hostnames for staging
- infra `6d0e6f9` fix(compose): staging host ports 8080/8443
- infra `096dc3b` fix(config): pin postgresql+psycopg2 dialect
- infra `3cc21b9` fix(compose): authenticated MQTT healthcheck env
- infra `b8f335d` fix(mqtt): ACL least-privilege, listener auth, LF configs,
  healthcheck creds (suite 245 passed / 2 skipped)

### P5 MQTT (staging, project ztd-staging, 2026-11-12)
Defects found live and fixed in `b8f335d`:
1. mosquitto `pattern write hs109rs/#` applies to EVERY user (mosquitto
   semantics), silently granting the read-only dashboard user write access.
   Replaced with explicit per-gateway `user gw-<id>` blocks + template.
2. Backend listener connected anonymously (no username_pw_set) → refused
   once allow_anonymous false took effect. MQTT_USER/MQTT_PASS now flow
   .env → config.py → mqtt_listener.username_pw_set → compose env.
3. mosquitto.conf + acl had CRLF endings: mosquitto 2.1.2 parses values
   literally ("false\r") so directives silently fail. LF enforced via
   .gitattributes (verified in committed blobs: 0 CR bytes).
4. Healthcheck creds (MQTT_HEALTH_*) drifted from listener creds; healthcheck
   now reuses MQTT_USER/MQTT_PASS. `topic readwrite #` never matches
   $SYS/# (MQTT wildcard rule), so ACL adds `topic read $SYS/#`.
5. mosquitto 2.x passwd file must be owned by UID 1883 mode 0600/0640 —
   world-readable is refused (documented in README-mqtt-auth.md §2).

Acceptance matrix results (staging broker ztd-stage-mqtt):
- anonymous connect → rc=5 "Connection Refused: not authorised" ✅
- backend (ztd-backend) pub iot/device/.../register + hs109rs/ts/data → rc=0 ✅
- backend sub $SYS/broker/version → rc=0 (ACL grant works) ✅
- gateway pub own status/register (gw-raspi-stage-01) → rc=0 ✅
- gateway pub FOREIGN gw id status → v5 reason "Not authorized" ✅
- gateway sub foreign config → denied (no delivery) ✅
- dashboard pub hs109rs/ts/data → "Warning: Publish 1 failed: Not authorized."
  and subscriber capture PROVES no delivery (denycheck-1037019) ✅
- dashboard sub hs109rs/# (as backend publishes) → received ✅
- wrong password / unknown user → rc=5 refused ✅
- broker healthcheck: HEALTH=healthy (was unhealthy on stale creds) ✅

End-to-end through the real backend listener (staging DB ztd_stage):
- MQTT register (gw publishes own id) → devices row created (hostname
  stage-gateway, ONLINE) ✅
- MQTT heartbeat → last_seen bumped ✅
- MQTT metrics (correct v1 schema) → telemetry row kind=device_metrics ✅
- invalid metrics payload correctly rejected+logged by backend ✅
- $SYS/broker/subscriptions/count = 5 (backend's 5 topic subs) ✅

Test-idempotency note: v3.1.1 publishes that violate the ACL are dropped
silently with PUBACK rc=0 — ACL denial visibility requires MQTT v5 or
QoS1-with-log inspection (documented in README §6).

### P4 runtime (staging, 2026-11-12/13)
Static gate (p4_results.txt): nginx -t OK; :8080→301 https; :8443→200
TLSv1.3 self-signed CN=ztd-staging.local; /api/v2/provisioning unauth→401;
/api/v1/bootstrap unauth→401.

Defects found live, fixed and re-verified through the real BFF flow:
1. `b2e6b3a` compose: htpasswd never mounted into backend → POST
   /api/dashboard/session 503 "authentication service not configured".
2. `c61543e` deps: itsdangerous missing in runtime image (lazily imported
   in _signer) → login 500 ModuleNotFoundError. requirements.txt + import-
   coverage regression test (test_bff_dependencies.py). VPS has no PyPI
   access (connection reset) — wheel 2.2.0 downloaded locally, scp'd,
   docker cp + pip install inside ztd-stage-backend.
3. `ef7e8dc` nginx: /api/dashboard/ proxied Host as $host (portless) →
   same-origin check saw Host 127.0.0.1 vs Origin …:8443 → 403 on every
   same-origin POST. Now $http_host for the BFF location only.
4. `e7e3f8d` bootstrap: agent_payload() hard-coded parents[3]/agent →
   FileNotFoundError /agent/agent_v2.py in container (mount is /app/agent).
   New _agent_root(): ZTD_AGENT_DIR env override + layout probing; .env
   gained ZTD_AGENT_DIR=/app/agent.
5. `d7806f4` bff: provisioning proxy used fastapi.testclient (httpx is a
   test-only dep) → 500 in runtime. Dual path: TestClient in tests,
   stdlib urllib loopback (ZTD_INTERNAL_API_URL, default 127.0.0.1:8000)
   at runtime; URLError → clean 502.
6. `29fc662` bff: proxy dropped the request body → enrollment POST 422
   (Enrollment.device_id missing). Body + Content-Type now forwarded.
7. `a401f53` bff: blocking urllib inline in async proxy deadlocked the
   event loop (loopback shares the same process) → hang/500. Now
   run_in_threadpool.
8. `53f6e67` bff: runtime image raises ImportError (not RuntimeError) on
   the testclient probe → fallback never engaged. Both caught.

Final BFF flow evidence (p4k/p4l_results.txt, all through nginx :8443):
login 200 {authenticated:true,username:staging}; GET /session 200;
POST /bootstrap/raspberry 200 text/x-shellscript 761965 B with markers
install_ztd_agent_v2 ×2, ztd-agent-v2.service ×4, PAYLOAD_B64+SHA256,
zero legacy secrets.h, zero Wi-Fi PSK, zero admin-token echo; evil
Origin with valid session → 403; no session → 401; wrong password →
401; logout 204 then 401; GET /api/dashboard/v2/provisioning/devices
via BFF → 200 []; /health {status:healthy,database:connected}.

### P1 Chromium E2E (Playwright 1.64.1 headless vs staging nginx, 2026-11-13)
14 PASS / 0 FAIL (p1_results.txt + screenshots 01–03):
- SPA loads; session gate shows login form; wrong password → explicit
  "Username atau password dashboard salah."; correct login → badge
  "Sesi: staging".
- Enrollment via UI (window.confirm auto-accepted): unique raspi-e2e-*
  → one-time password displayed once (len 43).
- Bootstrap form (Wired): Device Name/Pi Host/Pi Username/Room/MQTT
  broker + ZTD Device ID raspi-e2e-check → download event
  bootstrap-e2e-check.sh 761969 B; content asserts: install_ztd_agent_v2,
  ztd-agent-v2.service, PAYLOAD_B64+PAYLOAD_SHA256, no secrets.h, hub
  disposition embedded; sha256 head ea22904cb97efc07.
- Logout → login form returns; unauth POST download via API → 401.
- Backend log greps: 0× "500 Internal" in the E2E window.
Dashboard unit suite after E2E fixes: 174/174 pass; vite build OK.
Known residual (documented, not a blocker for staging): POST
/api/dashboard/session does not run _check_csrf (login-with-evil-origin
returns 200 when password is valid). Login-CSRF hardening is queued as
follow-up; session-boundary and download CSRF checks verified working.
