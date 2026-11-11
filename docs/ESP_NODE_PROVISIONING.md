# ESP Node Provisioning Guide

## Overview

This document describes how ESP8266/ESP32 nodes (running the WEMOS_TS firmware) integrate with the ZTD + HubBrain V5 system.

## Firmware Identity Model

The ESP firmware defines its identity at flash time:

| Firmware var | Source | Example |
|---|---|---|
| `DEV_ID` | `WiFi.macAddress()` | `AA:BB:CC:DD:EE:FF` |
| `DEV_NAME` | `"TS-" + last4MAC` | `TS-EEFF` |
| MQTT topic | hardcoded | `hs109rs/ts/data` |

## ⚠️ Zero-Touch Wireless Onboarding: NOT SUPPORTED

**The ESP firmware uses `secrets.h` compiled at flash time.** WiFi SSID, WiFi password, and MQTT credentials are baked into the firmware binary during the Arduino IDE build step.

**Consequence:** A fresh ESP node cannot receive wireless credentials over the air. Physical access is required to:
1. Create/update `firmware/WEMOS_TS/secrets.h` with correct credentials
2. Flash the firmware via USB

The ZTD system does NOT automate this step. "Zero-touch" for ESP nodes means:
- **Gateway side**: The Pi gateway's HubBrain instance auto-discovers ESP nodes by MAC address (via MQTT)
- **Physical side**: Initial flash still requires a human with a USB cable

## What the ESP Node Adapter Covers

The `esp_node_adapter.py` module provides:

1. **Identity mapping**: Convert firmware `DEV_ID` (MAC) → ZTD `node_id` (lowercase hex string)
2. **DEV_NAME derivation**: `"TS-" + last4MAC` matching firmware behavior  
3. **MQTT topic mapping**: `hs109rs/<sensor_type_lower>/data`
4. **Whitelist entry format**: HubBrain-compatible whitelist record
5. **Cross-gateway duplicate detection**: Same MAC on two different gateways = error

## Usage Example

```python
from esp_node_adapter import build_node_record, build_whitelist_entry, validate_whitelist

# When a new ESP node is discovered on a gateway:
record = build_node_record(
    gateway_id="raspi-edge-01",
    mac="AA:BB:CC:DD:EE:FF",
    sensor_type="TS",
)
# record = {
#   "gateway_id": "raspi-edge-01",
#   "node_id": "aabbccddeeff",
#   "dev_id": "AA:BB:CC:DD:EE:FF",
#   "dev_name": "TS-EEFF",
#   "sensor_type": "TS",
#   "mqtt_topic": "hs109rs/ts/data",
# }

whitelist_entry = build_whitelist_entry(mac="AA:BB:CC:DD:EE:FF", gateway_id="raspi-edge-01")
# whitelist_entry = {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-edge-01", "allowed": True, ...}

# Validate no cross-gateway MAC collisions before syncing whitelist to HubBrain:
validate_whitelist(all_entries)  # raises ValueError on duplicate DEV_ID across gateways
```

## MQTT Payload Format

The WEMOS_TS firmware publishes to `hs109rs/ts/data`:

```json
{
  "DEV_ID":   "AA:BB:CC:DD:EE:FF",
  "DEV_NAME": "TS-EEFF",
  "TEMP":     24.5,
  "HUM":      60.1,
  "RSSI":     -65,
  "IP":       "192.168.1.123"
}
```

HubBrain's `filter.py` applies deadband filtering (TS_DEADBAND_TEMP=0.3°C, TS_DEADBAND_HUM=1.0%) before forwarding to the Monitoring VPS.

## Sensor Types

| Sensor | MQTT topic | DEV_NAME prefix |
|---|---|---|
| Temperature/Humidity (SHT31) | `hs109rs/ts/data` | `TS-` |
| CO2 (future) | `hs109rs/co2/data` | `CO2-` |

## Manual Commissioning Checklist

For each new ESP node:
1. [ ] Obtain MAC address from device (printed on module or via serial monitor)
2. [ ] Update `firmware/WEMOS_TS/secrets.h` with correct WiFi/MQTT credentials
3. [ ] Flash firmware via USB
4. [ ] Register node in ZTD: `build_node_record(gateway_id, mac, sensor_type)`
5. [ ] Add to gateway whitelist: `build_whitelist_entry(mac, gateway_id)`
6. [ ] Sync whitelist to HubBrain (manual step or via Pi agent manifest)
7. [ ] Verify telemetry arrives on `hs109rs/ts/data` within 60 seconds of power-on
