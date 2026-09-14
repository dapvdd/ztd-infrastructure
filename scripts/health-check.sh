#!/bin/bash

check() {
    if [ "$1" = "0" ]; then
        echo "✅ $2"
    else
        echo "❌ $2"
    fi
}

echo "======================================"
echo "          ZTD HEALTH CHECK"
echo "======================================"

systemctl is-active --quiet docker
check $? "Docker"

docker inspect -f '{{.State.Health.Status}}' ztd-db 2>/dev/null | grep -q healthy
check $? "PostgreSQL"

docker inspect -f '{{.State.Health.Status}}' ztd-nginx 2>/dev/null | grep -q healthy
check $? "Nginx"

systemctl is-active --quiet ssh.socket
check $? "SSH"

sudo ufw status | grep -q "Status: active"
check $? "UFW"

systemctl is-active --quiet tailscaled
check $? "Tailscale"

curl -fsS http://localhost/ >/dev/null
check $? "HTTP :80"

echo "======================================"
