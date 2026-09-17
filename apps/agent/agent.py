import os
import time
import json
import socket
import logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEVICE_TOKEN = os.getenv("DEVICE_TOKEN")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 30))

if not DEVICE_TOKEN:
    logging.error("DEVICE_TOKEN environment variable is missing! Exiting.")
    exit(1)

TOPIC_HEARTBEAT = f"devices/{DEVICE_TOKEN}/heartbeat"
TOPIC_TELEMETRY = f"devices/{DEVICE_TOKEN}/telemetry"

def get_cpu_temp() -> float:
    """Read CPU temperature from Raspberry Pi thermal zone."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(float(f.read().strip()) / 1000.0, 2)
    except Exception:
        # Fallback for non-Pi or local simulated testing
        return 42.5

def get_system_stats() -> dict:
    """Collect basic system stats."""
    uptime_seconds = 0
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = int(float(f.readline().split()[0]))
    except Exception:
        pass

    return {
        "hostname": socket.gethostname(),
        "cpu_temp": get_cpu_temp(),
        "uptime_seconds": uptime_seconds,
        "timestamp": time.time()
    }

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info("Connected to MQTT Broker successfully!")
        # Immediately publish first heartbeat on connect
        publish_heartbeat(client)
    else:
        logging.error(f"Failed to connect to MQTT Broker, return code: {rc}")

def publish_heartbeat(client):
    payload = json.dumps({"token": DEVICE_TOKEN, "status": "ONLINE", "timestamp": time.time()})
    client.publish(TOPIC_HEARTBEAT, payload, qos=1)
    logging.info(f"Published heartbeat to {TOPIC_HEARTBEAT}")

def publish_telemetry(client):
    stats = get_system_stats()
    stats["token"] = DEVICE_TOKEN
    payload = json.dumps(stats)
    client.publish(TOPIC_TELEMETRY, payload, qos=0)
    logging.info(f"Published telemetry: {payload}")

def main():
    logging.info(f"Starting IoT Edge Agent for token: {DEVICE_TOKEN[:8]}...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            logging.warning(f"MQTT Broker not reachable at {MQTT_HOST}:{MQTT_PORT} ({e}). Retrying in 5s...")
            time.sleep(5)

    client.loop_start()

    try:
        while True:
            publish_heartbeat(client)
            publish_telemetry(client)
            time.sleep(HEARTBEAT_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Stopping IoT Edge Agent...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
