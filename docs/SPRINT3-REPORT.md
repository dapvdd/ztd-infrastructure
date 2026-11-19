# Sprint 3 Report — Zero Touch Deployment: Edge Provisioning & Dual-Server Integration

**Branch:** `sprint3/edge-integration` (infrastructure worktree)  
**Branch:** `sprint3/edge-dashboard` (dashboard worktree)  
**Date:** 2026-11-11  
**Baselines preserved:** Sprint 1 (8ec4900), Sprint 2 (6b6977c) — unmodified  

---

## Summary

Sprint 3 extends the ZTD system to support:
- Raspberry Pi provisioning with dual-server identity (Provisioning VPS + Monitoring VPS)
- V2 Pi agent with authenticated HTTP, approval-gated manifest, and durable state
- HubBrain V5 integration adapter with secure credential management
- ESP/IoT node onboarding with identity mapping and whitelist management  
- Dashboard monitoring status display (dual-server column)
- 18-scenario integration test harness

**Final test counts:**
- Python (pytest): **124 passed, 2 skipped** (full suite including 36 baseline)
- Dashboard (node --test): **156 passed, 0 failed** (run from correct CWD)

---

## Commits

### Infrastructure (`sprint3/edge-integration`)

| SHA | Message |
|---|---|
| 797bde1 | feat(bootstrap): add ZTD identity and dual-server config fields |
| d59e5bd | feat(agent): V2 Pi agent with dual-server support and state tracking |
| 1247169 | feat(hubbrain): secure adapter for HubBrain V5 integration |
| 5b34127 | feat(esp): node identity adapter and whitelist provisioning |
| c1563d5 | test(integration): Sprint 3 E2E harness, 18 scenarios, 28 test cases |

### Dashboard (`sprint3/edge-dashboard`)

| SHA | Message |
|---|---|
| 26ee5f6 | feat(dashboard): dual-server provisioning status display |

---

## Tasks

### Task 1: Bootstrap Extension ✅

**Files changed:** `apps/api/src/routes/bootstrap.py`, `apps/api/tests/test_bootstrap_v2.py`

Added 4 optional fields to `BootstrapRequest`:
- `ztd_device_id` → `ZTD_DEVICE_ID` in generated script
- `provisioning_url` → `PROVISIONING_URL`
- `monitoring_hub_id` → `MONITORING_HUB_ID`
- `monitoring_url` → `MONITORING_URL`

All fields pass through `_check_text` (control char rejection) and `shlex.quote` (shell injection prevention). 9 tests.

### Task 2: V2 Pi Agent ✅

**Files created:** `apps/agent/agent_v2.py`, `apps/agent/agent_v2_state.json.example`, `apps/agent/ztd-agent-v2.service`

Pure-function core (fully tested, 21 tests):
- `load_state` / `save_state` — durable JSON state with 0o600 permissions
- `backoff_seconds` — exponential backoff with jitter and cap
- `compute_manifest_hash` — SHA-256, key-sorted, deterministic
- `should_fetch_manifest` — approval gate: APPROVED + not expired + REGISTERED
- `render_hubbrain_env` — HubBrain .env content renderer
- `build_registration_payload` — registration JSON builder

Imperative shell (`run_agent_loop`) is `# pragma: no cover` — requires real HTTP.

### Task 3: HubBrain Integration Adapter ✅

**Files created:** `apps/agent/hubbrain_adapter.py`, `apps/agent/hubbrain.env.example`

- `validate_hub_config` — validates all required keys, server_url must be https://, mqtt_port 1–65535
- `write_hubbrain_env` — atomic write with 0o600 permissions
- `render_systemd_dropin` — EnvironmentFile= drop-in generator
- `issue_hubgate_credentials` — **explicitly raises NotImplementedError** (auto-issuance blocked)

15 tests.

#### Design decision: HubGate credential issuance blocked

The Monitoring team's `POST /api/hubs/pair` endpoint:
1. Requires `HUB_BOOTSTRAP_KEY` for authentication
2. Returns HTTP 202 (pending) — does NOT issue HUB_ID/HUB_KEY to ZTD
3. HUB_ID and HUB_KEY must be manually provisioned by a Monitoring VPS admin

This is enforced by `issue_hubgate_credentials` always raising `NotImplementedError` with a clear message directing operators to the manual process.

### Task 4: ESP/IoT Node Provisioning Adapter ✅

**Files created:** `apps/agent/esp_node_adapter.py`, `docs/ESP_NODE_PROVISIONING.md`

- `mac_to_node_id` — MAC → lowercase hex (e.g. `AA:BB:CC:DD:EE:FF` → `aabbccddeeff`)
- `mac_to_dev_name` — firmware-compatible DEV_NAME (e.g. `TS-EEFF`)
- `build_node_record` — full identity record with firmware-matching MQTT topic
- `build_whitelist_entry` — HubBrain whitelist entry format
- `validate_whitelist` — rejects same MAC on two different gateways (collision prevention)

15 tests.

#### Design decision: ESP wireless zero-touch onboarding NOT claimed

The WEMOS_TS firmware uses `secrets.h` compiled at flash time. WiFi SSID/password and MQTT credentials cannot be delivered over-the-air. Physical flashing is required for initial setup. ZTD covers gateway-side identity mapping only.

### Task 5: Dashboard Extension ✅

**Files created:** `src/utils/monitoringStatus.mjs`, `tests/monitoringStatus.test.mjs`  
**Files modified:** `src/views/DeploymentsView.vue`

