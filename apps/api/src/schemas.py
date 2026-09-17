import re
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

class DeviceWhitelistCreate(BaseModel):
    mac_address: str = Field(..., example="b8:27:eb:11:22:33", description="Physical MAC address of the Raspberry Pi")
    name: Optional[str] = Field(None, example="Raspberry Pi 2B - Sensor Hub")
    device_token: Optional[str] = Field(None, example="ztd_tok_pi2b_lab", description="Unique device token (auto-generated if omitted)")
    ip_address: Optional[str] = Field(None, example="192.168.1.50")
    ssh_user: Optional[str] = Field("pi", example="pi")
    ssh_port: Optional[int] = Field(22, example=22)

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        clean_mac = v.strip().lower().replace("-", ":")
        if not re.match(r"^([0-9a-f]{2}[:]){5}([0-9a-f]{2})$", clean_mac):
            raise ValueError("Invalid MAC address format. Expected format: xx:xx:xx:xx:xx:xx")
        return clean_mac

class DeviceResponse(BaseModel):
    id: UUID
    mac_address: str
    name: Optional[str]
    ip_address: Optional[str]
    device_token: Optional[str]
    status: str
    ssh_user: Optional[str]
    ssh_port: Optional[int]
    created_at: datetime
    provisioned_at: Optional[datetime]
    last_seen: Optional[datetime]

    class Config:
        from_attributes = True

class DeviceDeployRequest(BaseModel):
    ip_address: Optional[str] = Field(None, example="192.168.1.50", description="IP address of the target Raspberry Pi")
    ssh_password: Optional[str] = Field("raspberry", example="raspberry", description="SSH password for the Pi user")
    ssh_port: Optional[int] = Field(22, example=22)
    mqtt_host: Optional[str] = Field(None, example="192.168.1.100", description="IP/Hostname of the MQTT server that the Pi should connect to")
