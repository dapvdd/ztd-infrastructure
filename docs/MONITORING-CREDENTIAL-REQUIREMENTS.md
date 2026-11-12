# Monitoring HubGate & HubBrain Credential Requirements

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-12  
**Governing Subsystems:**
- Monitoring HubGate V5 (FastAPI backend on `100.108.98.30` / `10.33.102.172`)
- Monitoring HubBrain V5 (`hub/main.py` on Raspberry Pi)
- ZTD Agent V2 (`apps/agent/agent_v2.py`)

---

## 1. Architectural Boundary: Why Automated Issuance is Blocked

The external Monitoring platform (HubGate V5) owns the authority over hub registration and cryptographic identity.

In HubGate V5:
- The pairing endpoint `POST /api/hubs/pair` requires an incoming `X-Hub-Key` header matching `HUB_BOOTSTRAP_KEY` and returns `202 Accepted` (`{"status": "pending_approval", "hub_id": ...}`).
- It **does not generate or issue** a `HUB_ID` or `HUB_KEY` down to the client.
- The hub remains inactive (`is_active=False`) until a human Monitoring administrator explicitly issues an approval via `POST /api/hubs/{hub_id}/approve` (which requires admin authentication).
- Therefore, automated credential generation by ZTD is architecturally impossible and explicitly forbidden by contract.

In `apps/agent/hubbrain_adapter.py`:
```python
def issue_hubgate_credentials(provisioning_url: str, device_id: str) -> None:
    raise NotImplementedError(
        "HubGate credential issuance is not supported by the ZTD system. "
        "HUB_ID and HUB_KEY must be manually provisioned by a Monitoring VPS admin."
    )
```
Any attempt to automate this would require embedding Monitoring admin credentials inside the Raspberry Pi bootstrap script, which would violate CWE-259 (Hardcoded Credentials) and compromise the Monitoring production server.

---

## 2. Inventory of Required Credentials

To successfully start HubBrain and forward telemetry to HubGate V5, the edge gateway requires the following credentials:

| Variable Name | Required Scope | Secret Level | Purpose & Format | Storage Location on Pi |
|---|---|---|---|---|
| `HUB_ID` | Monitoring HubGate | Public ID | Hub identifier (e.g. `hs109rs-hub-01`). Must match `hub_table.hub_id` in HubGate database. | `/etc/ztd/hubbrain.env` |
| `HUB_KEY` | Monitoring HubGate | **High Secret** | 64-character hexadecimal API token. Sent as `X-Hub-Key` over HTTPS. | `/etc/ztd/hubbrain.env` / `/etc/ztd/agent.env` |
| `MQTT_USER` | Local Mosquitto | Low Secret | Local broker username. Default: `hubadmin`. | `/etc/ztd/hubbrain.env` |
| `MQTT_PASS` | Local Mosquitto | **High Secret** | PBKDF2 hashed password for Mosquitto client connection. Must NOT match default placeholder. | `/etc/ztd/hubbrain.env` / `/etc/ztd/agent.env` |
| `SERVER_URL` | Monitoring HubGate | Address | HTTPS upstream endpoint (e.g. `https://100.108.98.30/api/iot`). | `/etc/ztd/hubbrain.env` |
| `TLS_CERT_PATH` | Monitoring HubGate | Public Cert | Path to server TLS certificate (`cert.crt`) for upstream pinned verification. | `/etc/ztd/cert.crt` |

### Weak Credential Rejection Gate
HubBrain V5 `hub/main.py` enforces runtime startup assertions. The daemon **aborts immediately** if `MQTT_PASS` or `HUB_KEY` match known weak defaults:
- Weak `MQTT_PASS`: `414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1`
- Weak `HUB_KEY`: `70999354dda0638bbbe04b2e6d26e9f6484168193cdfdbcd517bbdf608134ee4`

Production startup strictly fails unless genuine, non-default credentials are provided.

---

## 3. Operator Provisioning Workflow

```
[Monitoring Admin Console]
       |
       | 1. POST /api/admin/hubs (HUB_ID, HUB_NAME, HUB_KEY)
       v
[HubGate Database]  <--- Hub Registered (is_active=True)
       |
       | 2. Hand off HUB_ID & HUB_KEY out-of-band to Onboarding Engineer
       v
[Onboarding Engineer]
       |
       | 3. Set ZTD_HUB_KEY & ZTD_MQTT_PASS in /etc/ztd/agent.env (chmod 600)
       |    or directly in /etc/ztd/hubbrain.env
       v
[Raspberry Pi Gateways]
       |
       | 4. Agent V2 fetches manifest -> validates config -> restarts hubbrain.service
       v
[HubBrain Online & Streaming]
```

### Detailed Steps:

1. **Hub Registration on Monitoring Server:**
   The Monitoring administrator executes an authenticated API call on HubGate:
   ```bash
   curl -X POST https://100.108.98.30/api/admin/hubs \
     -H "Content-Type: application/json" \
     -H "Cookie: session_id=<admin_session>" \
     -d '{
       "HUB_ID": "hs109rs-hub-01",
       "HUB_NAME": "Gedung DTEDI Lantai 1",
       "HUB_KEY": "f8a7e3b9c2d1e0f4a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5"
     }'
   ```

2. **Generate Local Mosquitto Password on Pi:**
   ```bash
   sudo mosquitto_passwd -c /etc/mosquitto/passwd hubadmin
   # Or using the repository script:
   python tools/generate_mosquitto_passwd.py --user hubadmin --password "<STRONG_PASSWORD>"
   ```

3. **Inject Secrets into Raspberry Pi Environment:**
   Append the issued credentials to `/etc/ztd/agent.env`:
   ```bash
   sudo bash -c 'cat >> /etc/ztd/agent.env' << 'EOF'
   ZTD_HUB_KEY=f8a7e3b9c2d1e0f4a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5
   ZTD_MQTT_PASS=<STRONG_PASSWORD>
   EOF
   sudo chmod 600 /etc/ztd/agent.env
   ```

4. **Service Verification:**
   ```bash
   sudo systemctl restart ztd-agent-v2
   sudo journalctl -u ztd-agent-v2 -n 20 --no-pager
   ```
   Verify output displays: `HubBrain .env written to /etc/ztd/hubbrain.env`.

---

## 4. Credential Rotation Procedures

When rotating `HUB_KEY` or `MQTT_PASS`:

1. **Server-Side Rotation:**
   The Monitoring administrator runs the official CLI utility:
   ```bash
   python tools/rotate_credentials.py --target-db server/hubgatev5.db --update-env server/.env --hub-id hs109rs-hub-01
   ```
   This generates a new 64-character hexadecimal key and updates `hub_table`.

2. **Edge-Side Update:**
   Update `ZTD_HUB_KEY` in `/etc/ztd/agent.env` on the Pi:
   ```bash
   sudo sed -i 's/^ZTD_HUB_KEY=.*/ZTD_HUB_KEY=<NEW_HUB_KEY>/' /etc/ztd/agent.env
   sudo systemctl restart ztd-agent-v2
   ```

3. **Zero-Data-Loss Guarantee:**
   During key rotation or brief upstream auth rejection (HTTP 401), HubBrain buffers all incoming telemetry in `edge_cache.db` (SQLite WAL). Once the new key is active, the replay worker resumes and drains the backlog with zero loss of sensor history.
