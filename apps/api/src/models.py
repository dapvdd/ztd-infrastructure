import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, func, Numeric, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mac_address = Column(String(17), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    ip_address = Column(String(45), nullable=True)
    device_token = Column(String(64), unique=True, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="WHITELISTED")
    ssh_user = Column(String(32), default="pi")
    ssh_port = Column(Integer, default=22)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    provisioned_at = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)

class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"))
    stage = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    log_output = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Telemetry(Base):
    __tablename__ = "telemetry"
    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"))
    cpu_temp = Column(Numeric(5, 2), nullable=True)
    ram_usage = Column(Numeric(5, 2), nullable=True)
    uptime_seconds = Column(BigInteger, nullable=True)
    payload = Column(JSONB, nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

