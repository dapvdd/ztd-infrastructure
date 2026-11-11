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

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/bootstrap", tags=["Bootstrap"])


class BootstrapRequest(BaseModel):
    device_name: str = "Raspberry-Pi"
    connection_type: str = "Wi-Fi"   # Wi-Fi | Wired
    wifi_type: str = "Personal"      # Personal | Enterprise
    wifi_ssid: str = ""
    wifi_username: str = ""
    wifi_password: str = ""
    ip_mode: str = "DHCP"            # DHCP | Static
    local_ip: str = ""
    gateway: str = ""
    subnet: str = ""                 # mask (255.255.255.0) atau prefix (24)
    dns: str = ""                    # satu atau beberapa IP, pisah koma/spasi
    # Sprint 3: ZTD identity and dual-server configuration
    ztd_device_id: str = ""          # e.g. raspi-abc123; injected as ZTD_DEVICE_ID
    provisioning_url: str = ""       # Provisioning VPS base URL
    monitoring_hub_id: str = ""      # HubBrain identity: HUB_ID
    monitoring_url: str = ""         # Monitoring VPS base URL


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
    for name in ("device_name", "wifi_ssid", "wifi_username", "wifi_password",
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
        if not req.wifi_password:
            _bad("Wi-Fi password is required.")
        if wifi_type == "PERSONAL" and not 8 <= len(req.wifi_password) <= 63:
            _bad("Wi-Fi password must be 8-63 characters for WPA2-Personal.")
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
        "WIFI_PASSWORD": req.wifi_password,
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
    values = _build_values(req)
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

        sudo nmcli connection modify "$CONNECTION_NAME" \
            wifi.ssid "$WIFI_SSID" \
            wifi-sec.key-mgmt wpa-eap \
            802-1x.eap ttls \
            802-1x.identity "$WIFI_USERNAME" \
            802-1x.anonymous-identity "anonymous" \
            802-1x.password "$WIFI_PASSWORD" \
            802-1x.phase2-auth pap

    else

        CONNECTION_NAME=$(nmcli -g GENERAL.CONNECTION device show "$WIFI_DEVICE" 2>/dev/null)

        if [ -z "$CONNECTION_NAME" ] || [ "$CONNECTION_NAME" = "--" ]; then
            echo "ERROR: No active Wi-Fi connection found on $WIFI_DEVICE."
            exit 1
        fi

        echo "Wi-Fi type      : Personal"
        echo "Current profile : $CONNECTION_NAME"

        sudo nmcli connection modify "$CONNECTION_NAME" \
            wifi.ssid "$WIFI_SSID" \
            wifi-sec.key-mgmt wpa-psk \
            wifi-sec.psk "$WIFI_PASSWORD"

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

    sudo mkdir -p /opt/ztd /etc/ztd /var/lib/ztd

    # /etc/ztd/agent.env — consumed by ztd-agent-v2.service (EnvironmentFile).
    # Passwords are never echoed here; ZTD_DEVICE_PASSWORD is issued out-of-band
    # at enrollment and appended by the operator with chmod 600.
    sudo bash -c "cat > /etc/ztd/agent.env" <<EOF
ZTD_DEVICE_ID=$ZTD_DEVICE_ID
ZTD_PROVISIONING_URL=$PROVISIONING_URL
ZTD_MONITORING_HUB_ID=$MONITORING_HUB_ID
ZTD_MONITORING_URL=$MONITORING_URL
EOF
    sudo chmod 600 /etc/ztd/agent.env

    # Durable state directory owned by the agent user.
    sudo chown -R ztd:ztd /var/lib/ztd /etc/ztd

    # systemd unit + hardening; ExecStart runs agent_v2.py.
    sudo systemctl enable --now ztd-agent-v2

    echo "ZTD Agent V2 installed and started."
}

install_ztd_agent_v2
'''