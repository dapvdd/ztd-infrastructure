# SDD ledger — ZTD Full Release Blocker Remediation Sprint (2026-11-12)

Authoritative baselines: infra `53a5bc6`, dashboard `beb86ab`.
Sprint branches: `sprint4/blocker-remediation` (both repos).
Original dashboard checkout with 48 modified files at
`Development/ztd-preserved-20261111/dashboard` — untouched.

## Phase checklist
- [x] P1 code: vite changeOrigin removed (dashboard c584f05); CSRF intact
- [ ] P1 evidence: Chromium E2E — 200 download, cross-site 403, unauth 401, Agent V2 content, no secrets
- [x] P2 code: argv-leak paths removed (infra 39c83e8) — keyfile-load mechanism,
      psk-flags fallback, pip abort-before-service; suite 233/3
- [ ] P2 evidence: bash -n on Linux staging + full installer acceptance there
- [x] P5 MQTT hardening verified end-to-end in staging (infra b8f335d) — see
      evidence log "P5 MQTT" below
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
