"""Strict public contracts; module configuration has no free-form secret fields."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Enrollment(StrictModel):
    device_id: str = Field(pattern=r"^raspi-[a-z0-9-]{3,20}$")


class Registration(StrictModel):
    hostname: str = Field(pattern=r"^raspi-[a-z0-9-]{3,20}$")


class DeviceStatus(StrictModel):
    device_id: str
    hostname: str | None
    registration_status: Literal["ENROLLED", "REGISTERED"]
    approval_status: Literal["PENDING", "APPROVED", "REJECTED", "REVOKED"]
    approval_revision: int
    approval_expires_at: datetime | None
    configuration_revision: int
    created_at: datetime
    registered_at: datetime | None


class EnrollmentResult(DeviceStatus):
    password: str


class Decision(StrictModel):
    schema_version: Literal["1"]
    event_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:._-]+$")
    revision: int = Field(ge=1)
    status: Literal["APPROVED", "REJECTED", "REVOKED"]
    actor: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:._-]+$")
    expires_at: AwareDatetime


class ModuleSpec(StrictModel):
    repo_url: str = Field(max_length=500, pattern=r"^https://[^\s]+\.git$")
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    approved: bool


class ModuleConfiguration(StrictModel):
    sample_interval_seconds: int = Field(default=60, ge=1, le=86400, strict=True)


class HubConfig(StrictModel):
    """Non-secret HubBrain addressing delivered via the manifest.

    Deliberately excludes hub_key and mqtt_pass: Monitoring credentials are
    provisioned manually on the device (env-only) and never travel through
    the provisioning API (F-02).
    """

    hub_id: str = Field(min_length=1, max_length=100)
    server_url: str = Field(pattern=r"^https://[^\s]+$")
    mqtt_host: str = Field(min_length=1, max_length=253)
    mqtt_port: int = Field(ge=1, le=65535)


class AssignmentInput(StrictModel):
    configuration: ModuleConfiguration | None = None


class ManifestModule(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$")
    repo_url: str = Field(pattern=r"^https://[^\s]+\.git$")
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    configuration: dict[str, int]


class Manifest(StrictModel):
    schema_version: Literal["2"] = "2"
    device_id: str
    configuration_revision: int
    updated_at: datetime
    assignment_status: Literal["EMPTY", "ASSIGNED"]
    modules: list[ManifestModule]
    hub_config: HubConfig | None = None
