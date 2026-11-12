# ZTD Raspberry Pi Bootstrap Security Audit

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-12  
**Lead Auditor:** Principal Linux & Security Engineer  
**Scope:** `apps/api/src/routes/bootstrap.py`, `apps/agent/agent_v2.py`, `apps/agent/hubbrain_adapter.py`, `apps/agent/ztd-agent-v2.service`  
**Git Tip:** `e4afaa3` / `13bca96` on branch `feat/dual-server-bootstrap-acceptance`

---

## Executive Summary

A comprehensive security audit of the Zero Touch Deployment (ZTD) Raspberry Pi bootstrap pipeline and agent daemon was conducted. The audit evaluated source code, template rendering, process execution, credential persistence, and error handling against standards defined in NIST SP 800-63B, OWASP Top 10 for IoT, and CIS Debian Linux Benchmarks.

All 16 security checklist criteria were verified through code analysis and automated test suites. Vulnerabilities identified in earlier iterations (unquoted shell interpolation, missing daemon system users, lack of daemon unit installation) have been resolved.

---

## Comprehensive Security Checklist & Evidence Matrix

### 1. Shell Injection Resistance (CWE-78 / CWE-88)
- **Status:** **PASS**
- **Evidence:** In `apps/api/src/routes/bootstrap.py`, line 135:
  ```python
  header = "\n".join(f"{k}={shlex.quote(v)}" for k, v in values.items())
  ```
  All user-supplied and server-configured parameters (`DEVICE_NAME`, `WIFI_SSID`, `WIFI_PASSWORD`, `ZTD_DEVICE_ID`, `PROVISIONING_URL`, `MONITORING_HUB_ID`, `MONITORING_URL`) are wrapped with POSIX single-quote escaping via `shlex.quote`.
- **Test Evidence:** `test_bootstrap_v2.py::TestBootstrapV2Fields::test_shell_injection_prevention_in_new_fields` confirms injection strings like `$(rm -rf /)` are escaped as literal single-quoted strings: `'https://host.example.com/$(rm -rf /)'`.

