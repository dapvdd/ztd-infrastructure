# ZTD & Monitoring Dual-Server System Contract

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-12  
**Classification:** Engineering Architecture & Security Specification  
**Governing Repositories:**
- ZTD Infrastructure: `sprint3-remediation/edge-integration` (commit `692221e` / `e4afaa3`)
- ZTD Dashboard: `sprint3-remediation/edge-dashboard` (commit `a60b9a3`)
- Monitoring HubGate & HubBrain V5: `mochmizan/proyek-monitoring-dtedi` (commit `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`)

---

## 1. Architectural Boundaries & System Topology

The Zero Touch Deployment (ZTD) Raspberry Pi gateway acts as an edge appliance interfacing with two strictly independent, non-overlapping backends:

```
+-------------------------------------------------------------------------------------------------+
|                                    RASPBERRY PI EDGE GATEWAY                                    |
|                                                                                                 |
|   +-------------------------------------+             +-------------------------------------+   |
|   |         ZTD Agent V2 Daemon         |             |       SMSB HubBrain V5 Gateway      |   |
|   |         (ztd-agent-v2.service)      |             |         (hubbrain.service)          |   |
|   |         User: ztd, Group: ztd       |             |     User: hubadmin, Group: hubadmin |   |
|   |     Config: /etc/ztd/agent.env      |             |   Config: /etc/ztd/hubbrain.env     |   |
|   +------------------+------------------+             +------------------+------------------+   |
|                      |                                                   |                      |
|                      | Basic Auth                                        | X-Hub-ID / X-Hub-Key |
|                      | (Device ID : Password)                            | (HTTPS TLS Pinned)   |
|                      v                                                   v                      |
+----------------------|---------------------------------------------------|----------------------+
                       |                                                   |
                       v                                                   v
+---------------------------------------------+     +---------------------------------------------+
|          ZTD PROVISIONING VPS               |     |           MONITORING HUBGATE V5             |
| Host: 100.105.163.126                       |     | Host: 100.108.98.30 / 10.33.102.172         |
| Owner: ZTD Team                             |     | Owner: External Monitoring Team             |
| Scope: OS Bootstrap, Device Approval,       |     | Scope: Sensor Telemetry Ingestion,          |
| Module Manifests, Configuration Snapshots   |     | Whitelist Sync, Downlink Node Commands      |
+---------------------------------------------+     +---------------------------------------------+
```

### Server Independence Guarantees
1. **Network Disjunction:** The two systems run on distinct infrastructure with independent DNS/IPs and separate trust roots.
2. **Failure Isolation:** Unavailability of the ZTD Provisioning VPS does NOT interrupt HubBrain telemetry forwarding or local MQTT bridging. Conversely, Monitoring HubGate outages or HTTP 429/500 responses do NOT compromise ZTD Agent V2 registration, polling, or status reporting.
3. **Database Separation:** Neither server connects to, queries, or replicates data from the other's database.

---

## 2. Identity Namespace Formalization

To prevent identity collision and cross-domain pollution, four distinct identifier namespaces are strictly defined:

| Identifier | Format / Syntax | Owning Authority | Scope & Consumption | Example |
|---|---|---|---|---|
| `ZTD_DEVICE_ID` | `raspi-[a-z0-9]{6,12}` | ZTD Provisioning VPS | Pi OS hostname, agent registration, provisioning status | `raspi-a1b2c3` |
| `MONITORING_HUB_ID` | `[a-z0-9_-]+` | Monitoring Team (HubGate) | HubBrain `X-Hub-ID` header, HubGate `hub_table.hub_id` | `hs109rs-hub-01` |
| `ESP_NODE_ID` | `^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$` | Hardware Manufacturer / ESP MAC | Local MQTT broker whitelist, `dev_table.dev_id` | `48:55:19:E3:64:2C` |
| `SENSOR_ID` | `[A-Z0-9_]+` | Monitoring Firmware Specification | Specific telemetry metric key within JSON payload | `TEMPERATURE`, `HUMIDITY`, `PLN_V` |

### Deterministic Identity Mapping Rules
1. **No Silent Equivalence:** `ZTD_DEVICE_ID` MUST NEVER be used as `MONITORING_HUB_ID`. A single ZTD device can physically host a HubBrain instance, but their identities belong to separate control planes.
2. **Manifest Echo Invariant:** When Provisioning returns a signed manifest containing the non-secret `hub_config` block, `hub_config.hub_id` must match `MONITORING_HUB_ID`.
3. **Firmware Display Name Derivation:** For ESP nodes, human-readable display names are deterministically derived from node type and the last 4 hexadecimal characters of the MAC address:
   $$\text{DEV\_NAME} = \text{DEV\_TYPE} + \text{"-"} + \text{MAC}[-5:-3] + \text{MAC}[-2:]$$
   *(e.g., MAC `48:55:19:E3:64:2C` with type `TS` produces `TS-642C`)*.
