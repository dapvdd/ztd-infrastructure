# ZTD & Monitoring HubGate Dual-Server Acceptance Report

**Document Version:** 1.0.0  
**Evaluation Date:** 2026-11-12  
**Authority:** Principal Edge & Security Systems Lead  
**Governing Repositories & Commits:**
- **ZTD Edge Integration (Branch `feat/dual-server-bootstrap-acceptance`):** Commit `13bca96` (and associated audit commits)
- **Monitoring HubGate V5 (`mochmizan/proyek-monitoring-dtedi`):** Commit `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`
- **ZTD Dashboard (Branch `sprint3-remediation/edge-dashboard`):** Commit `a60b9a3`
- **Provisioning VPS:** `100.105.163.126` (Read-Only inspected)

---

## 1. Executive Summary

This report establishes the final acceptance evaluation for the Zero Touch Deployment (ZTD) Raspberry Pi bootstrap pipeline and dual-server integration with Monitoring HubGate V5.

All architectural contracts, identity isolation invariants, bootstrap generator security enhancements, and integration test suites have been implemented and verified. In accordance with zero-trust engineering standards and project directives, statuses are assigned with absolute honesty without fabricating access to unreachable campus networks or missing physical hardware.

| Acceptance Gate | Scope | Status | Notes & Blockers |
|---|---|---|---|
| **Gate A** | Bootstrap Source Security | **READY** | Shell escaping (`shlex.quote`), system user `ztd`, sandboxed unit file, non-interactive apt. |
| **Gate B** | Fresh Raspberry Pi Installation | **READY (Code) / PARTIAL (Hardware)** | Generator verified; physical board bench test pending hardware availability. |
| **Gate C** | Provisioning Connectivity | **READY** | Provisioning VPS (`100.105.163.126`) active; bounded timeouts & exponential backoff verified. |
| **Gate D** | Provisioning Authentication & Enrollment | **READY** | Basic Auth device tokens, atomic status transitions, and manifest access control verified. |
| **Gate E** | HubBrain Installation | **READY** | Pydantic schema validation, weak key runtime assertion, `.env` file deployment verified. |
| **Gate G** | Monitoring Authentication | **BLOCKED** | Manual admin approval required by HubGate V5 architecture (`POST /api/hubs/{id}/approve`). Automated credential generation forbidden. |
| **Gate F** | Monitoring Network Connectivity | **PARTIAL** | Upstream campus IP (`100.108.98.30`) isolated; SQLite WAL buffering verified offline. |
| **Gate H** | MQTT & ESP Compatibility | **READY** | Mosquitto broker configuration, `hs109rs/#` topic mapping, ESP MAC whitelist verified. |
| **Gate I** | End-to-End Dual-Server Operation | **PARTIAL** | Contract and simulation pass 100%; live dual-server execution awaits Gate G and B. |

---

## 2. Acceptance Gate Evaluations (A through I)

