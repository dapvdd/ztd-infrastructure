# Raspberry Pi Edge Gateway Installation & Operations Runbook

**Document Version:** 1.0.0  
**Effective Date:** 2026-11-12  
**Target Hardware:** Raspberry Pi 3B+, 4B, 5  
**Target OS:** Raspberry Pi OS Lite (64-bit), Debian 12 (Bookworm)  
**Governing Subsystems:** ZTD Provisioning V2 & Monitoring HubBrain / HubGate V5  

---

## 1. Prerequisites & Preparation

### Hardware Requirements
- Raspberry Pi (3B+, 4B, or 5) with at least 1GB RAM.
- MicroSD card (16 GB minimum, High Endurance / Class 10 recommended).
- 5V DC power supply meeting official Raspberry Pi specifications.
- Network interface: Active Ethernet link or 2.4GHz / 5GHz Wi-Fi.

### Network Requirements
Before deployment, verify outbound connectivity for the following targets:
- **ZTD Provisioning VPS:** Port 80 / 443 (e.g. `100.105.163.126`).
- **Monitoring HubGate V5:** Port 443 (e.g. `100.108.98.30` or `10.33.102.172`).
- **Local Broker:** Loopback / Local Subnet TCP Port 1883 (Mosquitto).

### Base OS Flashing & Configuration
1. Flash **Raspberry Pi OS Lite (64-bit)** using the official Raspberry Pi Imager.
2. In Advanced Options (Gear Icon):
   - Set Hostname (e.g., `ztd-gateway-01`).
   - Enable SSH with public-key or secure password authentication.
   - Configure Wi-Fi credentials if deploying headlessly over wireless.
   - Set locale and timezone (`Asia/Jakarta` / `WIB`).
3. Boot the Raspberry Pi, obtain its IP address via DHCP lease or console, and SSH in:
   ```bash
   ssh pi@<pi-ip-address>
   ```
4. Update initial packages and ensure standard tooling is installed:
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   sudo apt-get install -y curl ca-certificates network-manager git
   ```

---

## 2. Downloading & Verifying Bootstrap Script

The bootstrap script generator dynamically renders a tailored, self-contained shell script that prepares the operating system, installs dependencies, configures systemd daemons, and locks down permissions.

### Option A: Generating via Provisioning API (Automated)
If generating directly from the Provisioning server:
```bash
curl -fsSL "http://100.105.163.126/api/v2/bootstrap/pi?device_name=ztd-gateway-01&device_id=pi-edge-01&provisioning_url=http://100.105.163.126&monitoring_hub_id=hs109rs-hub-01&monitoring_url=https://100.108.98.30" -o /tmp/bootstrap-pi.sh
```

### Option B: Local Repository Build
If deploying from a local repository copy:
```bash
python3 -c "
from apps.api.src.routes.bootstrap import generate_pi_bootstrap_script
script = generate_pi_bootstrap_script(
    device_name='ztd-gateway-01',
    device_id='pi-edge-01',
    provisioning_url='http://100.105.163.126',
    monitoring_hub_id='hs109rs-hub-01',
    monitoring_url='https://100.108.98.30'
)
with open('/tmp/bootstrap-pi.sh', 'w') as f:
    f.write(script)
