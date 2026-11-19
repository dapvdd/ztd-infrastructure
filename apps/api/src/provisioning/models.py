"""Provisioning identity is deliberately independent of MQTT discovery."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProvisioningBase(DeclarativeBase):
    pass


class RegisteredDevice(ProvisioningBase):
    __tablename__ = "provisioning_devices"
    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    credential_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hostname: Mapped[str | None] = mapped_column(String(100))
    approval_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    approval_revision: Mapped[int] = mapped_column(Integer, default=0)
    approval_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    configuration_revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalogModule(ProvisioningBase):
    __tablename__ = "provisioning_modules"
    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    repo_url: Mapped[str] = mapped_column(String(500))
    commit: Mapped[str] = mapped_column(String(40))
    approved: Mapped[bool]


class Assignment(ProvisioningBase):
    __tablename__ = "provisioning_assignments"
    device_id: Mapped[str] = mapped_column(
        ForeignKey("provisioning_devices.device_id"), primary_key=True
    )
    module_name: Mapped[str] = mapped_column(
        ForeignKey("provisioning_modules.name"), primary_key=True
    )
    repo_url: Mapped[str] = mapped_column(String(500))
    commit: Mapped[str] = mapped_column(String(40))
    configuration: Mapped[dict[str, int]] = mapped_column(JSON)
    withdrawn: Mapped[bool] = mapped_column(default=False)


class ApprovalEvent(ProvisioningBase):
    __tablename__ = "provisioning_approval_events"
    device_id: Mapped[str] = mapped_column(
        ForeignKey("provisioning_devices.device_id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
