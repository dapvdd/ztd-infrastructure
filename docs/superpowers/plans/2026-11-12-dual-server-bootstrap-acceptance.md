# ZTD Dual-Server Bootstrap Security & Connectivity Acceptance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish end-to-end bootstrap security, multi-server identity isolation, and verified integration tests for ZTD Provisioning and Monitoring HubGate V5, delivering 6 authoritative engineering reports and acceptance gates.

**Architecture:** The Raspberry Pi edge gateway operates under a strict dual-server boundary: ZTD Provisioning (VPS `100.105.163.126`) controls device lifecycle, status, and module manifests via `agent_v2.py`, while Monitoring HubGate V5 (`mochmizan/proyek-monitoring-dtedi`, commit `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`) receives IoT sensor telemetry from HubBrain (`hub/main.py`) via local Mosquitto. Bootstrap script generator (`bootstrap.py`) is hardened with system user creation, unit file deployment, and package management without leaking secrets or command arguments.

**Tech Stack:** Python 3.11+ (FastAPI, HTTPX, Pydantic v2, pytest), Bash / NetworkManager (nmcli), systemd, Mosquitto 2.x with ACLs, OpenSSL TLS, Node.js 20+ (test runner), SSH (read-only VPS telemetry).

**Spec:** ZTD Dual-Server Bootstrap Security & Connectivity Acceptance Prompt, `docs/SYSTEM_CONTRACTS.md`, `docs/PROVISIONING-V2-API.md`, `docs/SPRINT3-REMEDIATION-REPORT.md`, Monitoring repository `hub/AGENTS.md`, `server/AGENTS.md`, `deploy/AGENTS.md`.

## Global Constraints

- Never push, merge, or deploy to production; keep local baselines intact.
- Provisioning VPS (`firza@100.105.163.126`) operations must be STRICTLY READ-ONLY (no restarts, no migrations, no file changes, no database writes).
- External Monitoring repository (`mochmizan/proyek-monitoring-dtedi`) is strictly read-only.
- Preserve separation between `ZTD_DEVICE_ID`, `MONITORING_HUB_ID`, `ESP_NODE_ID`, and `SENSOR_ID`.
- No credentials passed via CLI process args, public manifests, or printed in logs.
- Fails closed: unapproved devices cannot receive privileged configuration; monitoring outages must not break provisioning, and provisioning outages must not corrupt monitoring state.
- If physical Pi hardware or official Monitoring credentials are unavailable, document the manual boundary and mark the gate BLOCKED or PARTIAL without fabricating connection success.

## Review Focus

1. Fresh Pi execution failure: uncreated `ztd` user and missing `ztd-agent-v2.service` file break installation on bare Raspberry Pi OS.
2. Manifest credential injection: manifest returns `hub_config` with server/port, but agent must strictly merge local secrets (`ZTD_HUB_KEY`, `ZTD_MQTT_PASS`) from `/etc/ztd/agent.env` rather than expecting secrets from Provisioning.
3. HubBrain service crash on startup: HubBrain V5 `main.py` raises `RuntimeError` if `MQTT_PASS` or `HUB_KEY` is empty or matches weak default values unless `ALLOW_INSECURE_DEV_KEYS=true`.
4. Import path portability: pytest running from repository root fails with `ModuleNotFoundError: No module named 'src'` in `test_bootstrap_v2.py`.
5. Replay stamp & timing: HubBrain offline SQLite WAL replay stamps `_hub_created_at` float epoch; server requires `event_time` derivation.

---

### Task 1: Contract Verification & Live Read-Only VPS Reconnaissance

**Files:**
- Read: `C:/Users/user/.local/share/opencode/worktree/4fdc7b/sprint3-edge-integration/apps/api/src/routes/bootstrap.py`
- Read: `C:/Users/user/.local/share/opencode/worktree/4fdc7b/sprint3-edge-integration/apps/agent/agent_v2.py`
- Read: `C:/Users/user/Development/proyek-monitoring-dtedi/hub/main.py`
- Read: `C:/Users/user/Development/proyek-monitoring-dtedi/server/app/dependencies.py`
- Read: `C:/Users/user/Development/proyek-monitoring-dtedi/server/app/routers/hubs.py`
- Read: `C:/Users/user/Development/proyek-monitoring-dtedi/deploy/hubbrain.service`

**Interfaces:**
- Consumes: SSH `firza@100.105.163.126`, Git commit logs of both repositories
- Produces: Sanitized VPS state (ports, active systemd units, public HTTP status), exact commit SHAs and contract matrix