4. **Single-Gateway Ownership:** An `ESP_NODE_ID` (MAC) must be registered under exactly one gateway hub. Cross-gateway node collisions are rejected by HubGate validation.

---

## 3. Communication & Authentication Protocols

### Channel 1: ZTD Provisioning Client (Agent V2)
- **Protocol:** HTTPS (TLS 1.2 or 1.3)
- **Port:** 443 (Nginx reverse-proxy terminating to `127.0.0.1:8000` Uvicorn)
- **Authentication:** HTTP Basic Authentication
  - Username: `ZTD_DEVICE_ID`
  - Password: `ZTD_DEVICE_PASSWORD` (issued once upon admin enrollment, stored in `/etc/ztd/agent.env` mode 0600)
- **TLS Trust:** Validated against system CA trust store or custom bundle via `ZTD_TLS_CA_BUNDLE`. Insecure fallback (`verify=False`) is explicitly prohibited by code assertion.
- **Endpoints:**
  - `POST /api/v2/provisioning/register` — Initial device registration (`{"hostname": ZTD_DEVICE_ID}`)
  - `GET /api/v2/provisioning/status` — Approval lifecycle polling
  - `GET /api/v2/provisioning/manifest` — Cryptographically hashed module manifest (accessible only when `APPROVED`)

### Channel 2: Monitoring Edge Ingestion (HubBrain V5)
- **Protocol:** HTTPS (TLS pinned via `TLS_CERT_PATH`)
- **Port:** 443 (Nginx terminating to `127.0.0.1:8000` Uvicorn)
- **Authentication:** Custom HTTP Headers
  - `X-Hub-ID`: `MONITORING_HUB_ID`
  - `X-Hub-Key`: 64-character hexadecimal API Key (Argon2id / timing-safe compared on server)
- **Endpoints:**
  - `POST /api/iot` — Single whitelisted telemetry payload
  - `POST /api/iot/batch` — Bulk telemetry ingestion (up to 1000 items)
  - `GET /api/devices` — Device whitelist synchronization (every 30 seconds)
  - `GET /api/hub/commands` — Downlink actuator command polling (every 2 seconds)
  - `POST /api/hub/commands/{id}/delivered` — Command execution delivery acknowledgement
  - `POST /api/iot/unapproved` — Rate-limited alert for unknown rogue node detection

### Channel 3: Local Edge Ingestion (ESP to Pi Broker)
- **Protocol:** MQTT 3.1.1 / TCP
- **Port:** 1883 (Local Mosquitto on `127.0.0.1` / `192.168.72.242` AP interface; NO public WAN exposure)
- **Authentication:** Mosquitto Password File (`/etc/mosquitto/passwd` PBKDF2)
  - HubBrain username: `hubadmin`
  - Password: `MQTT_PASS`
- **Topics:**
  - Ingestion: `hs109rs/#` (subdivided into `hs109rs/ts/data`, `hs109rs/ats/data`, `hs109rs/ac/data`)
  - Downlink: `{hub_name}/{dev_type}/command` (e.g. `hs109rs/ac/command`)

---

## 4. Lifecycle States & Configuration Application

```
+---------------+     Bootstrap     +-----------------+     Wait for     +-------------------+
|  UNENROLLED   | ----------------> | PENDING_APPROVAL| ---------------> |     APPROVED      |
| (Bare RasPi)  |                   | (Registered V2) |     Admin Auth   | (Manifest Valid)  |
+---------------+                   +-----------------+                  +---------+---------+
                                                                                   |
                                                                                   | Fetch Manifest
                                                                                   v
+---------------+      Offline      +-----------------+     Atomic Apply +-------------------+
| WAL BUFFERING | <---------------- | ACTIVE_TELEMETRY| <--------------- | HUBBRAIN CONFIGURE|
| (SQLite WAL)  |     Outage        | (Edge Ingestion)|                  | (/etc/ztd/hubbrain|
+---------------+                   +-----------------+                  +-------------------+
```

### Stage 1: Bootstrap & Identity Generation
1. Administrator accesses ZTD Provisioning UI and submits a bootstrap request with desired network parameters, `ZTD_DEVICE_ID`, `PROVISIONING_URL`, `MONITORING_HUB_ID`, and `MONITORING_URL`.
2. Server validates all fields (IPv4, CIDR, printable characters) and returns a shell-quoted `bootstrap-pi.sh`.
3. Script executes on Pi:
   - Sets up system group `ztd` and system user `ztd`.
   - Creates `/etc/ztd` (mode 750) and `/var/lib/ztd` (mode 750).
   - Writes `/etc/ztd/agent.env` (mode 600) with endpoint URLs and device identifiers.
   - Installs `/etc/systemd/system/ztd-agent-v2.service` (mode 644) and reloads systemd.
   - Enables and activates `ztd-agent-v2.service`.

