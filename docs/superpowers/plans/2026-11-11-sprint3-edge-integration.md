# Sprint 3 — Full Edge Provisioning & Dual-Server Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, chosen by user).

**Goal:** Extend ZTD to provision Raspberry Pi gateways, integrate ESP/IoT nodes, and connect each Pi to both Provisioning VPS and Monitoring VPS without replacing any working Sprint 1/2 behavior.

**Architecture:**  
Fresh Pi → existing bootstrap script (network+SSH) → ZTD Agent v2 (authenticated HTTP, approval-gated manifest) → HubBrain (Monitoring MQTT bridge) → ESP8266/ESP32 → MQTT → HubGate.  
Two independent logical server connections over a single physical network interface (Tailscale VPN or LAN).

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, pydantic v2, pytest, bash, systemd, paho-mqtt, Vue 3

**Spec:** `apps/api/src/provisioning/routes.py`, `apps/api/src/provisioning/schemas.py`, `apps/api/src/provisioning/auth.py`, monitoring reference at `C:/Users/user/AppData/Local/Temp/opencode/sprint3-monitoring-reference`

## Global Constraints

- Preserve Sprint 1 baseline exactly: 36 passed, 2 skipped before Sprint 3 changes
- Never modify Monitoring team's repository clone
- Never invent missing API endpoints; block unsupported automated HubGate credential issuance
- device_id pattern: `^raspi-[a-z0-9-]{3,20}$`; hostname must match device_id on /register
- Module repo must be in `ZTD_MODULE_REPOSITORIES` allowlist; commit must be 40-hex
- ModuleConfiguration only field: `sample_interval_seconds: int (1..86400)`; no secrets
- Approval required: APPROVED + not expired + registered → manifest; PENDING/REJECTED/REVOKED → 403
- HubBrain auth: env `HUB_ID`, `HUB_KEY`, headers `X-Hub-ID` / `X-Hub-Key`; strict `ALLOW_INSECURE_DEV_KEYS=false` in production
- MQTT topic for TS firmware: `hs109rs/ts/data`; DEV_ID = WiFi MAC address; DEV_NAME = `TS-last4MAC`
- No production DB connections; all tests use isolated SQLite in-memory
- No push, merge, deploy; local commits only

## Review Focus

1. Shell injection in generated bootstrap script (user-controlled device_name/ssid piped into bash)
2. Config file permission leak — agent state file containing device password written world-readable
3. HubBrain .env credential exposure if file not chmod 600 before service start
4. Approval expiry race — approval checked at manifest request but not refreshed during long polling
5. Duplicate node IDs across different gateways colliding in Monitoring whitelist

---

## Task 1: Bootstrap Extension

**Files:**
- Modify: `apps/api/src/routes/bootstrap.py`
- Create: `apps/api/tests/test_bootstrap_v2.py`

**Interfaces:**
- Produces: `BootstrapRequest` extended with `ztd_device_id`, `provisioning_url`, `monitoring_hub_id`, `monitoring_url`; build_script() output includes ZTD_DEVICE_ID, PROVISIONING_URL, MONITORING_HUB_ID, MONITORING_URL as shlex.quote'd vars

