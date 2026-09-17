from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
import secrets

from src.database import get_db
from src.models import Device
from src.schemas import DeviceWhitelistCreate, DeviceResponse, DeviceDeployRequest
from src.services.provisioning import execute_provisioning

router = APIRouter(prefix="/api/v1/devices", tags=["Devices"])

@router.post("/whitelist", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def whitelist_device(payload: DeviceWhitelistCreate, db: Session = Depends(get_db)):
    """Pre-register a legitimate Raspberry Pi MAC address with an immediate unique token."""
    existing = db.query(Device).filter(Device.mac_address == payload.mac_address).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device with MAC address '{payload.mac_address}' is already registered."
        )

    # Assign token from payload, or generate a cryptographically secure 128-bit token
    assigned_token = payload.device_token or f"ztd_tok_{secrets.token_hex(16)}"
    # Check for token uniqueness
    token_conflict = db.query(Device).filter(Device.device_token == assigned_token).first()
    if token_conflict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided device_token is already in use by another device."
        )
    device = Device(
        mac_address=payload.mac_address,
        name=payload.name,
        device_token=assigned_token,
        ip_address=payload.ip_address,
        ssh_user=payload.ssh_user,
        ssh_port=payload.ssh_port,
        status="WHITELISTED"
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device

@router.get("", response_model=List[DeviceResponse])
def list_devices(db: Session = Depends(get_db)):
    """List all registered IoT devices and their current status."""
    return db.query(Device).order_by(Device.created_at.desc()).all()

@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(device_id: UUID, db: Session = Depends(get_db)):
    """Retrieve details of a specific device by its UUID."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device

@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: UUID, db: Session = Depends(get_db)):
    """Remove a device from the whitelist."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    db.delete(device)
    db.commit()
    return None

@router.post("/{device_id}/deploy")
def trigger_deployment(
    device_id: UUID,
    payload: DeviceDeployRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger automated Zero Touch Deployment to the Raspberry Pi over SSH.
    Verifies physical MAC against whitelist, installs agent, and starts systemd service.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    target_ip = payload.ip_address or device.ip_address
    if not target_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target IP address must be provided in payload or pre-registered in device record."
        )
    # Run provisioning as background task so API responds immediately
    background_tasks.add_task(
        execute_provisioning,
        device_id=device.id,
        ip_address=target_ip,
        ssh_password=payload.ssh_password,
        ssh_port=payload.ssh_port or device.ssh_port or 22,
        mqtt_host=payload.mqtt_host
    )

    return {
        "message": f"Zero Touch Deployment initiated for device '{device.mac_address}' at {target_ip}.",
        "status": "PROVISIONING"
    }

@router.get("/{device_id}/telemetry")
def get_device_telemetry(device_id: UUID, limit: int = 20, db: Session = Depends(get_db)):
    """Retrieve the latest telemetry data (CPU temp, uptime) received from the Pi."""
    from src.models import Telemetry
    telemetry_records = db.query(Telemetry)\
        .filter(Telemetry.device_id == device_id)\
        .order_by(Telemetry.recorded_at.desc())\
        .limit(limit)\
        .all()
    return telemetry_records

@router.get("/{device_id}/logs")
def get_deployment_logs(device_id: UUID, db: Session = Depends(get_db)):
    """View step-by-step deployment audit logs for a device."""
    from src.models import DeploymentLog
    logs = db.query(DeploymentLog).filter(DeploymentLog.device_id == device_id).order_by(DeploymentLog.created_at.asc()).all()
    return logs
