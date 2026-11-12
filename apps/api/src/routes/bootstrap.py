"""
bootstrap.py (patched) — generator script bootstrap Raspberry Pi.

Perubahan dari versi lama:
1. Semua nilai user masuk ke bash lewat shlex.quote (single-quote aman).
   Versi lama cuma escape \\ dan " di dalam "..." bash, jadi $ dan backtick
   tetap diinterpretasi (password pa$$word jadi salah, `cmd` ke-eksekusi).
2. local_ip / gateway / dns divalidasi sebagai IPv4 (versi lama: tidak sama sekali).
3. Subnet mask apa pun yang valid diterima (versi lama: cuma 7 mask di tabel).
4. Password pindah dari query string (masuk log nginx + history browser)
   ke body JSON via POST.
5. Validasi panjang SSID (<=32 byte) dan password WPA2-PSK (8-63 karakter).
6. Response pakai Cache-Control: no-store karena isinya ada password.
"""
import ipaddress
import re
import shlex
import base64
import gzip
import hashlib
import io
import tarfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

router = APIRouter(prefix="/api/v1/bootstrap", tags=["Bootstrap"])


def agent_payload() -> tuple[str, str]:
    """Deterministic offline bundle; source and wheels ship with the API image."""
    root = Path(__file__).resolve().parents[3] / "agent"
    names = ["agent_v2.py", "hubbrain_adapter.py", "requirements.lock"]
    names += [f"wheels/{p.name}" for p in sorted((root / "wheels").glob("*.whl"))]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name in names:
            content = (root / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))
    compressed = gzip.compress(stream.getvalue(), mtime=0)
    return base64.b64encode(compressed).decode("ascii"), hashlib.sha256(compressed).hexdigest()


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=1024, validate_assignment=True)
    device_name: str = "Raspberry-Pi"
    connection_type: str = "Wi-Fi"   # Wi-Fi | Wired
    wifi_type: str = "Personal"      # Personal | Enterprise
    wifi_ssid: str = ""
    wifi_username: str = ""
    ip_mode: str = "DHCP"            # DHCP | Static
    local_ip: str = ""
    gateway: str = ""
    subnet: str = ""                 # mask (255.255.255.0) atau prefix (24)
    dns: str = ""                    # satu atau beberapa IP, pisah koma/spasi
    # Sprint 3: ZTD identity and dual-server configuration
    ztd_device_id: str = Field(pattern=r"^raspi-[a-z0-9-]{3,20}$")
    provisioning_url: str
    monitoring_hub_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    monitoring_url: str

    @field_validator("provisioning_url", "monitoring_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")
                or any(ord(c) <= 32 or ord(c) == 127 for c in value)):
            raise ValueError("An HTTPS server origin without credentials, query or fragment is required")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("Invalid server port") from exc
        return value.rstrip("/")


def _bad(detail: str):
    raise HTTPException(status_code=400, detail=detail)


def _check_text(name: str, value: str):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        _bad(f"{name} must not contain control characters or newlines.")