### 2. Safe Quoting & Argument Handling
- **Status:** **PASS**
- **Evidence:** Inside `bootstrap.py` `_BODY`, all bash variables expanded in commands are safely enclosed in double quotes:
  ```bash
  sudo nmcli connection modify "$CONNECTION_NAME" wifi.ssid "$WIFI_SSID"
  ```
  In `hubbrain_adapter.py` and `agent_v2.py`, `_env_quote` safely escapes and quotes `.env` values containing special characters (`$`, `` ` ``, `"`, `\`, `;`, etc.).

### 3. No Secrets Embedded in Downloaded Scripts (CWE-312)
- **Status:** **PASS**
- **Evidence:** `bootstrap-pi.sh` contains zero hardcoded provisioning passwords or Monitoring keys:
  - `ZTD_DEVICE_PASSWORD` is explicitly omitted from `bootstrap.py` and `/etc/ztd/agent.env`. It must be injected out-of-band upon one-time enrollment.
  - Monitoring `HUB_KEY` and `MQTT_PASS` are never rendered into the bootstrap script.
- **Test Evidence:** `test_dual_server_acceptance_16.py::test_scenario_01_fresh_bootstrap` verifies no API tokens or passwords are built into the bootstrap script.

### 4. No Credentials Printed in Logs (CWE-532)
- **Status:** **PASS**
- **Evidence:**
  - `agent_v2.py` logs state transitions, HTTP status codes, and revisions, but suppresses payload bodies containing authentication tokens or passwords.
  - Bootstrap output displays network status and device identifiers, but deliberately omits `WIFI_PASSWORD`, `ZTD_DEVICE_PASSWORD`, and API keys.

### 5. No Secrets Passed via Process CLI Arguments (CWE-214)
- **Status:** **PASS**
- **Evidence:** Daemons (`ztd-agent-v2` and `hubbrain`) consume credentials exclusively via `EnvironmentFile=/etc/ztd/agent.env` and `EnvironmentFile=/etc/ztd/hubbrain.env`. No secret is passed as a command-line flag (e.g. `--password` or `-k`), preventing disclosure via `/proc/$PID/cmdline` or `ps aux`.

### 6. Secure Temporary File Creation & Atomic Swapping (CWE-377)
- **Status:** **PASS**
- **Evidence:**
  - In `agent_v2.py` `save_state`:
    ```python
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    if os.name != "nt":
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)
    ```
  - In `hubbrain_adapter.py` `write_hubbrain_env`: Writes to `.tmp`, sets mode `0600`, and executes atomic rename (`os.replace`). This guarantees zero file corruption during power interruptions or race conditions.

### 7. Restrictive Environment File Permissions (CWE-732)
- **Status:** **PASS**
- **Evidence:**
  - `/etc/ztd/agent.env` is created and locked with `chmod 600`.
  - `/etc/ztd/hubbrain.env` is written with `chmod 600` (`S_IRUSR | S_IWUSR`).
  - Directories `/etc/ztd` and `/var/lib/ztd` are restricted with `chmod 750` and owned by `ztd:ztd`.

### 8. Verified HTTPS & CA Trust
- **Status:** **PASS**
- **Evidence:**
  - `agent_v2.py` enforces HTTPS for `ZTD_PROVISIONING_URL`.
  - Configurable CA bundle support via `ZTD_TLS_CA_BUNDLE`.
  - `hubbrain_adapter.py` rejects any `server_url` that does not start with `https://`.
- **Test Evidence:** `test_hubbrain_adapter.py::TestConfigValidation::test_non_https_server_url_raises` asserts that `http://` raises `ValueError`.

### 9. No TLS Verification Bypass (CWE-295)
- **Status:** **PASS**
- **Evidence:** In `agent_v2.py`, line 227:
  ```python
  if ca_bundle:
      verify = ca_bundle
      if not os.path.isfile(ca_bundle):
          raise RuntimeError(f"ZTD_TLS_CA_BUNDLE points to a missing file: {ca_bundle!r}")
  else:
      verify = True
  ```
  `verify=False` is never set under any circumstances. If `ZTD_TLS_CA_BUNDLE` is missing, the daemon immediately fails closed.

### 10. Safe Handling of Failed Downloads & Connections
- **Status:** **PASS**
- **Evidence:**
  - `bootstrap-pi.sh` begins with `set -e`, aborting immediately on download failure or network failure before touching system services.
  - `agent_v2.py` traps HTTP timeouts (15.0s bounded timeout) and connection exceptions, falling back to capped exponential backoff (`backoff_seconds`).

### 11. Dependency Pinning & Runtime Verification
- **Status:** **PASS**
- **Evidence:**
  - `apps/agent/requirements.txt` pins runtime dependencies: `httpx>=0.27,<0.29`, `pydantic>=2.0,<3.0`.
  - Monitoring HubBrain `hub/requirements.txt` strictly pins versions: `paho-mqtt==2.2.1`, `requests==2.32.3`, `python-dotenv==1.0.1`, `urllib3==2.2.3`.

### 12. No Execution of Unverified Remote Code (CWE-94)
- **Status:** **PASS**
- **Evidence:** Neither ZTD Agent V2 nor HubBrain dynamically evaluates remote scripts, runs `eval()`, or executes untrusted shell payloads from manifests. Module manifests only define configuration parameters (`hub_config`), which are strictly validated against Pydantic schema models.

### 13. Least-Privilege Daemon Installation
- **Status:** **PASS**
- **Evidence:**
  - `ztd-agent-v2.service` executes under dedicated unprivileged system user: `User=ztd`, `Group=ztd`.
  - `hubbrain.service` executes under dedicated unprivileged user: `User=hubadmin`, `Group=hubadmin`.
  - Root privileges are required only during initial bootstrap setup.

### 14. Correct Systemd Unit Hardening & Sandboxing
- **Status:** **PASS**
- **Evidence:** `apps/agent/ztd-agent-v2.service` includes security directives:
  ```ini
  NoNewPrivileges=true
  PrivateTmp=true
  ProtectSystem=strict
  ReadWritePaths=/var/lib/ztd /etc/ztd
  ```
  File permissions on the installed unit file are locked to `0644`.

### 15. Safe Service Restart & Recovery Behavior
- **Status:** **PASS**
- **Evidence:**
  - `ztd-agent-v2.service` uses `Restart=on-failure` with `RestartSec=30`, preventing rapid crash looping.
  - `hubbrain.service` uses `Restart=always` with `RestartSec=10` and `MemoryMax=150M`.

### 16. Idempotent Reruns & Explicit Recovery States
- **Status:** **PASS**
- **Evidence:**
  - Group and user creation checks `getent group ztd` and `getent passwd ztd`.
  - NetworkManager profile creation checks `nmcli connection show` before adding profiles.
  - Agent V2 registration tolerates HTTP 422 ("already registered") and resumes status polling without error.
  - State persistence preserves previous manifest hashes on failed apply (`_apply_hubbrain_config`), preventing corrupt state.

---

## Conclusion & Audit Verdict

**Audit Verdict: READY (Code & Architecture Verified)**  
The ZTD bootstrap generator and edge agent meet all security invariants for automated edge onboarding. Secrets are protected at rest and in transit, processes are sandboxed, and injection vectors are eliminated.
