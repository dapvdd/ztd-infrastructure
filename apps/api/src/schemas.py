from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

# Model untuk modul individual
class ModuleItem(BaseModel):
    name: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$",
        example="temperature",
    )
    version: str = Field("1.0.0", example="1.0.0")
    enabled: bool = Field(True, example=True)

# Payload saat Admin/Dashboard ingin deploy modul ke Raspi
class DeviceConfigPayload(BaseModel):
    room_id: Optional[str] = Field(None, example="room-b")
    modules: List[ModuleItem]

# Skema response data perangkat untuk Dashboard
class DeviceResponse(BaseModel):
    id: str = Field(..., example="raspi-a1b2c3")
    hostname: Optional[str] = None
    room_id: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = Field("ONLINE", example="ONLINE")
    created_at: datetime
    last_seen: Optional[datetime] = None
    uptime_seconds: Optional[int] = None
    cpu_temp: Optional[float] = None
    modules: Optional[List[str]] = Field(default_factory=list)

    class Config:
        from_attributes = True

# Skema untuk 4 Kartu Metrik di Dashboard Atas
class DashboardSummary(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    rooms_count: int
