from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database import get_db
from src.models import Device, Telemetry, DeploymentLog
from src.schemas import DeviceResponse, DeviceConfigPayload, DashboardSummary
from src.config import settings
from src.services.device_metrics import (
    METRICS_KIND,
    build_metrics_response,
    temperature_metadata,
)
from src.services.mqtt_listener import publish_device_config
from src.services.presence import ONLINE_WINDOW_SECONDS, device_status

router = APIRouter(prefix="/api/v1/devices", tags=["Devices & Monitoring"])


def _serialize_device(device, now, db: Optional[Session] = None):
    """API shape with the status computed from last_seen (backend source of truth).

    ``devices.status`` in the database is never aged by the listener, so it must not
    be returned as-is; doing so would report a dead device as ONLINE forever.
    """
    data = {
        "id": device.id,
        "hostname": device.hostname,
        "room_id": device.room_id,
        "ip_address": device.ip_address,
        "status": device_status(device.last_seen, now),
        "created_at": device.created_at,
        "last_seen": device.last_seen,
        "uptime_seconds": None,
        "cpu_temp": None,
        "modules": [],
    }

    if db is not None:
        latest_tel = (
            db.query(Telemetry)
            .filter(Telemetry.device_id == device.id)
            .order_by(Telemetry.recorded_at.desc())
            .first()
        )
        if latest_tel:
            if latest_tel.cpu_temp is not None:
                data["cpu_temp"] = float(latest_tel.cpu_temp)
            if latest_tel.uptime_seconds is not None:
                data["uptime_seconds"] = int(latest_tel.uptime_seconds)
            elif isinstance(latest_tel.payload, dict):
                data["uptime_seconds"] = latest_tel.payload.get("uptime_seconds")

        logs = (
            db.query(DeploymentLog)
            .filter(DeploymentLog.device_id == device.id)
            .order_by(DeploymentLog.created_at.desc(), DeploymentLog.id.desc())
            .all()
        )
        latest_by_stage = {}
        for log in logs:
            if log.stage and log.stage not in latest_by_stage:
                latest_by_stage[log.stage] = log.status.lower() if log.status else ""
        data["modules"] = [
            stage for stage, status in latest_by_stage.items() if status == "success"
        ]

    return data

@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Mengisi 4 Kartu Metrik di Dashboard Utama."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=ONLINE_WINDOW_SECONDS)

    total = db.query(Device).count()
    online = db.query(Device).filter(Device.last_seen >= threshold).count()
    offline = total - online
    rooms = db.query(func.count(func.distinct(Device.room_id))).scalar() or 0

    return DashboardSummary(
        total_devices=total,
        online_devices=online,
        offline_devices=offline,
        rooms_count=rooms
    )

@router.get("", response_model=List[DeviceResponse])
def list_devices(room_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Menampilkan tabel inventaris perangkat."""
    query = db.query(Device)
    if room_id:
        query = query.filter(Device.room_id == room_id)
    now = datetime.now(timezone.utc)
    return [_serialize_device(device, now, db) for device in query.order_by(Device.created_at.desc()).all()]

@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(device_id: str, db: Session = Depends(get_db)):
    """Mengambil detail satu Raspberry Pi."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")
    return _serialize_device(device, datetime.now(timezone.utc), db)

@router.post("/{device_id}/config", status_code=status.HTTP_200_OK)
def set_device_config(device_id: str, payload: DeviceConfigPayload, db: Session = Depends(get_db)):
    """
    Kirim Desired State ke Raspi via MQTT Retained.
    Raspi akan membaca konfigurasi ini dan memasang modul yang diminta.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")

    if payload.room_id:
        device.room_id = payload.room_id
        db.commit()

    config_dict = payload.model_dump()
    config_dict["device_id"] = device_id
    publish_device_config(device_id, config_dict)

    return {
        "message": f"Konfigurasi modul berhasil dikirim ke {device_id}.",
        "config": config_dict
    }

@router.get("/{device_id}/metrics")
def get_device_metrics(device_id: str, db: Session = Depends(get_db)):
    """Latest device-metrics v1 sample plus explicit freshness metadata.

    Returns HTTP 200 with ``available: false`` when the device has never
    published v1 metrics. This lets the dashboard explain the missing data
    instead of treating it as an API failure or inventing zeroes.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")

    now = datetime.now(timezone.utc)
    latest = (
        db.query(Telemetry)
        .filter(
            Telemetry.device_id == device_id,
            Telemetry.payload["kind"].astext == METRICS_KIND,
        )
        .order_by(Telemetry.recorded_at.desc())
        .first()
    )
    response = build_metrics_response(
        latest,
        now,
        stale_after_seconds=settings.DEVICE_METRICS_STALE_SECONDS,
    )
    response["device_id"] = device_id
    response["device_status"] = device_status(device.last_seen, now)
    return response


@router.get("/{device_id}/telemetry")
def get_device_telemetry(device_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """Data untuk kurva grafik suhu CPU (Line Chart).

    Metrics rows share the telemetry table for storage but are excluded here:
    ``/metrics`` is their API. The unit is only reported when the stored payload
    actually contains it; legacy Fahrenheit samples stay unlabeled.
    """
    records = db.query(Telemetry)\
        .filter(Telemetry.device_id == device_id)\
        .filter(func.coalesce(Telemetry.payload["kind"].astext, "") != METRICS_KIND)\
        .order_by(Telemetry.recorded_at.desc())\
        .limit(limit)\
        .all()
    # Balik urutan agar kronologis (dari waktu terlama ke terbaru) untuk grafik
    records.reverse()
    response = []
    for record in records:
        metadata = temperature_metadata(record.payload)
        response.append({
            "timestamp": record.recorded_at.isoformat(),
            "cpu_temp": float(record.cpu_temp) if record.cpu_temp is not None else None,
            "unit": metadata["unit"],
            "unit_source": metadata["unit_source"],
            "schema_version": metadata["schema_version"],
            "room_id": metadata["room_id"],
            "error": metadata["error"],
        })
    return response

@router.get("/{device_id}/logs")
def get_device_logs(device_id: str, db: Session = Depends(get_db)):
    """Riwayat status modul (installing, success, failed)."""
    return db.query(DeploymentLog)\
        .filter(DeploymentLog.device_id == device_id)\
        .order_by(DeploymentLog.created_at.desc())\
        .all()

@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: str, db: Session = Depends(get_db)):
    """Hapus perangkat dari database."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")
    db.delete(device)
    db.commit()
    return None
