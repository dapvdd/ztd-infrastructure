#!/bin/bash

echo "======================================"
echo "        ZTD SERVER STATUS"
echo "======================================"

echo
echo "[SYSTEM]"
echo "Hostname : $(hostname)"
echo "Uptime   : $(uptime -p)"
echo "Date     : $(date)"

echo
echo "[RESOURCE]"
echo "Disk:"
df -h / | tail -1

echo
echo "Memory:"
free -h

echo
echo "[DOCKER]"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "[UFW]"
sudo ufw status | head -6

echo
echo "[SSH]"
systemctl is-active ssh

echo
echo "[TAILSCALE]"
tailscale status --self

echo
echo "======================================"
echo "             STATUS DONE"
echo "======================================"