"
```

### Verification Prior to Execution
Always inspect the downloaded script before executing it with root privileges:
```bash
head -n 35 /tmp/bootstrap-pi.sh
chmod +x /tmp/bootstrap-pi.sh
```
Verify that all variables (`DEVICE_NAME`, `ZTD_DEVICE_ID`, `PROVISIONING_URL`, `MONITORING_HUB_ID`, `MONITORING_URL`) are safely quoted with single quotes (`'...'`) without shell interpolation.

---

## 3. Bootstrap Script Execution

Execute the script as `root`:
```bash
sudo bash /tmp/bootstrap-pi.sh
```

### What the Bootstrap Script Executes (Execution Flow):
1. **Safety Flags:** Runs with `set -e` so any failure terminates execution cleanly.
2. **Package Installation:** Installs `python3-venv`, `python3-pip`, `mosquitto`, `mosquitto-clients`, `network-manager`.
3. **Local Mosquitto Setup:**
   - Deploys `/etc/mosquitto/conf.d/ztd.conf` (disables anonymous access, binds `0.0.0.0:1883`).
   - Creates `/etc/mosquitto/passwd` and `/etc/mosquitto/acl`.
   - Enables and starts `mosquitto.service`.
4. **Dedicated System User Creation:**
   - Checks `getent group ztd || groupadd -r ztd`.
   - Checks `getent passwd ztd || useradd -r -g ztd -s /usr/sbin/nologin -d /var/lib/ztd -c "ZTD Edge Agent" ztd`.
5. **Directory Creation & Permissions:**
   - Creates `/etc/ztd` (mode `0750`, owned by `root:ztd`).
   - Creates `/var/lib/ztd` (mode `0750`, owned by `ztd:ztd`).
6. **Agent Runtime Isolation:**
   - Initializes virtual environment in `/opt/ztd-agent/venv`.
   - Copies `apps/agent` code and installs `httpx`, `pydantic`.
7. **Environment File Generation:**
   - Writes `/etc/ztd/agent.env` with mode `0600`, owned by `root:ztd`.
8. **Systemd Service Unit Deployment:**
   - Writes `/etc/systemd/system/ztd-agent-v2.service` with sandbox flags (`NoNewPrivileges=true`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/ztd /etc/ztd`).
   - Executes `systemctl daemon-reload`.
   - Executes `systemctl enable --now ztd-agent-v2`.

---

## 4. Credential Injection & Local Configuration

### Step 4.1: Configure ZTD Agent Credentials
Edit `/etc/ztd/agent.env` with appropriate root privileges:
```bash
sudo nano /etc/ztd/agent.env
```
Ensure the following variables are defined:
```ini
ZTD_DEVICE_ID=pi-edge-01
ZTD_DEVICE_PASSWORD=sec-device-auth-token-44281
PROVISIONING_URL=http://100.105.163.126
MONITORING_HUB_ID=hs109rs-hub-01
MONITORING_URL=https://100.108.98.30
ZTD_HUB_KEY=f4c90e803a58e653da9d2d85b14115e4785b4f0b2f5dca77c1d1a6e9270bb931
ZTD_MQTT_PASS=94f8b417e9bb499b90c1f6d7285a22bb0b6ca6bf6f1122aef9127d142b781cf0
```

Verify restrictive permissions:
```bash
sudo chown root:ztd /etc/ztd/agent.env
sudo chmod 0640 /etc/ztd/agent.env
```

### Step 4.2: Configure Monitoring HubBrain Daemon
If running the external HubBrain service independently or via adapter:
1. Clone the Monitoring repository to `/opt/hubbrain`:
   ```bash
   sudo git clone https://github.com/mochmizan/proyek-monitoring-dtedi.git /opt/hubbrain
   cd /opt/hubbrain/hub
   sudo python3 -m venv venv
   sudo ./venv/bin/pip install -r requirements.txt
   ```
2. Verify `/etc/ztd/hubbrain.env` (automatically written by `hubbrain_adapter.py` or configured manually):
   ```ini
   SERVER_URL=https://100.108.98.30/api/iot
   MQTT_BROKER=127.0.0.1
   MQTT_PORT=1883
   MQTT_USER=hubadmin
   MQTT_PASS=94f8b417e9bb499b90c1f6d7285a22bb0b6ca6bf6f1122aef9127d142b781cf0
   HUB_ID=hs109rs-hub-01
   HUB_KEY=f4c90e803a58e653da9d2d85b14115e4785b4f0b2f5dca77c1d1a6e9270bb931
   OFFLINE_BUFFER_DB=/var/lib/ztd/hub_buffer.db
   ```