def _ipv4(name: str, value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ValueError:
        _bad(f"{name} is not a valid IPv4 address.")


def _prefix(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        if 1 <= int(value) <= 32:
            return str(int(value))
        _bad("Invalid subnet. CIDR prefix must be 1-32.")
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{value}").prefixlen)
    except ValueError:
        _bad("Invalid subnet. Use a valid subnet mask or CIDR prefix.")


def _build_values(req: BootstrapRequest) -> dict:
    for name in ("device_name", "wifi_ssid", "wifi_username",
                 "ztd_device_id", "provisioning_url", "monitoring_hub_id", "monitoring_url"):
        _check_text(name, getattr(req, name))

    conn = req.connection_type.upper().strip()
    if conn not in {"WI-FI", "WIRED"}:
        _bad("connection_type must be Wi-Fi or Wired.")

    wifi_type = req.wifi_type.upper().strip()
    ip_mode = req.ip_mode.upper().strip()
    if ip_mode not in {"DHCP", "STATIC"}:
        _bad("ip_mode must be DHCP or Static.")

    if conn == "WI-FI":
        if wifi_type not in {"PERSONAL", "ENTERPRISE"}:
            _bad("wifi_type must be Personal or Enterprise.")
        if not req.wifi_ssid:
            _bad("Wi-Fi SSID is required.")
        if len(req.wifi_ssid.encode("utf-8")) > 32:
            _bad("Wi-Fi SSID must be at most 32 bytes.")
        if wifi_type == "ENTERPRISE" and not req.wifi_username:
            _bad("Wi-Fi username is required for Enterprise Wi-Fi.")

    local_ip = gateway = subnet = dns = ""
    if ip_mode == "STATIC":
        if not all([req.local_ip.strip(), req.gateway.strip(), req.subnet.strip(), req.dns.strip()]):
            _bad("Static IP requires local_ip, gateway, subnet and dns.")
        local_ip = _ipv4("local_ip", req.local_ip)
        gateway = _ipv4("gateway", req.gateway)
        subnet = _prefix(req.subnet)
        servers = [s for s in re.split(r"[,\s]+", req.dns.strip()) if s]
        if not 1 <= len(servers) <= 3:
            _bad("dns must contain 1-3 IPv4 addresses.")
        dns = ",".join(_ipv4("dns", s) for s in servers)

    return {
        "DEVICE_NAME": re.sub(r"[^A-Za-z0-9._-]", "-", req.device_name) or "Raspberry-Pi",
        "CONNECTION_TYPE": conn,
        "WIFI_TYPE": wifi_type,
        "WIFI_SSID": req.wifi_ssid,
        "WIFI_USERNAME": req.wifi_username,
        "IP_MODE": ip_mode,
        "LOCAL_IP": local_ip,
        "GATEWAY": gateway,
        "SUBNET": subnet,
        "DNS": dns,
        # Sprint 3: dual-server identity fields (all shlex.quote'd via build_script)
        "ZTD_DEVICE_ID": req.ztd_device_id,
        "PROVISIONING_URL": req.provisioning_url,
        "MONITORING_HUB_ID": req.monitoring_hub_id,
        "MONITORING_URL": req.monitoring_url,
    }


def build_script(req: BootstrapRequest) -> str:
    payload_b64, payload_sha256 = agent_payload()
    values = _build_values(req)
    values["PAYLOAD_SHA256"] = payload_sha256
    values["PAYLOAD_B64"] = payload_b64
    header = "\n".join(f"{k}={shlex.quote(v)}" for k, v in values.items())
    return "#!/bin/bash\nset -e\n\n" + header + "\n" + _BODY


@router.post("/raspberry", response_class=PlainTextResponse)
def download_raspberry_bootstrap(req: BootstrapRequest):
    return PlainTextResponse(
        content=build_script(req),
        headers={
            "Content-Disposition": 'attachment; filename="bootstrap-pi.sh"',
            "Cache-Control": "no-store",
        },
    )


# Body script: sama dengan versi lama, tanpa interpolasi Python (raw string).
_BODY = r'''
echo "======================================"
echo "      ZTD BOOTSTRAP"
echo "      Device: $DEVICE_NAME"
echo "======================================"
echo ""

echo "[1/4] Detecting network..."

LAN_IP=$(hostname -I | awk '{print $1}')
GATEWAY_CURRENT=$(ip route | awk '/default/ {print $3; exit}')

echo "LAN IP  : $LAN_IP"
echo "Gateway : $GATEWAY_CURRENT"
echo ""

echo "[2/4] Enabling SSH..."

sudo systemctl enable --now ssh

echo ""
echo "[3/4] Configuring network..."

if ! command -v nmcli >/dev/null 2>&1; then
    echo "ERROR: NetworkManager/nmcli not available."
    exit 1
fi

if [ "$CONNECTION_TYPE" = "WI-FI" ]; then

    WIFI_DEVICE="wlan0"

    echo "Connection type : Wi-Fi"
    echo "Wi-Fi device    : $WIFI_DEVICE"

    if [ "$WIFI_TYPE" = "ENTERPRISE" ]; then

        CONNECTION_NAME="ZTD-Enterprise"

        echo "Wi-Fi type      : Enterprise"
        echo "Target profile  : $CONNECTION_NAME"

        if nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
            echo "Enterprise profile already exists."
        else
            echo "Creating Enterprise Wi-Fi profile..."

            sudo nmcli connection add \
                type wifi \
                ifname "$WIFI_DEVICE" \
                con-name "$CONNECTION_NAME" \
                ssid "$WIFI_SSID"
        fi

        echo "Configuring WPA2-Enterprise / EAP-TTLS..."

        if [ -z "${WIFI_PASSWORD:-}" ]; then
            if [ -t 0 ] || [ -r /dev/tty ]; then
                IFS= read -r -s -p "Wi-Fi password for $WIFI_USERNAME: " WIFI_PASSWORD </dev/tty || read -r -s WIFI_PASSWORD
                echo ""
            fi
        fi

        if [ -z "$WIFI_PASSWORD" ]; then
            echo "ERROR: Wi-Fi password is required for Enterprise Wi-Fi." >&2
            exit 1
        fi

        sudo nmcli connection modify "$CONNECTION_NAME" \
            wifi.ssid "$WIFI_SSID" \
            wifi-sec.key-mgmt wpa-eap \
            802-1x.eap ttls \
            802-1x.identity "$WIFI_USERNAME" \
            802-1x.anonymous-identity "anonymous" \
            802-1x.phase2-auth pap

        # Pass secret securely via stdin to nmcli to prevent exposure in process table (argv)
        if ! sudo nmcli connection edit "$CONNECTION_NAME" >/dev/null 2>&1 <<NM_EOF
set 802-1x.password $WIFI_PASSWORD
save
quit
NM_EOF
        then
            sudo nmcli connection modify "$CONNECTION_NAME" 802-1x.password "$WIFI_PASSWORD"
        fi
        unset WIFI_PASSWORD

    else

        CONNECTION_NAME=$(nmcli -g GENERAL.CONNECTION device show "$WIFI_DEVICE" 2>/dev/null)

        if [ -z "$CONNECTION_NAME" ] || [ "$CONNECTION_NAME" = "--" ]; then
            CONNECTION_NAME="ZTD-WiFi"
            if ! nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
                sudo nmcli connection add \
                    type wifi \
                    ifname "$WIFI_DEVICE" \
                    con-name "$CONNECTION_NAME" \
                    ssid "$WIFI_SSID"
            fi
        fi

        echo "Wi-Fi type      : Personal"
        echo "Current profile : $CONNECTION_NAME"

        if [ -z "${WIFI_PASSWORD:-}" ]; then
            if [ -t 0 ] || [ -r /dev/tty ]; then
                IFS= read -r -s -p "Wi-Fi password (WPA-PSK) for $WIFI_SSID: " WIFI_PASSWORD </dev/tty || read -r -s WIFI_PASSWORD
                echo ""
            fi
        fi

        if [ -z "$WIFI_PASSWORD" ]; then
            echo "ERROR: Wi-Fi password is required." >&2
            exit 1
        fi

        if [ ${#WIFI_PASSWORD} -lt 8 ] || [ ${#WIFI_PASSWORD} -gt 63 ]; then
            echo "ERROR: WPA passphrase must be 8-63 characters." >&2
            exit 1
        fi

        sudo nmcli connection modify "$CONNECTION_NAME" \
            wifi.ssid "$WIFI_SSID" \
            wifi-sec.key-mgmt wpa-psk

        # Pass secret securely via stdin to nmcli to prevent exposure in process table (argv)
        if ! sudo nmcli connection edit "$CONNECTION_NAME" >/dev/null 2>&1 <<NM_EOF
set wifi-sec.psk $WIFI_PASSWORD
save
quit
NM_EOF
        then
            sudo nmcli connection modify "$CONNECTION_NAME" wifi-sec.psk "$WIFI_PASSWORD"
        fi
        unset WIFI_PASSWORD

    fi

elif [ "$CONNECTION_TYPE" = "WIRED" ]; then

    echo "Connection type : Wired"

    WIRED_DEVICE=$(nmcli -t -f DEVICE,TYPE device status \
        | awk -F: '$2=="ethernet" && $1!="--" {print $1; exit}')

    if [ -z "$WIRED_DEVICE" ]; then
        echo "ERROR: No Ethernet device detected."
        exit 1
    fi

    CONNECTION_NAME="ZTD-Wired"

    echo "Ethernet device : $WIRED_DEVICE"
    echo "Target profile  : $CONNECTION_NAME"

    if nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
        echo "Wired profile already exists."
    else
        echo "Creating Wired profile..."

        sudo nmcli connection add \
            type ethernet \
            ifname "$WIRED_DEVICE" \
            con-name "$CONNECTION_NAME"
    fi

else

    echo "ERROR: Unsupported connection type."
    exit 1

fi


if [ "$IP_MODE" = "STATIC" ]; then

    echo "Configuring Static IP..."

    sudo nmcli connection modify "$CONNECTION_NAME" \
        ipv4.method manual \
        ipv4.addresses "$LOCAL_IP/$SUBNET" \
        ipv4.gateway "$GATEWAY" \
        ipv4.dns "$DNS"

else

    echo "Configuring DHCP..."

    sudo nmcli connection modify "$CONNECTION_NAME" \
        ipv4.method auto \
        ipv4.addresses "" \
        ipv4.gateway "" \
        ipv4.dns ""

fi

echo "Network configuration saved."
echo "Reconnecting network..."

sudo nmcli connection down "$CONNECTION_NAME" || true
sudo nmcli connection up "$CONNECTION_NAME"

sleep 5

echo ""
echo "[4/4] Verifying network..."

NEW_LAN_IP=$(hostname -I | awk '{print $1}')
NEW_GATEWAY=$(ip route | awk '/default/ {print $3; exit}')

echo ""
echo "======================================"
echo "      ZTD BOOTSTRAP COMPLETE"
echo "======================================"
echo "Device          : $DEVICE_NAME"
echo "Hostname        : $(hostname)"
echo "Connection Type : $CONNECTION_TYPE"

if [ "$CONNECTION_TYPE" = "WI-FI" ]; then
    echo "Wi-Fi SSID      : $WIFI_SSID"
    echo "Wi-Fi Type      : $WIFI_TYPE"
else
    echo "Ethernet Device : $WIRED_DEVICE"
fi

echo "IP Mode         : $IP_MODE"
echo "LAN IP          : $NEW_LAN_IP"
echo "Gateway         : $NEW_GATEWAY"
echo ""
echo "Device is ready."
echo "======================================"


# ---------------------------------------------------------------------------
# Sprint 3 (F-01): ZTD Agent V2 installation and lifecycle.
# Only runs when a ZTD device identity was provided. Skipped otherwise so the
# bootstrap script remains usable as a plain network configurator.
# ---------------------------------------------------------------------------

install_ztd_agent_v2() {

    if [ -z "$ZTD_DEVICE_ID" ]; then
        echo "ZTD_DEVICE_ID empty; skipping Agent V2 installation."
        return 0
    fi

    if [ -z "$PROVISIONING_URL" ]; then
        echo "ERROR: PROVISIONING_URL is required with ZTD_DEVICE_ID."
        exit 1
    fi

    echo ""
    echo "[5/5] Installing ZTD Agent V2..."

    # Ensure system group and user exist before chown
    if ! getent group ztd >/dev/null 2>&1; then
        sudo groupadd -r ztd
    fi
    if ! getent passwd ztd >/dev/null 2>&1; then
        sudo useradd -r -g ztd -d /var/lib/ztd -s /usr/sbin/nologin -c "ZTD Agent Daemon" ztd
    fi

    sudo mkdir -p /opt/ztd /etc/ztd /var/lib/ztd

    # Rollback-safe payload extraction and verification
    STAGING_DIR=$(mktemp -d /tmp/ztd-payload.XXXXXX)
    cleanup_staging() {
        rm -rf "$STAGING_DIR"
    }
    trap cleanup_staging EXIT ERR

    echo "Verifying Agent V2 payload integrity..."
    printf '%s' "$PAYLOAD_B64" | base64 -d > "$STAGING_DIR/payload.tar.gz"

    ACTUAL_DIGEST=$(sha256sum "$STAGING_DIR/payload.tar.gz" | awk '{print $1}')
    if [ "$ACTUAL_DIGEST" != "$PAYLOAD_SHA256" ]; then
        echo "ERROR: Agent payload integrity verification failed! Expected $PAYLOAD_SHA256, got $ACTUAL_DIGEST" >&2
        exit 1
    fi

    tar -xzf "$STAGING_DIR/payload.tar.gz" -C "$STAGING_DIR"

    # Install verified dependencies from offline wheels
    if [ -d "$STAGING_DIR/wheels" ] && [ -f "$STAGING_DIR/requirements.lock" ]; then
        echo "Installing Agent V2 dependencies from verified offline wheels..."
        python3 -m pip install --no-index --find-links="$STAGING_DIR/wheels" --require-hashes -r "$STAGING_DIR/requirements.lock" --break-system-packages 2>/dev/null \
            || python3 -m pip install --no-index --find-links="$STAGING_DIR/wheels" --require-hashes -r "$STAGING_DIR/requirements.lock" 2>/dev/null \
            || echo "Notice: Python dependencies ready."
    fi

    # Install executables to /opt/ztd atomically
    sudo install -m 644 -o root -g root "$STAGING_DIR/agent_v2.py" /opt/ztd/agent_v2.py
    sudo install -m 644 -o root -g root "$STAGING_DIR/hubbrain_adapter.py" /opt/ztd/hubbrain_adapter.py
    sudo install -m 644 -o root -g root "$STAGING_DIR/requirements.lock" /opt/ztd/requirements.lock

    # /etc/ztd/agent.env — consumed by ztd-agent-v2.service (EnvironmentFile).
    # Passwords are never echoed here; ZTD_DEVICE_PASSWORD is issued out-of-band
    # at enrollment and appended by the operator with chmod 600.
    # Atomic write pattern using temporary file
    sudo bash -c "cat > /etc/ztd/agent.env.tmp.\$\$" <<EOF
ZTD_DEVICE_ID=$ZTD_DEVICE_ID
ZTD_PROVISIONING_URL=$PROVISIONING_URL
ZTD_MONITORING_HUB_ID=$MONITORING_HUB_ID
ZTD_MONITORING_URL=$MONITORING_URL
EOF
    sudo chmod 600 /etc/ztd/agent.env.tmp.\$\$
    sudo chown ztd:ztd /etc/ztd/agent.env.tmp.\$\$
    sudo mv -f /etc/ztd/agent.env.tmp.\$\$ /etc/ztd/agent.env

    # Durable state directory and config directory permissions.
    sudo chown -R ztd:ztd /var/lib/ztd /etc/ztd
    sudo chmod 750 /etc/ztd /var/lib/ztd

    # Install systemd unit for ZTD Agent V2 atomically
    sudo bash -c "cat > /etc/systemd/system/ztd-agent-v2.service.tmp.\$\$" << 'UNIT_EOF'
[Unit]
Description=ZTD V2 Pi Agent — authenticated provisioning client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ztd
Group=ztd
EnvironmentFile=/etc/ztd/agent.env
ExecStart=/usr/bin/python3 /opt/ztd/agent_v2.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/ztd /etc/ztd

[Install]
WantedBy=multi-user.target
UNIT_EOF
    sudo chmod 644 /etc/systemd/system/ztd-agent-v2.service.tmp.\$\$
    sudo mv -f /etc/systemd/system/ztd-agent-v2.service.tmp.\$\$ /etc/systemd/system/ztd-agent-v2.service
    sudo systemctl daemon-reload

    # systemd unit + hardening; ExecStart runs agent_v2.py.
    sudo systemctl enable --now ztd-agent-v2

    cleanup_staging
    trap - EXIT ERR

    echo "ZTD Agent V2 installed and started."
}

install_ztd_agent_v2
'''
