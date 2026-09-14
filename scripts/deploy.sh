#!/bin/bash

set -e

PROJECT_DIR="/home/david/ztd-server"

echo "======================================"
echo "          ZTD DEPLOYMENT"
echo "======================================"

cd "$PROJECT_DIR"

echo
echo "[1/4] Validating Docker Compose..."
docker compose config -q
echo "✅ Compose configuration valid"

echo
echo "[2/4] Starting containers..."
docker compose up -d
echo "✅ Containers started"

echo
echo "[3/4] Waiting for services..."
sleep 5

echo
echo "[4/4] Running health check..."
"$PROJECT_DIR/scripts/health-check.sh"

echo
echo "======================================"
echo "       DEPLOYMENT COMPLETED"
echo "======================================"