3. Set ownership and file mode:
   ```bash
   sudo chown root:ztd /etc/ztd/hubbrain.env
   sudo chmod 0640 /etc/ztd/hubbrain.env
   ```

---

## 5. Service Status Verification

### 5.1 Mosquitto Local Broker
Check that Mosquitto is active and listening on port 1883:
```bash
sudo systemctl status mosquitto
ss -tulpn | grep 1883
```
Test local message exchange:
```bash
# Terminal 1: Subscribe
mosquitto_sub -h 127.0.0.1 -p 1883 -u hubadmin -P "94f8b417e9bb499b90c1f6d7285a22bb0b6ca6bf6f1122aef9127d142b781cf0" -t "hs109rs/#" -v

# Terminal 2: Publish test telemetry
mosquitto_pub -h 127.0.0.1 -p 1883 -u esp_node_01 -P "node_pass_token" -t "hs109rs/esp_node_01/telemetry" -m '{"temperature": 25.4, "humidity": 60.1}'
```

### 5.2 ZTD Agent V2 Daemon
Verify the agent service is active:
```bash
sudo systemctl status ztd-agent-v2
```
Inspect recent journal entries:
```bash
journalctl -u ztd-agent-v2 -n 50 --no-pager
```
Expected log entries:
- `Registered device pi-edge-01 with status=pending (or approved)`
- `Status poll: approved=True, manifest_hash=...`
- `HubBrain config synchronized successfully to /etc/ztd/hubbrain.env`

Check persisted state file:
```bash
sudo cat /var/lib/ztd/state.json
```

### 5.3 HubBrain Daemon
Verify HubBrain status:
```bash
sudo systemctl status hubbrain
```
Check journal logs:
```bash
journalctl -u hubbrain -n 50 --no-pager
```
Expected log entries:
- `Connecting to MQTT broker 127.0.0.1:1883...`
- `Subscribed to topic hs109rs/#`
- `HubBrain running loop...`

---

## 6. Troubleshooting & Recovery Runbook

### Issue A: Agent fails with HTTP 401 Unauthorized
- **Symptom:** Journal reports `Registration/Status check returned 401`.
- **Cause:** `ZTD_DEVICE_PASSWORD` in `/etc/ztd/agent.env` does not match the Provisioning database record for `ZTD_DEVICE_ID`.
- **Fix:** Update `/etc/ztd/agent.env` with the issued registration secret and restart:
  ```bash
  sudo systemctl restart ztd-agent-v2
  ```

### Issue B: HubBrain crashes with `RuntimeError: MQTT_PASS cannot be empty or default`
- **Symptom:** HubBrain daemon enters rapid crashloop (`code=exited, status=1/FAILURE`).
- **Cause:** `MQTT_PASS` or `HUB_KEY` in `/etc/ztd/hubbrain.env` matches the insecure template default hash or is blank.
- **Fix:** Generate fresh 64-char hex strings and update `/etc/ztd/agent.env` and `/etc/ztd/hubbrain.env`:
  ```bash
  openssl rand -hex 32
  sudo systemctl restart ztd-agent-v2
  ```

### Issue C: Monitoring Server returns HTTP 403 Forbidden / Not Approved
- **Symptom:** HubBrain reports `Failed to push telemetry: 403 Forbidden`.
- **Cause:** Hub has paired with HubGate but has not yet been approved by an administrator via `POST /api/hubs/{hub_id}/approve`.
- **Fix:** Contact Monitoring server administrator to approve `hs109rs-hub-01`. HubBrain will buffer telemetry in SQLite WAL (`/var/lib/ztd/hub_buffer.db`) until approval is granted.

### Issue D: Full Reset & Re-Bootstrap
To wipe local configuration and perform a clean re-installation:
```bash
sudo systemctl stop ztd-agent-v2 hubbrain mosquitto
sudo rm -rf /etc/ztd /var/lib/ztd /opt/ztd-agent /etc/systemd/system/ztd-agent-v2.service
sudo systemctl daemon-reload
sudo bash /tmp/bootstrap-pi.sh
```
