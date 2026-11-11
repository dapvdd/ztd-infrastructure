"""
esp_node_adapter.py — ESP/IoT Node Identity & Whitelist Adapter

Maps ESP8266/ESP32 firmware identity to ZTD/HubBrain gateway-side concepts.

Firmware constraints (documented limitation):
  - ESP firmware uses secrets.h compiled at flash time for WiFi/MQTT credentials.
  - Zero-touch wireless credential provisioning is NOT supported — the firmware
    requires physical flashing to update secrets.h.
  - This adapter covers only identity mapping (MAC → node_id) and gateway-side
    whitelist management. Physical device commissioning remains a manual step.

Firmware identity (from WEMOS_TS.ino):
  DEV_ID   = WiFi.macAddress()         e.g. "AA:BB:CC:DD:EE:FF"
  DEV_NAME = "TS-" + last4MAC          e.g. "TS-EEFF"
  MQTT topic: "hs109rs/<sensor_type_lower>/data"
  Payload: {"DEV_ID", "DEV_NAME", "TEMP", "HUM", "RSSI", "IP"}
"""

from __future__ import annotations

import re
from typing import Any

# Firmware-defined MQTT topic pattern
MQTT_TOPIC_PATTERN = "hs109rs/{sensor_type_lower}/data"

# Valid MAC pattern (colon or hyphen separated)
_MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})"
    r"[:\-]([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})$"
)


def _parse_mac(mac: str) -> list[str]:
    """Parse MAC address string into 6 uppercase hex octets. Raises ValueError on bad input."""
    m = _MAC_RE.match(mac.strip())
    if not m:
        raise ValueError(f"Invalid MAC address format: {mac!r}. Expected XX:XX:XX:XX:XX:XX")
    return [g.upper() for g in m.groups()]


# ---------------------------------------------------------------------------
# Identity mapping functions (pure)
# ---------------------------------------------------------------------------


def mac_to_node_id(mac: str) -> str:
    """Convert firmware MAC address to ZTD node_id (lowercase, no separators).

    >>> mac_to_node_id("AA:BB:CC:DD:EE:FF")
    'aabbccddeeff'
    """
    octets = _parse_mac(mac)
    return "".join(octets).lower()


def mac_to_dev_name(mac: str, sensor_type: str = "TS") -> str:
    """Derive firmware DEV_NAME from MAC (last 4 hex chars uppercase).

    Matches the firmware: DEV_NAME = sensor_type + "-" + last4MAC
    >>> mac_to_dev_name("AA:BB:CC:DD:EE:FF")
    'TS-EEFF'
    """
    octets = _parse_mac(mac)
    last4 = octets[4] + octets[5]  # e.g. "EE" + "FF" → "EEFF"
    return f"{sensor_type.upper()}-{last4}"


def build_node_record(
    gateway_id: str,
    mac: str,
    sensor_type: str = "TS",
) -> dict[str, Any]:
    """Build a ZTD node association record for a gateway-attached ESP node.

    Returns a dict suitable for persistence and whitelist generation.
    """
    node_id = mac_to_node_id(mac)
    dev_name = mac_to_dev_name(mac, sensor_type)
    mqtt_topic = MQTT_TOPIC_PATTERN.format(sensor_type_lower=sensor_type.lower())
    return {
        "gateway_id": gateway_id,
        "node_id": node_id,
        "dev_id": mac.upper().replace("-", ":"),
        "dev_name": dev_name,
        "sensor_type": sensor_type.upper(),
        "mqtt_topic": mqtt_topic,
    }


# ---------------------------------------------------------------------------
# Whitelist management
# ---------------------------------------------------------------------------


def build_whitelist_entry(
    mac: str,
    gateway_id: str,
    allowed: bool = True,
) -> dict[str, Any]:
    """Build a HubBrain-compatible whitelist entry for an ESP node.

    DEV_ID is the firmware-reported MAC address string (colon-separated, uppercase).
    """
    octets = _parse_mac(mac)
    dev_id = ":".join(octets)
    return {
        "DEV_ID": dev_id,
        "gateway_id": gateway_id,
        "node_id": "".join(octets).lower(),
        "allowed": allowed,
    }


def validate_whitelist(entries: list[dict[str, Any]]) -> None:
    """Validate a list of whitelist entries for duplicate DEV_ID across gateways.

    Raises ValueError if the same DEV_ID appears on more than one gateway_id,
    which would cause collision in the HubBrain telemetry stream.
    """
    seen: dict[str, str] = {}  # DEV_ID → gateway_id
    for entry in entries:
        dev_id = entry["DEV_ID"]
        gw = entry["gateway_id"]
        if dev_id in seen and seen[dev_id] != gw:
            raise ValueError(
                f"duplicate DEV_ID {dev_id!r} registered on multiple gateways: "
                f"{seen[dev_id]!r} and {gw!r}. "
                "Each ESP node may only belong to one gateway."
            )
        seen[dev_id] = gw
