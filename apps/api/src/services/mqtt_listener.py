import json
import logging
from datetime import datetime, timedelta, timezone
import paho.mqtt.client as mqtt
from sqlalchemy import or_, update

from src.config import settings
from src.database import SessionLocal
from src.models import Device, Telemetry, DeploymentLog
from src.services.device_metrics import METRICS_KIND, normalize_metrics_payload
from src.services.presence import TOUCH_MIN_INTERVAL_SECONDS, touch_device

logger = logging.getLogger("mqtt_listener")
logger.setLevel(logging.INFO)

def process_register(device_id: str, payload: dict):
    """Auto-discovery: Daftarkan perangkat otomatis saat pesan register diterima."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        now = datetime.now(timezone.utc)
        if not device:
            device = Device(
                id=device_id,
                hostname=payload.get("hostname"),
                status="ONLINE",
                last_seen=now
            )
            db.add(device)
            logger.info(f"[Auto-Discovery] Perangkat baru terdaftar: {device_id} ({payload.get('hostname')})")
        else:
            device.status = "ONLINE"
            device.hostname = payload.get("hostname", device.hostname)
            device.last_seen = now
        db.commit()
    except Exception as e:
        logger.error(f"Error pada register {device_id}: {e}")
    finally:
        db.close()

def process_heartbeat(device_id: str, payload: dict):
    """Menandai perangkat aktif dengan satu UPDATE (tanpa deployment log).

    Nilai ditulis paling sering sekali per TOUCH_MIN_INTERVAL_SECONDS supaya
    duplikat QoS 1 / telemetry yang berdekatan tidak menambah beban tulis.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=TOUCH_MIN_INTERVAL_SECONDS)
        result = db.execute(
            update(Device)
            .where(Device.id == device_id)
            .where(or_(Device.last_seen.is_(None), Device.last_seen < cutoff))
            .values(status="ONLINE", last_seen=now)
        )
        if result.rowcount:
            db.commit()
        else:
            db.rollback()
    except Exception as e:
        logger.error(f"Error pada heartbeat {device_id}: {e}")
        db.rollback()
    finally:
        db.close()

def process_metrics(device_id: str, payload: dict):
    """Store one validated device-metrics v1 sample without a deployment log.

    Metrics share the existing telemetry table/JSONB payload, so no schema
    migration is required. ``cpu_temp`` is deliberately left NULL: metrics rows
    must never be mixed into the temperature history chart. Duplicate QoS 1
    deliveries with the same ``measured_at`` are coalesced.
    """
    normalized, errors = normalize_metrics_payload(payload, expected_device_id=device_id)
    if normalized is None:
        logger.warning(f"Metrik perangkat ditolak {device_id}: {', '.join(errors)}")
        return

    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            # Inventory is still created by register/telemetry discovery. A metrics
            # message must not silently invent an unknown device.
            logger.warning(f"Metrik dari perangkat tidak dikenal diabaikan: {device_id}")
            return

        last = (
            db.query(Telemetry)
            .filter(
                Telemetry.device_id == device_id,
                Telemetry.payload["kind"].astext == METRICS_KIND,
            )
            .order_by(Telemetry.recorded_at.desc())
            .first()
        )
        if last is not None and isinstance(last.payload, dict):
            if last.payload.get("measured_at") == normalized["measured_at"]:
                return

        db.add(
            Telemetry(
                device_id=device_id,
                cpu_temp=None,
                ram_usage=None,
                uptime_seconds=normalized["uptime_seconds"],
                payload=normalized,
            )
        )
        touch_device(device)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error menyimpan metrik perangkat {device_id}: {e}")
    finally:
        db.close()


def process_deployment(device_id: str, payload: dict):
    """Mencatat status instalasi modul ke deployment_logs."""
    db = SessionLocal()
    try:
        log_entry = DeploymentLog(
            device_id=device_id,
            stage=payload.get("module", "unknown"),
            status=payload.get("status", "unknown"),
            log_output=payload.get("detail", "")
        )
        db.add(log_entry)
        db.commit()
        logger.info(f"Deployment [{device_id}]: {payload.get('module')} -> {payload.get('status')}")
    except Exception as e:
        logger.error(f"Error mencatat deployment log {device_id}: {e}")
    finally:
        db.close()

def process_temperature(room_id: str, payload: dict):
    """Mencatat data suhu dari modul temperature ke tabel telemetry."""
    db = SessionLocal()
    try:
        device_id = payload.get("device_id")
        if not device_id:
            return

        telemetry_entry = Telemetry(
            device_id=device_id,
            cpu_temp=payload.get("temperature"),
            payload=payload
        )
        db.add(telemetry_entry)

        # Update last_seen dan room_id jika belum terisi
        device = db.query(Device).filter(Device.id == device_id).first()
        if device:
            # Telemetry remains a liveness fallback until every edge agent sends
            # its own heartbeat; the write is coalesced with heartbeats.
            touch_device(device)
            if not device.room_id:
                device.room_id = room_id

        db.commit()
    except Exception as e:
        logger.error(f"Error menyimpan telemetri suhu: {e}")
    finally:
        db.close()

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("MQTT Listener terhubung ke Broker Mosquitto.")
        client.subscribe("iot/device/+/register", qos=1)
        client.subscribe("iot/device/+/heartbeat", qos=1)
        client.subscribe("iot/device/+/metrics", qos=1)
        client.subscribe("iot/device/+/deployment", qos=1)
        client.subscribe("iot/room/+/temperature", qos=0)
    else:
        logger.error(f"Gagal terhubung ke MQTT Broker, code: {rc}")

def on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        payload = json.loads(msg.payload.decode("utf-8"))

        if topic_parts[0] == "iot" and topic_parts[1] == "device":
            device_id = topic_parts[2]
            action = topic_parts[3]
            if action == "register":
                process_register(device_id, payload)
            elif action == "heartbeat":
                process_heartbeat(device_id, payload)
            elif action == "metrics":
                process_metrics(device_id, payload)
            elif action == "deployment":
                process_deployment(device_id, payload)

        elif topic_parts[0] == "iot" and topic_parts[1] == "room":
            room_id = topic_parts[2]
            metric = topic_parts[3]
            if metric == "temperature":
                process_temperature(room_id, payload)
    except Exception as e:
        logger.error(f"Error parsing MQTT {msg.topic}: {e}")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# F-07: the broker disables anonymous access, so the listener must present
# credentials from the operator's .env. Empty MQTT_USER keeps the old
# anonymous behavior for local/test brokers that allow it.
if settings.MQTT_USER:
    mqtt_client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASS)

def publish_device_config(device_id: str, config_dict: dict):
    """Mengirim Desired State ke Raspi sebagai RETAINED MESSAGE."""
    topic = f"iot/device/{device_id}/config"
    payload = json.dumps(config_dict)
    mqtt_client.publish(topic, payload, qos=1, retain=True)
    logger.info(f"Published retained config ke {topic}: {payload}")

def start_mqtt_listener():
    try:
        mqtt_client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.warning(f"Gagal koneksi awal MQTT ({e}), akan mencoba di background...")

def stop_mqtt_listener():
    try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    except Exception:
        pass