- [ ] **Step 1: Write failing tests for new bootstrap fields**
- [ ] **Step 2: Run tests → FAIL (fields not in model)**
- [ ] **Step 3: Extend BootstrapRequest with 4 new optional fields (all shlex.quote'd in _build_values)**
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit** `feat(bootstrap): add ZTD identity and dual-server config fields`

## Task 2: V2 Pi Agent

**Files:**
- Create: `apps/agent/agent_v2.py`
- Create: `apps/agent/agent_v2_state.json.example`
- Create: `apps/agent/ztd-agent-v2.service`
- Create: `apps/api/tests/test_agent_v2_contracts.py`

**Interfaces:**
- Consumes: `/api/v2/provisioning/register`, `/api/v2/provisioning/status`, `/api/v2/provisioning/manifest` (HTTP Basic auth, device_id:password)
- Produces: `ZTD_AGENT_STATE_FILE` JSON: `{device_id, revision, approval_status, manifest_hash, applied_at}`

- [ ] **Step 1: Write failing tests for state tracking and retry logic (pure functions, no network)**
- [ ] **Step 2: Run tests → FAIL**
- [ ] **Step 3: Implement agent_v2.py: authenticated register/status/manifest, exponential backoff, durable state, monitoring handoff**
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit** `feat(agent): V2 Pi agent with dual-server support and state tracking`

## Task 3: HubBrain Integration Adapter

**Files:**
- Create: `apps/agent/hubbrain_adapter.py`
- Create: `apps/agent/hubbrain_adapter_test_fixture.py` (test-only credential fixture)
- Create: `apps/agent/hubbrain.env.example`
- Create: `apps/api/tests/test_hubbrain_adapter.py`

**Interfaces:**
- Consumes: `manifest` from Task 2, env `HUB_ID`, `HUB_KEY`, `SERVER_URL`, `MQTT_HOST/PORT/PASS`
- Produces: `hub/.env` file at configurable path (chmod 600), systemd drop-in with EnvironmentFile

- [ ] **Step 1: Write failing tests for env file generation, permission check, blocklist for auto-issuance**
- [ ] **Step 2: Run tests → FAIL**
- [ ] **Step 3: Implement adapter: write .env, verify permissions, explicitly block HubGate credential issuance**
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit** `feat(hubbrain): secure adapter for HubBrain V5 integration`

## Task 4: ESP/IoT Node Provisioning Adapter

**Files:**
- Create: `apps/agent/esp_node_adapter.py`
- Create: `apps/agent/esp_node_adapter_test.py`
- Create: `docs/ESP_NODE_PROVISIONING.md`

**Interfaces:**
- Consumes: hub identity (gateway_id), ESP MAC (node_id = MAC), firmware topic pattern `hs109rs/{dev_type}/data`
- Produces: node association record JSON, whitelist entry format for HubBrain

- [ ] **Step 1: Write failing tests for identity mapping and whitelist format**
- [ ] **Step 2: Run tests → FAIL**
- [ ] **Step 3: Implement adapter: gateway_id/node_id/sensor_id/module_id mapping; firmware-compatible topics**
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit** `feat(esp): node identity adapter and whitelist provisioning`

## Task 5: Dashboard Minimal Extension

**Files:**
- Modify: `C:/Users/user/.local/share/opencode/worktree/6fed07/sprint3-edge-dashboard/ztd-dashboard/src/utils/provisioningState.mjs`
- Create: `C:/Users/user/.local/share/opencode/worktree/6fed07/sprint3-edge-dashboard/ztd-dashboard/src/utils/monitoringStatus.mjs`
- Modify: `C:/Users/user/.local/share/opencode/worktree/6fed07/sprint3-edge-dashboard/ztd-dashboard/src/views/DeploymentsView.vue`

**Interfaces:**
- Consumes: `/api/v2/provisioning/devices` (admin token from env, BFF pattern note)
- Produces: dual-server status display per device row

- [ ] **Step 1: Implement monitoringStatus.mjs (pure utility, no browser secrets)**
- [ ] **Step 2: Update DeploymentsView to show hub_id column and monitoring status**
- [ ] **Step 3: Run existing dashboard tests (vitest/vite-build if available)**
- [ ] **Step 4: Commit** `feat(dashboard): dual-server provisioning status display`

## Task 6: Integration Test Harness

**Files:**
- Create: `apps/api/tests/test_sprint3_integration.py`

**Interfaces:**
- Consumes: all previous tasks' produced artifacts (agent functions, adapter functions, V2 API)

- [ ] **Step 1: Write 18-scenario integration test suite (all locally isolated)**
- [ ] **Step 2: Run → PASS (or document hardware gaps)**
- [ ] **Step 3: Commit** `test(integration): Sprint 3 E2E harness, 18 scenarios`

## Task 7: Security Hardening + Sprint Report

**Files:**
- Create: `docs/SPRINT3-REPORT.md`
- Modify: `apps/agent/agent_v2.py` (fix any findings)
- Modify: `apps/agent/hubbrain_adapter.py` (fix any findings)

- [ ] **Step 1: Security review against 8 areas from mission brief**
- [ ] **Step 2: Fix confirmed defects**
- [ ] **Step 3: Write comprehensive sprint report**
- [ ] **Step 4: Commit** `docs: Sprint 3 security hardening and final report`