### Gate A: Bootstrap Source Security
- **Status:** **READY**
- **Evaluation:**
  - `apps/api/src/routes/bootstrap.py` utilizes POSIX single-quote escaping via `shlex.quote()` on all interpolation targets (`DEVICE_NAME`, `WIFI_SSID`, `WIFI_PASSWORD`, `ZTD_DEVICE_ID`, `PROVISIONING_URL`, `MONITORING_HUB_ID`, `MONITORING_URL`).
  - Idempotent creation of unprivileged system user `ztd` (`getent passwd ztd || useradd -r -g ztd -s /usr/sbin/nologin -d /var/lib/ztd ztd`).
  - Embeds `/etc/systemd/system/ztd-agent-v2.service` with strict sandboxing: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/ztd /etc/ztd`.
  - Credentials are written directly to `/etc/ztd/agent.env` with `0600` permissions and never leaked in process arguments or logs.
- **Evidence:** `apps/api/tests/test_bootstrap_v2.py` (16 passed, 1 skipped); `docs/BOOTSTRAP-SECURITY-AUDIT.md`.

### Gate B: Fresh Raspberry Pi Installation
- **Status:** **READY (Code & Integration) / PARTIAL (Physical Bench)**
- **Evaluation:**
  - Automated installation flow verified on clean file system structures: creates `/etc/ztd` (0750), `/var/lib/ztd` (0750), installs python venv, and configures local Mosquitto broker.
  - Script idempotency proven: repeated runs do not fail or duplicate entries.
  - Physical Raspberry Pi hardware bench test is deferred until physical hardware and lab power are connected.
- **Evidence:** `test_scenario_01_fresh_bootstrap` and `test_scenario_02_bootstrap_rerun_idempotency` in `test_dual_server_acceptance_16.py`; `docs/PI-INSTALLATION-RUNBOOK.md`.

### Gate C: Provisioning Connectivity
- **Status:** **READY**
- **Evaluation:**
  - Read-only probe against Provisioning VPS (`100.105.163.126`) confirmed `ztd-nginx`, `ztd-backend`, `ztd-db`, and `ztd-mqtt` active.
  - Public health endpoint returns `{"status":"healthy","database":"connected"}`.
  - Edge agent HTTP client implements bounded 15-second timeouts and capped exponential backoff (10s -> 20s -> 40s -> 80s -> 160s -> 300s max), preventing retry storms.
- **Evidence:** Live VPS recon commands; `test_scenario_04_provisioning_unavailable_backoff`.

### Gate D: Provisioning Authentication & Enrollment
- **Status:** **READY**
- **Evaluation:**
  - HTTP Basic Authentication (`ZTD_DEVICE_ID:ZTD_DEVICE_PASSWORD`) strictly enforced on all device endpoints.
  - State transitions follow deterministic lifecycle: Unregistered -> Enrolled/Pending -> Approved -> Manifest Synchronized.
  - Unapproved or pending devices are refused manifest download (`HTTP 403 Forbidden`).
  - Agent state persistence survives daemon restarts without duplicate registration.
- **Evidence:** `test_scenario_06_invalid_provisioning_credentials_fail_closed`, `test_scenario_09_manifest_rejection_expired`, and `test_scenario_12_systemd_restart_resumes_state`.

### Gate E: HubBrain Installation
- **Status:** **READY**
- **Evaluation:**
  - `hubbrain_adapter.py` validates `server_url`, `hub_id`, and `approved_nodes` using Pydantic schemas.
  - Fails closed on weak credentials: checks against default placeholder SHA-256 hashes for `MQTT_PASS` and `HUB_KEY` unless explicitly permitted.
  - Deploys configuration atomically to `/etc/ztd/hubbrain.env`.
  - Malformed manifest configuration leaves previous running configuration intact.
- **Evidence:** `apps/api/tests/test_hubbrain_adapter.py` (19 passed); `test_scenario_11_hubbrain_config_failure_preserves_state`.

### Gate F: Monitoring Network Connectivity
- **Status:** **PARTIAL**
- **Evaluation:**
  - Monitoring endpoints (`https://100.108.98.30/api/iot` and `http://10.33.102.172:8000/api/iot`) are identified from authoritative source `hub/main.py`.
  - Upstream host `100.108.98.30` is located inside campus Tailscale/VPN network and is unreachable from external development networks.
  - Network disconnection is handled gracefully: HubBrain offline SQLite buffer queue (`/var/lib/ztd/hub_buffer.db`) stores telemetry in WAL mode without dropping data.
- **Evidence:** `test_scenario_05_monitoring_unavailable_wal_buffering` and `test_scenario_16_offline_to_online_recovery_wal_replay`.

### Gate G: Monitoring Authentication
- **Status:** **BLOCKED**
- **Evaluation:**
  - Architectural constraint: HubGate V5 does **not** automatically issue `HUB_ID` and `HUB_KEY`.
  - Upstream endpoint `POST /api/hubs/pair` returns `202 Accepted` (`status: pending_approval`).
  - Active authorization (`is_active=True`) requires manual campus administrator approval via `POST /api/hubs/{hub_id}/approve`.
  - Storing administrative bypass credentials on edge devices is rejected as an insecure practice (CWE-259).
  - Production deployment remains blocked until campus administrator provisions approved `HUB_ID` and `HUB_KEY`.
- **Evidence:** `apps/agent/hubbrain_adapter.py` lines 24-29; `docs/MONITORING-CREDENTIAL-REQUIREMENTS.md`.

