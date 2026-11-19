#!/bin/bash

set -e

echo "======================================"
echo "      ZTD BOOTSTRAP"
echo "======================================"

echo
echo "[1/4] Detecting network..."

LAN_IP=$(hostname -I | awk '{print $1}')
GATEWAY=$(ip route | awk '/default/ {print $3; exit}')

echo "LAN IP  : $LAN_IP"
echo "Gateway : $GATEWAY"

echo
echo "[2/4] Installing Tailscale..."

if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi

echo
echo "[3/4] Connecting to Tailscale..."

echo "Tailscale must be configured by the provisioning system."

echo
echo "[4/4] Checking SSH..."

sudo systemctl enable --now ssh

echo
echo "======================================"
echo "       ZTD BOOTSTRAP COMPLETE"
echo "======================================"
echo "LAN IP      : $LAN_IP"
echo "Tailscale IP: $(tailscale ip -4 2>/dev/null || echo 'NOT CONNECTED')"
