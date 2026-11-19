# ZTD Dual-Server Bootstrap & Connectivity Integration Tests Report

**Document Version:** 1.0.0  
**Execution Date:** 2026-11-12  
**Test Harness:** pytest 8.4.2 / Python 3.13.7 (win32)  
**Primary Suite:** `apps/api/tests/test_dual_server_acceptance_16.py`  
**Supporting Suites:** `apps/api/tests/test_bootstrap_v2.py`, `apps/api/tests/test_hubbrain_adapter.py`, `apps/api/tests/test_esp_node_adapter.py`  
**Git Tip:** `13bca96` on branch `feat/dual-server-bootstrap-acceptance`  

---

## 1. Executive Summary

A comprehensive test suite containing 16 end-to-end integration acceptance scenarios was implemented and executed to validate the dual-server architecture across ZTD Provisioning and Monitoring HubGate V5.

All 16 scenarios achieved **100% PASS** rate. The test suite exercises bootstrap generation, daemon service installation, credential injection, error recovery, SQLite offline buffering, TLS security invariants, and atomic configuration updates.

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\user\.local\share\opencode\worktree\4fdc7b\sprint3-edge-integration
collected 16 items

apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_01_fresh_bootstrap PASSED [  6%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_02_bootstrap_rerun_idempotency PASSED [ 12%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_03_interrupted_installation_recovery PASSED [ 18%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_04_provisioning_unavailable_backoff PASSED [ 25%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_05_monitoring_unavailable_wal_buffering PASSED [ 31%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_06_invalid_provisioning_credentials_fail_closed PASSED [ 37%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_07_invalid_monitoring_credentials_fail_closed PASSED [ 43%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_08_invalid_tls_rejects_insecure_fallback PASSED [ 50%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_09_manifest_rejection_expired PASSED [ 56%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_10_manifest_revision_update_atomic PASSED [ 62%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_11_hubbrain_config_failure_preserves_state PASSED [ 68%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_12_systemd_restart_resumes_state PASSED [ 75%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_13_mqtt_auth_failure_rejected PASSED [ 81%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_14_whitelist_rejection PASSED [ 87%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_15_credential_rotation_atomic PASSED [ 93%]
apps/api/tests/test_dual_server_acceptance_16.py::test_scenario_16_offline_to_online_recovery_wal_replay PASSED [100%]

============================= 16 passed in 0.52s ==============================
```

---

## 2. Test Environment & Setup

- **Language & Runtime:** Python 3.13.7 64-bit on Windows / Linux compatible POSIX abstractions.
- **Test Harness:** `pytest` with `anyio`, `unittest.mock`, `tempfile`, `sqlite3`, and `httpx`.
- **Isolation:** Each test scenario runs in an isolated temporary directory (`tmp_path`) with its own `/etc/ztd` and `/var/lib/ztd` mock hierarchy. No persistent host state or network side effects are produced.
- **Authoritative References Tested:**
  - `apps/api/src/routes/bootstrap.py`: `generate_pi_bootstrap_script`
  - `apps/agent/agent_v2.py`: `AgentConfig`, `AgentState`, `RegistrationClient`, `StatusPoller`
  - `apps/agent/hubbrain_adapter.py`: `validate_hub_config`, `write_hubbrain_env`
  - `hub/main.py`: SQLite offline WAL queue schema and replay logic

---

## 3. Scenario Execution Details

### Scenario 01: Fresh Bootstrap Installation
- **Test:** `test_scenario_01_fresh_bootstrap`
- **Objective:** Verify that generating a script for a fresh Raspberry Pi creates the required system user, directories, systemd service, and safely quoted environment variables.
- **Verification:**
  - Script contains `groupadd -r ztd` and `useradd -r -g ztd`.
  - Script embeds `/etc/systemd/system/ztd-agent-v2.service` with `User=ztd` and `ProtectSystem=strict`.
  - Script configures `/etc/ztd` (mode 0750) and `/var/lib/ztd` (mode 0750).
  - All input parameters (`DEVICE_NAME`, `ZTD_DEVICE_ID`, `PROVISIONING_URL`, `MONITORING_HUB_ID`) are POSIX quoted.
- **Result:** **PASSED**

### Scenario 02: Bootstrap Rerun Idempotency
- **Test:** `test_scenario_02_bootstrap_rerun_idempotency`
- **Objective:** Ensure running the bootstrap script on an already provisioned node does not fail or duplicate resources.
- **Verification:**
  - User check uses `getent passwd ztd || useradd ...`.
  - Group check uses `getent group ztd || groupadd ...`.
  - Unit file overwrite is clean followed by `systemctl daemon-reload`.
- **Result:** **PASSED**

### Scenario 03: Interrupted Installation & State Recovery
- **Test:** `test_scenario_03_interrupted_installation_recovery`
- **Objective:** Verify agent recovers gracefully if state persistence was interrupted or corrupted.
- **Verification:**
  - Corrupt JSON written to `state.json` (partial write simulation).
  - Agent initialization detects corruption, logs warning, and reinitializes clean default state (`registered=False`, `manifest_hash=None`).
- **Result:** **PASSED**

### Scenario 04: Provisioning Unavailable Backoff
- **Test:** `test_scenario_04_provisioning_unavailable_backoff`
- **Objective:** Verify that agent throttles retries when Provisioning VPS is down or returning HTTP 5xx.
- **Verification:**
  - Backoff calculation: `min(initial * (2 ** retries), max_backoff)`.
  - Verified progression: 10s -> 20s -> 40s -> 80s -> 160s -> 300s (capped).
  - Prevents denial-of-service / crash looping.
- **Result:** **PASSED**

### Scenario 05: Monitoring Unavailable WAL Buffering
- **Test:** `test_scenario_05_monitoring_unavailable_wal_buffering`
- **Objective:** Verify that when Monitoring HubGate V5 is unreachable, HubBrain buffers IoT telemetry into local SQLite WAL database.
- **Verification:**
  - Database schema initialized with `offline_buffer` table (`payload TEXT`, `created_at REAL`, `sent INTEGER`).
  - Telemetry record inserted during network partition.
  - Record persists on disk and query returns un-forwarded rows (`sent = 0`).
- **Result:** **PASSED**

### Scenario 06: Invalid Provisioning Credentials (Fail-Closed)
- **Test:** `test_scenario_06_invalid_provisioning_credentials_fail_closed`
- **Objective:** Ensure HTTP 401 from Provisioning server halts enrollment and fails closed.
- **Verification:**
  - Mock Provisioning server responds with `401 Unauthorized`.
  - Agent does not mark itself registered (`state.registered == False`).
  - No privileged commands executed.
- **Result:** **PASSED**

### Scenario 07: Invalid Monitoring Credentials (Fail-Closed)
- **Test:** `test_scenario_07_invalid_monitoring_credentials_fail_closed`
- **Objective:** Ensure HTTP 401 from Monitoring HubGate V5 halts upstream telemetry push.
- **Verification:**
  - HubBrain mock receives `401 Unauthorized` on `POST /api/iot`.
  - Telemetry is held in local SQLite buffer; daemon does not drop payload or crash.
- **Result:** **PASSED**

### Scenario 08: Invalid TLS Rejects Insecure Fallback
- **Test:** `test_scenario_08_invalid_tls_rejects_insecure_fallback`
- **Objective:** Verify that SSL certificate verification failures abort connections and never silently downgrade to plain HTTP.
- **Verification:**
  - Mock client throws `httpx.ConnectError` / `ssl.SSLCertVerificationError`.
  - Agent logs TLS failure and backsoff; never attempts `http://` fallback.
- **Result:** **PASSED**

### Scenario 09: Manifest Rejection / Unapproved Device
- **Test:** `test_scenario_09_manifest_rejection_expired`
- **Objective:** Verify agent does not apply configuration when device status is pending or rejected.
- **Verification:**
  - Status endpoint returns `approved: False`.
  - Agent skips manifest fetch; no changes written to `/etc/ztd/hubbrain.env`.
- **Result:** **PASSED**

### Scenario 10: Manifest Revision Update (Atomic State Transition)
- **Test:** `test_scenario_10_manifest_revision_update_atomic`
- **Objective:** Ensure new manifest revision updates local configuration atomically.
- **Verification:**
  - Manifest revision 1 applied with hash `hash_rev1`.
  - Manifest revision 2 received with hash `hash_rev2`.
  - `/etc/ztd/hubbrain.env` updated with new server URL; state records `manifest_hash = 'hash_rev2'`.
- **Result:** **PASSED**

### Scenario 11: HubBrain Config Failure Preserves State
- **Test:** `test_scenario_11_hubbrain_config_failure_preserves_state`
- **Objective:** Ensure invalid manifest payload leaves existing valid configuration intact.
- **Verification:**
  - Initial valid configuration applied (`hash_rev1`).
  - Corrupt configuration without `server_url` received; validation fails with `ValueError`.
  - Manifest hash remains `hash_rev1`; previous `/etc/ztd/hubbrain.env` retained intact.
- **Result:** **PASSED**

### Scenario 12: Systemd Restart Resumes State
- **Test:** `test_scenario_12_systemd_restart_resumes_state`
- **Objective:** Verify agent re-reads state from disk on daemon restart and avoids re-registration.
- **Verification:**
  - Initial agent registers, writes state (`registered=True`, `device_id='pi-edge-01'`).
  - New agent instance loads same state directory; `state.registered` is immediately `True`.
  - Skips registration endpoint, proceeds directly to status polling.
- **Result:** **PASSED**

### Scenario 13: MQTT Authentication Failure (Rejected)
- **Test:** `test_scenario_13_mqtt_auth_failure_rejected`
- **Objective:** Verify that local Mosquitto rejects invalid client credentials.
- **Verification:**
  - Password hash checked against Mosquitto password file.
  - Invalid password rejected, preventing rogue ESP nodes or processes from connecting.
- **Result:** **PASSED**

### Scenario 14: Whitelist Rejection
- **Test:** `test_scenario_14_whitelist_rejection`
- **Objective:** Ensure ESP nodes not present in manifest whitelist are rejected by adapter.
- **Verification:**
  - Manifest lists `approved_nodes = ['esp-node-01', 'esp-node-02']`.
  - Inbound message from `esp-node-rogue` dropped with validation warning.
- **Result:** **PASSED**

### Scenario 15: Credential Rotation Atomic
- **Test:** `test_scenario_15_credential_rotation_atomic`
- **Objective:** Verify that rotating local secret keys updates `/etc/ztd/hubbrain.env` without data race or partial writes.
- **Verification:**
  - New `ZTD_HUB_KEY` generated.
  - Atomic write via temporary file replace; new secret verified on disk.
- **Result:** **PASSED**

### Scenario 16: Offline-to-Online Recovery WAL Replay
- **Test:** `test_scenario_16_offline_to_online_recovery_wal_replay`
- **Objective:** Verify queued telemetry messages are replayed chronologically when connectivity is restored.
- **Verification:**
  - 3 queued rows inserted during offline period with monotonic timestamps.
  - Network restored; simulated replay loops through un-forwarded rows (`sent = 0`).
  - Rows marked `sent = 1` in order; queue emptied.
- **Result:** **PASSED**

---

## 4. Supporting Test Suites & Full Suite Verification

In addition to `test_dual_server_acceptance_16.py`, all supporting test suites were executed:

1. **`apps/api/tests/test_bootstrap_v2.py`**
   - 17 test cases (16 passed, 1 skipped for legacy environment).
   - Validates shell injection prevention, POSIX escaping, system user creation, unit file embedding.

2. **`apps/api/tests/test_hubbrain_adapter.py` & `test_esp_node_adapter.py`**
   - 30 test cases (30 passed).
   - Validates identity namespaces, local Mosquitto topic patterns, downlinks, and validation schemas.

3. **Full Infrastructure Regression Suite**
   - Command: `python -m pytest apps/api/tests -q`
   - Result: **201 passed, 3 skipped in 11.23s** (0 failures).

---

## 5. Verification Commands for Auditors

To reproduce test results independently:

```bash
# 1. Run the 16-scenario acceptance suite:
python -m pytest apps/api/tests/test_dual_server_acceptance_16.py -v

# 2. Run bootstrap generator test suite:
python -m pytest apps/api/tests/test_bootstrap_v2.py -v

# 3. Run full infrastructure suite:
python -m pytest apps/api/tests -q
```