- [ ] **Step 1: Execute read-only inspection commands against Provisioning VPS**
  Run: `ssh firza@100.105.163.126 "systemctl list-units --type=service --state=running | grep -E 'ztd|nginx|docker'; ss -tulpn; docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"`
  Verify: Only inspect, no modifications.

- [ ] **Step 2: Inspect public Provisioning VPS HTTP endpoints with curl**
  Run: `ssh firza@100.105.163.126 "curl -sk https://127.0.0.1/health || curl -sk http://127.0.0.1:8000/health"`
  Verify: HTTP status code and response payload structure.

- [ ] **Step 3: Document commit hashes, endpoints, headers, and schemas from authoritative sources**
  Verify: Monitoring commit `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`, Infrastructure tip `692221e`, Dashboard tip `a60b9a3`.

---

### Task 2: Bootstrap Script Hardening & Import Path Portability

**Files:**
- Modify: `apps/api/src/routes/bootstrap.py`
- Modify: `apps/api/tests/test_bootstrap_v2.py`
- Test: `apps/api/tests/test_bootstrap_v2.py`

**Interfaces:**
- Consumes: `BootstrapRequest` payload
- Produces: Production-grade `bootstrap-pi.sh` containing system user creation, directory setup, unit installation, env file generation, and systemd enable; dual-CWD portable pytest import

- [ ] **Step 1: Write failing tests for bootstrap script completeness in `test_bootstrap_v2.py`**
  Test asserts that generated script contains:
  - System group and user creation `getent group ztd || groupadd -r ztd` and `getent passwd ztd || useradd -r -g ztd ...`
  - Unit file creation for `/etc/systemd/system/ztd-agent-v2.service`
  - `systemctl daemon-reload` before `systemctl enable --now ztd-agent-v2`
  - Fix test import so `test_bootstrap_v2.py` can be imported from both repo root and `apps/api`

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m pytest apps/api/tests/test_bootstrap_v2.py -q`
  Expected: FAIL on missing user creation or unit embedding.

- [ ] **Step 3: Implement user creation, unit file installation, and dual-CWD imports**
  Update `apps/api/src/routes/bootstrap.py` to embed `/etc/systemd/system/ztd-agent-v2.service` and user setup.
  Update `test_bootstrap_v2.py` with `try: from src.main import app except ModuleNotFoundError: from apps.api.src.main import app`.

- [ ] **Step 4: Run tests to verify they pass from both CWDs**
  Run: `python -m pytest apps/api/tests/test_bootstrap_v2.py -q` from repo root and `apps/api`.
  Expected: PASS.

---

### Task 3: Dual-Server Identity Specification & Verification

**Files:**
- Create: `docs/DUAL-SERVER-CONTRACT.md`
- Test: `apps/api/tests/test_hubbrain_adapter.py`
- Test: `apps/api/tests/test_esp_node_adapter.py`

**Interfaces:**
- Consumes: `ZTD_DEVICE_ID`, `MONITORING_HUB_ID`, `ESP_NODE_ID`, `SENSOR_ID`
- Produces: Deterministic identity mapping rules, contract invariants, header standards (`X-Hub-ID`, `X-Hub-Key`, Basic Auth `ZTD_DEVICE_ID:ZTD_DEVICE_PASSWORD`)

- [ ] **Step 1: Write tests verifying strict identity decoupling and validation**
  Ensure adapter tests prove:
  - `ZTD_DEVICE_ID` never replaces `MONITORING_HUB_ID`
  - `hubbrain_adapter.validate_hub_config` rejects missing or mismatched `hub_id`
  - Local MQTT topics follow `hs109rs/#` and downlink `{hub_name}/{dev_type}/command`

- [ ] **Step 2: Run tests to verify existing contract adherence**
  Run: `python -m pytest apps/api/tests/test_hubbrain_adapter.py apps/api/tests/test_esp_node_adapter.py -q`
  Expected: PASS.

- [ ] **Step 3: Compile `docs/DUAL-SERVER-CONTRACT.md`**
  Detail exact identity namespaces, lifecycle states, token flows, and network topology.

---

### Task 4: Comprehensive 16-Scenario Integration Tests Suite

**Files:**
- Create: `apps/api/tests/test_dual_server_acceptance_16.py`
- Test: `apps/api/tests/test_dual_server_acceptance_16.py`

