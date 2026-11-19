from sqlalchemy import Column, String, DateTime, ForeignKey, Text, func, Numeric, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from src.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(String(32), primary_key=True)       # raspi-xxxxxx
    room_id = Column(String(50), nullable=True)     # room-a, room-b, dll
    hostname = Column(String(100), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IP Tailscale
    status = Column(String(20), nullable=False, default="ONLINE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=True)

class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(String(32), ForeignKey("devices.id", ondelete="CASCADE"))
    stage = Column(String(50), nullable=False)      # Nama modul (temperature, camera, dll)
    status = Column(String(20), nullable=False)     # installing, success, failed, removed
    log_output = Column(Text, nullable=True)        # Detail pesan / traceback error
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(String(32), ForeignKey("devices.id", ondelete="CASCADE"))
    cpu_temp = Column(Numeric(5, 2), nullable=True)
    ram_usage = Column(Numeric(5, 2), nullable=True)
    uptime_seconds = Column(BigInteger, nullable=True)
    payload = Column(JSONB, nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