### Stage 2: Provisioning Enrollment & Approval
1. Administrator executes out-of-band device enrollment via ZTD BFF (`POST /api/dashboard/v2/provisioning/devices/{id}/enroll`), generating a 256-bit one-time device password.
2. Operator appends `ZTD_DEVICE_PASSWORD=<secret>` to `/etc/ztd/agent.env` on the Pi.
3. `agent_v2.py` daemon starts its loop, issues `POST /api/v2/provisioning/register`, and enters the `PENDING` polling cycle.
4. Administrator approves the device in the ZTD Dashboard (`POST /api/dashboard/v2/provisioning/devices/{id}/approve`).

### Stage 3: Manifest Retrieval & Atomic Application
1. On next poll, `agent_v2.py` detects status `APPROVED` with valid expiration timestamp.
2. Agent requests `GET /api/v2/provisioning/manifest`.
3. Agent computes `manifest_hash = sha256(canonical_json(manifest))`.
4. If hash differs from persistent `/var/lib/ztd/state.json`:
   - Extracts non-secret `hub_config` (`hub_id`, `server_url`, `mqtt_host`, `mqtt_port`, `mqtt_user`).
   - Merges edge-local secrets from environment: `ZTD_HUB_KEY` and `ZTD_MQTT_PASS`.
   - Validates merged config via `hubbrain_adapter.validate_hub_config` (validating HTTPS scheme, port ranges 1–65535, non-empty keys).
   - Writes `/etc/ztd/hubbrain.env.tmp` (mode 600) and atomically replaces `/etc/ztd/hubbrain.env`.
   - Commits `manifest_hash`, `revision`, and `applied_at` to `/var/lib/ztd/state.json`.

---

## 5. Blast-Radius & Fault Isolation Matrix

| Failure Mode | Impact on ZTD Provisioning | Impact on Monitoring Telemetry | Recovery Behavior |
|---|---|---|---|
| **Provisioning VPS Down / Unreachable** | Status polling enters exponential backoff (5s–300s). Manifest updates paused. | **Zero impact.** HubBrain continues local MQTT ingestion and forwards to Monitoring HubGate without interruption. | Agent automatically resumes polling upon Provisioning VPS recovery. |
| **Monitoring HubGate Down / Unreachable** | **Zero impact.** Agent V2 remains `APPROVED` and continues regular manifest lifecycle. | HubBrain fails upstream HTTPS POST (timeout 5s). Automatically buffers payloads in SQLite WAL (`MAX_PENDING_ROWS=20000`). | Upon recovery, WAL replay thread drains backlog at 0.35s pacing with preserved `_hub_created_at` timestamps. |
| **Local Mosquitto MQTT Crash** | Zero impact. Agent V2 is unaffected. | Ingestion thread drops connection; enters backoff reconnect. ESP nodes retry publishing. | Systemd restarts Mosquitto (`Restart=always`); HubBrain reconnects within 10s. |
| **Invalid Provisioning Password** | Agent registration / status returns HTTP 401. State preserved as `PENDING`. | Zero impact. HubBrain operates independently. | Operator injects corrected password in `/etc/ztd/agent.env`; Agent succeeds on next loop iteration. |
| **Invalid Monitoring HUB_KEY** | Zero impact. Provisioning operates normally. | HubGate rejects telemetry with HTTP 401. HubBrain quarantined from upstream. | Monitoring admin rotates key via `tools/rotate_credentials.py`; operator updates `ZTD_HUB_KEY` on edge. |
| **Corrupted Manifest Payload** | `_apply_hubbrain_config` raises validation error; previous state and hash preserved. | HubBrain continues running with previous valid configuration. | Provisioning admin publishes corrected revision; agent re-applies atomically. |

---

## 6. Verification & Compliance Standards

1. **RFC 2104 / FIPS 198-1:** Cryptographic SHA-256 manifest integrity verification.
2. **NIST SP 800-63B:** Minimum 128-bit entropy for server-generated tokens and passwords.
3. **CWE-78 / CWE-88 Protection:** Zero raw string interpolation in generated shell scripts; all variables wrapped with POSIX single-quote escaping via `shlex.quote`.
4. **CWE-538 Protection:** No passwords, tokens, or private keys written into world-readable files or printed to `stdout`/`stderr` logs.
5. **Least Privilege:** Daemons execute under dedicated system users (`ztd` and `hubadmin`), with systemd sandbox directives (`NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, bounded `ReadWritePaths`).