**Interfaces:**
- Consumes: `agent_v2.py`, `hubbrain_adapter.py`, `bootstrap.py`, FastAPI test client
- Produces: Automated pytest suite exercising all 16 mission scenarios:
  1. Fresh bootstrap
  2. Bootstrap rerun (idempotent)
  3. Interrupted installation / corrupt state recovery
  4. Provisioning unavailable (graceful backoff)
  5. Monitoring unavailable (offline SQLite WAL buffering)
  6. Invalid Provisioning credentials (401 backoff, fail-closed)
  7. Invalid Monitoring credentials (401 reject, fail-closed)
  8. Invalid TLS certificate (reject, no insecure fallback)
  9. Manifest rejection (unapproved device 403)
  10. Manifest revision update (atomic state transition)
  11. HubBrain configuration failure (invalid schema leaves state intact)
  12. Systemd restart and recovery (resumes from persisted state.json)
  13. MQTT authentication failure (Mosquitto bad creds fail-closed)
  14. Whitelist rejection (unapproved MAC dropped)
  15. Credential rotation (re-read updated env without data corruption)
  16. Offline-to-online recovery (WAL replay with timestamps)

- [ ] **Step 1: Write the 16 integration tests in `test_dual_server_acceptance_16.py`**
  Each test corresponds to one of the 16 required verification scenarios with explicit assertions.

- [ ] **Step 2: Run test suite to verify all 16 scenarios pass**
  Run: `python -m pytest apps/api/tests/test_dual_server_acceptance_16.py -v`
  Expected: 16 passed.

---

### Task 5: Security Audit Documentation

**Files:**
- Create: `docs/BOOTSTRAP-SECURITY-AUDIT.md`
- Create: `docs/MONITORING-CREDENTIAL-REQUIREMENTS.md`

**Interfaces:**
- Consumes: Audit findings from `bootstrap.py`, `agent_v2.py`, `hubbrain_adapter.py`, and Monitoring V5 security specifications
- Produces: Complete threat analysis, CVE/CWE mapping, argument safety, secret handling, and credential provisioning runbook

- [ ] **Step 1: Audit bootstrap and agent for the 16 safety requirements**
  Inspect shell quoting, log output, process args, env permissions, CA trust, dependency pinning, failure states.

- [ ] **Step 2: Write `docs/BOOTSTRAP-SECURITY-AUDIT.md`**
  Cover all 16 security checklist items with code evidence and line numbers.

- [ ] **Step 3: Write `docs/MONITORING-CREDENTIAL-REQUIREMENTS.md`**
  Document the exact boundary between automated ZTD provisioning and manual Monitoring credential issuance.

---

### Task 6: Operational Runbook & Integration Test Report

**Files:**
- Create: `docs/PI-INSTALLATION-RUNBOOK.md`
- Create: `docs/BOOTSTRAP-INTEGRATION-TESTS.md`

**Interfaces:**
- Consumes: Verified commands, systemd unit templates, test outputs
- Produces: Step-by-step Pi installation guide and detailed test execution log

- [ ] **Step 1: Write `docs/PI-INSTALLATION-RUNBOOK.md`**
  Provide operators with step-by-step instructions for:
  - Preparing Raspberry Pi OS (Debian 12 Bookworm)
  - Downloading and verifying the bootstrap script
  - Running bootstrap and verifying user/systemd setup
  - Provisioning ZTD device credentials and Monitoring HUB_ID/HUB_KEY
  - Validating local Mosquitto, Agent V2, and HubBrain service statuses

- [ ] **Step 2: Write `docs/BOOTSTRAP-INTEGRATION-TESTS.md`**
  Document all test commands, environment configurations, mock vs real fixtures, and exact test results for the 16 scenarios.

---

### Task 7: Dual-Server Acceptance Gate Report & Review

**Files:**
- Create: `docs/DUAL-SERVER-ACCEPTANCE-REPORT.md`

**Interfaces:**
- Consumes: Results from Tasks 1 through 6
- Produces: Authoritative verdict for Gates A through I (READY / PARTIAL / BLOCKED), rollback instructions, and sign-off summary

- [ ] **Step 1: Evaluate each acceptance gate (A through I)**
  - A. Bootstrap source security
  - B. Fresh Raspberry Pi installation
  - C. Provisioning connectivity
  - D. Provisioning authentication and enrollment
  - E. HubBrain installation
  - F. Monitoring network connectivity
  - G. Monitoring authentication
  - H. MQTT and ESP compatibility
  - I. End-to-end dual-server operation

- [ ] **Step 2: Compile `docs/DUAL-SERVER-ACCEPTANCE-REPORT.md`**
  Include exact commits, commands executed, passed/failed/skipped breakdown, remaining blockers, reproduction and rollback instructions.

- [ ] **Step 3: Run regression suites across Infrastructure and Dashboard to verify zero regression**
  Run: `python -m pytest apps/api/tests -q` (infra)
  Run: `node --test tests/*.test.mjs` (dashboard)
  Verify: All existing tests pass without regressions.