Pure helpers for dual-server status display:
- `classifyDualServerStatus` — REGISTERED+APPROVED+not-expired → linked/connected
- `monitoringStateLabel` / `monitoringStateTone` — UI labels (Indonesian)
- `hubIdDisplay` — safe hub_id display with em-dash fallback
- `bffRequiredNotice` — BFF limitation notice

18 Node.js tests. Device dropdown now shows monitoring status alongside approval status.

#### Design decision: Dashboard BFF authentication limitation

The admin token for `/api/v2/provisioning/devices` cannot be safely browser-held without a server-side session layer. The `bffRequiredNotice()` function documents this limitation. Status display works for environments where the token is provided via environment (dev mode).

### Task 6: Integration Test Harness ✅

**File created:** `apps/api/tests/test_sprint3_integration.py`

18 scenarios, 28 test cases covering the entire Sprint 3 surface end-to-end (locally isolated, no network):

| # | Scenario | Tests |
|---|---|---|
| 1 | Bootstrap ZTD fields in script | 1 |
| 2 | Bootstrap shell injection prevention | 1 |
| 3 | Agent state defaults | 1 |
| 4 | Agent state round-trip | 1 |
| 5 | Agent backoff cap | 2 |
| 6 | Manifest hash stability | 2 |
| 7 | Approval gate: permits | 1 |
| 8 | Approval gate: pending | 1 |
| 9 | Approval gate: expired | 1 |
| 10 | HubBrain env file | 2 |
| 11 | HubBrain auto-issuance blocked | 1 |
| 12 | HubBrain config validation | 1 |
| 13 | ESP MAC normalization | 3 |
| 14 | ESP whitelist format | 2 |
| 15 | ESP cross-gateway duplicate | 2 |
| 16 | Provisioning API: enroll→register→status | 1 |
| 17 | Manifest blocked without approval | 1 |
| 18 | Dual-server status classification | 4 |

### Task 7: Security Review ✅

---

## Security Review

### 1. Shell injection in bootstrap script ✅ RESOLVED

All user-supplied values pass through `shlex.quote()` before entering the generated bash script. Test `test_shell_injection_prevention_in_new_fields` verifies that `$(rm -rf /)` is wrapped in single quotes.

### 2. Config file permission leak ✅ RESOLVED

`agent_v2.save_state()` uses `os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)` before `os.replace()`. State file (containing device_id and manifest hash) is owner-readable only.

### 3. HubBrain .env credential exposure ✅ RESOLVED

`hubbrain_adapter.write_hubbrain_env()` applies identical `chmod 0o600` pattern. HUB_KEY and MQTT_PASS are never logged. Example file `.env.example` does not contain real credentials.

### 4. Approval expiry race ✅ ACCEPTABLE

The manifest endpoint re-checks `approval_expires_at` on every request (server-side, in `manifest()` route). There is no long-polling; each HTTP request re-evaluates approval. Race window is the HTTP round-trip time only.

### 5. Duplicate node IDs across gateways ✅ RESOLVED

`esp_node_adapter.validate_whitelist()` explicitly raises `ValueError` on same MAC registered to two different gateways, with a clear error message naming both gateway IDs.

### 6. Control characters in bootstrap fields ✅ RESOLVED

`_check_text()` rejects any character with `ord(c) < 32 or ord(c) == 127`. All 8 user-controlled fields (original + 4 new Sprint 3 fields) are checked.

### 7. HubBrain auto-issuance permanently blocked ✅ RESOLVED

`issue_hubgate_credentials()` always raises `NotImplementedError`. The docstring names the specific endpoint that does not support automated issuance and directs operators to the manual process.

### 8. Admin token browser exposure ✅ DOCUMENTED

`bffRequiredNotice()` in `monitoringStatus.mjs` explicitly labels the BFF requirement. The dashboard does not store or forward admin tokens. The notice appears when status cannot be fetched.

---

## Known Limitations

1. **ESP wireless onboarding**: Physical flashing required for each ESP node. Cannot be automated without firmware changes (AP mode provisioning not implemented in WEMOS_TS.ino).

2. **HubGate credential issuance**: Manual step — Monitoring VPS admin must provision HUB_ID/HUB_KEY and inject into `/etc/ztd/agent.env`.

3. **Dashboard BFF layer**: Admin token display requires a Backend-for-Frontend layer. Without it, the admin must supply the token to the development environment directly.

4. **No real HTTP tests**: `run_agent_loop()` is marked `pragma: no cover` — testing requires a live Provisioning VPS or mock HTTP server (httpx.Client mock). Hardware integration tests are out of scope for this sprint.

---

## Architecture Notes

```
Fresh Pi
   │
   ▼ bootstrap-pi.sh (generated by /api/v1/bootstrap/raspberry)
   │  ZTD_DEVICE_ID, PROVISIONING_URL, MONITORING_HUB_ID, MONITORING_URL
   │
   ▼ agent_v2.py (systemd service: ztd-agent-v2.service)
   │  POST /api/v2/provisioning/register  → HTTP Basic (device_id:password)
   │  GET  /api/v2/provisioning/status    → poll approval_status
   │  GET  /api/v2/provisioning/manifest  → requires APPROVED + not expired
   │
   ├──▶ Provisioning VPS (FastAPI)
   │      approval by Monitoring VPS via PUT /integrations/monitoring/.../approval
   │
   └──▶ HubBrain V5 (via hubbrain_adapter.py)
         writes /etc/ztd/hubbrain.env (chmod 600)
         reads: HUB_ID, HUB_KEY, SERVER_URL, MQTT_HOST/PORT/USER/PASS (manual)
         MQTT topic: hs109rs/ts/data  ◀── ESP8266 nodes (TS sensor)
```
