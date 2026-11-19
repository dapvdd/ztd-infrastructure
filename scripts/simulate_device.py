#!/usr/bin/env python3
"""
ZTD Edge Device Simulator.

Simulates an edge Raspberry Pi sending MQTT messages to the ZTD broker:
1. Registration (iot/device/<id>/register)
2. Heartbeat (iot/device/<id>/heartbeat)
3. Temperature Telemetry (iot/room/<room>/temperature)
4. System Metrics v1 (iot/device/<id>/metrics)
5. Deployment Log (iot/device/<id>/deployment)

Can run as a one-shot burst or in a continuous loop.
Falls back seamlessly to mosquitto_pub if paho-mqtt is not installed.
"""

import argparse
import json
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
    HAS_PAHO = True
except ImportError:
    HAS_PAHO = False


def publish_mqtt(host: str, port: int, topic: str, payload: dict, qos: int = 1) -> bool:
    payload_str = json.dumps(payload)
    if HAS_PAHO:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2 if hasattr(mqtt, "CallbackAPIVersion") else None)
            client.connect(host, port, 60)
            client.publish(topic, payload_str, qos=qos)
            client.disconnect()
            return True
        except Exception as e:
            print(f"[!] Paho publish failed ({e}), falling back to mosquitto_pub...")

    if shutil.which("mosquitto_pub"):
        cmd = [
            "mosquitto_pub",
            "-h", host,
            "-p", str(port),
            "-t", topic,
            "-m", payload_str,
            "-q", str(qos),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[✗] mosquitto_pub error: {res.stderr.strip()}", file=sys.stderr)
            return False
        return True

    print("[✗] Error: Neither paho-mqtt nor mosquitto_pub is available.", file=sys.stderr)
    return False


def send_register(host: str, port: int, device_id: str, hostname: str):
    topic = f"iot/device/{device_id}/register"
    payload = {"hostname": hostname}
    ok = publish_mqtt(host, port, topic, payload, qos=1)
    if ok:
        print(f"[✓] Register published -> {topic}: {payload}")


def send_heartbeat(host: str, port: int, device_id: str):
    topic = f"iot/device/{device_id}/heartbeat"
    payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
    ok = publish_mqtt(host, port, topic, payload, qos=1)
    if ok:
        print(f"[✓] Heartbeat published -> {topic}")


def send_temperature(host: str, port: int, device_id: str, room_id: str, temp: float):
    topic = f"iot/room/{room_id}/temperature"
    payload = {
        "device_id": device_id,
        "temperature": round(temp, 2),
        "temperature_unit": "C",
        "schema_version": 2,
        "room_id": room_id,
    }
    ok = publish_mqtt(host, port, topic, payload, qos=0)
    if ok:
        print(f"[✓] Temperature published -> {topic}: {payload['temperature']}°C")


def send_metrics(host: str, port: int, device_id: str, uptime: int, temp: float):
    topic = f"iot/device/{device_id}/metrics"
    now_iso = datetime.now(timezone.utc).isoformat()
    cpu_util = round(random.uniform(5.0, 35.0), 1)
    load_1m = round(random.uniform(0.1, 0.9), 2)
    payload = {
        "schema_version": 1,
        "kind": "device_metrics",
        "device_id": device_id,
        "measured_at": now_iso,
        "network": {
            "local_ip": "192.168.1.120",
            "tailscale_ip": "100.105.163.220",
            "public_ip": None,
            "public_ip_status": "not_configured",
        },
        "cpu": {
            "utilization_percent": cpu_util,
            "utilization_window_seconds": 60,
            "load_average_1m": load_1m,
            "load_average_5m": round(load_1m * 0.85, 2),
            "load_average_15m": round(load_1m * 0.70, 2),
        },
        "uptime_seconds": uptime,
        "cpu_temperature": {
            "value": round(temp, 2),
            "unit": "C",
            "source": "thermal_zone0",
        },
        "unavailable": {
            "network.public_ip": "not_configured",
        },
    }
    ok = publish_mqtt(host, port, topic, payload, qos=1)
    if ok:
        print(f"[✓] Metrics v1 published -> {topic}: CPU {cpu_util}%, Uptime {uptime}s")


def send_deployment_log(host: str, port: int, device_id: str, module: str, status: str = "success"):
    topic = f"iot/device/{device_id}/deployment"
    payload = {
        "module": module,
        "status": status,
        "detail": f"Module '{module}' status updated to {status} by simulator.",
    }
    ok = publish_mqtt(host, port, topic, payload, qos=1)
    if ok:
        print(f"[✓] Deployment log published -> {topic}: {module} -> {status}")


def main():
    parser = argparse.ArgumentParser(description="ZTD Edge Device Simulator")
    parser.add_argument("--device-id", default="raspi-sim-01", help="Device ID (default: raspi-sim-01)")
    parser.add_argument("--hostname", default="edge-simulator", help="Hostname (default: edge-simulator)")
    parser.add_argument("--room-id", default="lab-sim", help="Room ID (default: lab-sim)")
    parser.add_argument("--host", default="localhost", help="MQTT Broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker port (default: 1883)")
    parser.add_argument(
        "--action",
        choices=["all", "register", "heartbeat", "metrics", "temperature", "deploy-log", "loop"],
        default="all",
        help="Action to perform (default: all)",
    )
    parser.add_argument("--temp", type=float, default=42.5, help="Base temperature (default: 42.5)")
    parser.add_argument("--interval", type=int, default=10, help="Loop interval in seconds (default: 10)")

    args = parser.parse_args()

    print("=" * 55)
    print("         ZTD EDGE DEVICE SIMULATOR")
    print("=" * 55)
    print(f"Target Broker : {args.host}:{args.port}")
    print(f"Device ID     : {args.device_id} ({args.hostname})")
    print(f"Room ID       : {args.room_id}")
    print(f"Action        : {args.action}")
    print("=" * 55)

    base_uptime = 3600

    if args.action == "register":
        send_register(args.host, args.port, args.device_id, args.hostname)
    elif args.action == "heartbeat":
        send_heartbeat(args.host, args.port, args.device_id)
    elif args.action == "temperature":
        send_temperature(args.host, args.port, args.device_id, args.room_id, args.temp)
    elif args.action == "metrics":
        send_metrics(args.host, args.port, args.device_id, base_uptime, args.temp)
    elif args.action == "deploy-log":
        send_deployment_log(args.host, args.port, args.device_id, "temperature", "success")
        send_deployment_log(args.host, args.port, args.device_id, "memory", "success")
    elif args.action == "all":
        print("\n[*] Sending full initial registration burst...")
        send_register(args.host, args.port, args.device_id, args.hostname)
        time.sleep(0.5)
        send_deployment_log(args.host, args.port, args.device_id, "temperature", "success")
        send_deployment_log(args.host, args.port, args.device_id, "memory", "success")
        time.sleep(0.5)
        send_temperature(args.host, args.port, args.device_id, args.room_id, args.temp)
        time.sleep(0.5)
        send_metrics(args.host, args.port, args.device_id, base_uptime, args.temp)
        time.sleep(0.5)
        send_heartbeat(args.host, args.port, args.device_id)
        print("\n[✓] All simulation packets sent successfully.")
    elif args.action == "loop":
        print("\n[*] Registering device...")
        send_register(args.host, args.port, args.device_id, args.hostname)
        send_deployment_log(args.host, args.port, args.device_id, "temperature", "success")
        send_deployment_log(args.host, args.port, args.device_id, "memory", "success")
        print(f"\n[*] Entering telemetry loop (Ctrl+C to stop, interval: {args.interval}s)...")
        elapsed = 0
        try:
            while True:
                current_temp = args.temp + random.uniform(-1.5, 2.0)
                uptime = base_uptime + elapsed
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Tick:")
                send_heartbeat(args.host, args.port, args.device_id)
                send_temperature(args.host, args.port, args.device_id, args.room_id, current_temp)
                send_metrics(args.host, args.port, args.device_id, uptime, current_temp)
                time.sleep(args.interval)
                elapsed += args.interval
        except KeyboardInterrupt:
            print("\n[*] Simulator stopped by user.")


if __name__ == "__main__":
    main()
