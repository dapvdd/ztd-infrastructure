import json
import logging
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

from src.config import settings
from src.database import SessionLocal
from src.models import Device, Telemetry

logger = logging.getLogger("mqtt_listener")
logger.setLevel(logging.INFO)

def process_heartbeat(token: str, payload_data: dict):
    """Update device status to ONLINE and record last_seen timestamp."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.device_token == token).first()
        if not device:
            logger.warning(f"Heartbeat received for unknown device token: {token[:8]}...")
            return

        device.status = "ONLINE"
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Heartbeat: Device '{device.name or device.mac_address}' is ONLINE.")
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
    finally:
        db.close()

def process_telemetry(token: str, payload_data: dict):
    """Store sensor/system telemetry in the telemetry table."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.device_token == token).first()
        if not device:
            logger.warning(f"Telemetry received for unknown token: {token[:8]}...")
            return

        # Record telemetry row
        telemetry_entry = Telemetry(
            device_id=device.id,
            cpu_temp=payload_data.get("cpu_temp"),
            ram_usage=payload_data.get("ram_usage"),
            uptime_seconds=payload_data.get("uptime_seconds"),
            payload=payload_data
        )
        db.add(telemetry_entry)

        # Keep device status fresh
        device.status = "ONLINE"
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Telemetry recorded for '{device.mac_address}': CPU {payload_data.get('cpu_temp')}°C")
    except Exception as e:
        logger.error(f"Error processing telemetry: {e}")
    finally:
        db.close()

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("MQTT Listener connected to broker successfully.")
        # Subscribe to heartbeats and telemetry for all tokens using '+' wildcard
        client.subscribe("devices/+/heartbeat", qos=1)
        client.subscribe("devices/+/telemetry", qos=0)
        logger.info("Subscribed to 'devices/+/heartbeat' and 'devices/+/telemetry'")
    else:
        logger.error(f"Failed to connect to MQTT broker, return code: {rc}")

def on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        if len(topic_parts) != 3:
            return

        _, token, message_type = topic_parts
        payload = json.loads(msg.payload.decode("utf-8"))

        if message_type == "heartbeat":
            process_heartbeat(token, payload)
        elif message_type == "telemetry":
            process_telemetry(token, payload)
    except Exception as e:
        logger.error(f"Error parsing MQTT message on {msg.topic}: {e}")

# Global client instance
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt_listener():
    """Start the non-blocking background MQTT client thread."""
    try:
        logger.info(f"Connecting to MQTT broker at {settings.MQTT_HOST}:{settings.MQTT_PORT}...")
        mqtt_client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.warning(f"Could not connect to MQTT broker on startup ({e}). Retrying in background...")

def stop_mqtt_listener():
    """Stop the MQTT background client."""
    try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        logger.info("MQTT Listener disconnected cleanly.")
    except Exception:
        pass