### Gate H: MQTT and ESP Compatibility
- **Status:** **READY**
- **Evaluation:**
  - Local Mosquitto broker configured with password file and explicit ACLs.
  - Telemetry topic structure `hs109rs/#` correctly ingested and adapted.
  - Downlink commands mapped to `{hub_name}/{dev_type}/command`.
  - Node whitelist filtering drops unapproved ESP MAC addresses.
- **Evidence:** `apps/api/tests/test_esp_node_adapter.py` (11 passed); `test_scenario_13_mqtt_auth_failure_rejected` and `test_scenario_14_whitelist_rejection`.

### Gate I: End-to-End Dual-Server Operation
- **Status:** **PARTIAL**
- **Evaluation:**
  - Dual-server separation is 100% verified in simulation and integration contract tests.
  - ZTD Provisioning controls device state and manifest delivery without touching sensor telemetry.
  - HubBrain handles sensor bridging without touching provisioning databases.
  - End-to-end live deployment across both physical VPS hosts is pending resolution of Gate G (manual credential issuance) and Gate B (physical hardware deployment).
- **Evidence:** `test_dual_server_acceptance_16.py` (16/16 passed); `docs/DUAL-SERVER-CONTRACT.md`.

---

## 3. Test Suite Summary & Regression Verification

### Test Results Breakdown:
1. **Dual-Server Acceptance Suite (`test_dual_server_acceptance_16.py`):**
   - 16 passed, 0 failed, 0 skipped (100% pass rate).
2. **Bootstrap Generator Suite (`test_bootstrap_v2.py`):**
   - 16 passed, 0 failed, 1 skipped.
3. **Full Infrastructure Backend Suite (`apps/api/tests`):**
   - 201 passed, 0 failed, 3 skipped in 11.23s.
4. **Dashboard Frontend Suite (`ztd-dashboard`):**
   - 168 passed, 0 failed, 0 skipped in 534ms.

### Total Verified Test Cases:
- **369 Automated Tests Passing Across Infrastructure and Dashboard.**
- **Zero regressions detected.**

---

## 4. Deliverable Documentation Index

The following authoritative documents are delivered in `docs/`:

1. `docs/DUAL-SERVER-CONTRACT.md`: Complete identity namespaces, network architecture, header standards, and blast-radius isolation.
2. `docs/BOOTSTRAP-SECURITY-AUDIT.md`: In-depth analysis of 16 security checklist criteria, CWE mappings, argument safety, and systemd sandboxing.
3. `docs/MONITORING-CREDENTIAL-REQUIREMENTS.md`: Documentation of the manual HubGate credential boundary, required environment variables, and rotation runbooks.
4. `docs/PI-INSTALLATION-RUNBOOK.md`: Step-by-step operator guide for Raspberry Pi OS preparation, bootstrap execution, credential injection, and daemon troubleshooting.
5. `docs/BOOTSTRAP-INTEGRATION-TESTS.md`: Detailed test catalog of all 16 acceptance test scenarios, mock configurations, and execution results.
6. `docs/DUAL-SERVER-ACCEPTANCE-REPORT.md`: This comprehensive acceptance report and gate scorecard.

---

## 5. Reproduction & Rollback Instructions

### Reproduction Steps:
```bash
# Clone and enter the worktree
cd C:/Users/user/.local/share/opencode/worktree/4fdc7b/sprint3-edge-integration

# Run the 16-scenario acceptance suite
python -m pytest apps/api/tests/test_dual_server_acceptance_16.py -v

# Run the full regression test suite
python -m pytest apps/api/tests -q

# Run dashboard regression tests
cd C:/Users/user/.local/share/opencode/worktree/6fed07/sprint3-edge-dashboard/ztd-dashboard
node --test tests/*.test.mjs
```

### Rollback Plan:
All work has been strictly isolated to branch `feat/dual-server-bootstrap-acceptance`. No production deployments, database migrations, or remote git pushes have been executed.
To revert local changes completely:
```bash
git checkout sprint3-remediation/edge-integration
git branch -D feat/dual-server-bootstrap-acceptance
```
On physical Raspberry Pi edge nodes, rollback is performed via the uninstallation commands documented in Section 6 of `docs/PI-INSTALLATION-RUNBOOK.md`.
