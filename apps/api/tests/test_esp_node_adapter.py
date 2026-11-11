"""
Tests for apps/agent/esp_node_adapter.py

The ESP8266 firmware uses:
  DEV_ID = WiFi.macAddress()       e.g. "AA:BB:CC:DD:EE:FF"
  DEV_NAME = "TS-" + last4MAC     e.g. "TS-EEFF"
  MQTT topic: "hs109rs/ts/data"
  Payload: JSON {"DEV_ID", "DEV_NAME", "TEMP", "HUM", "RSSI", "IP"}

The adapter maps this firmware identity to ZTD/HubBrain gateway-side concepts.
ESP wireless onboarding NOT claimed (secrets.h compiled at flash time).
"""

import os
import sys

import pytest

AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "agent")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

import esp_node_adapter


class TestNodeIdentityMapping:
    """Gateway identity mapping from firmware DEV_ID (MAC) to ZTD node record."""

    def test_mac_to_node_id_normalized(self):
        node_id = esp_node_adapter.mac_to_node_id("AA:BB:CC:DD:EE:FF")
        assert node_id == "aabbccddeeff"

    def test_mac_with_hyphens_normalized(self):
        node_id = esp_node_adapter.mac_to_node_id("AA-BB-CC-DD-EE-FF")
        assert node_id == "aabbccddeeff"

    def test_mac_to_dev_name(self):
        name = esp_node_adapter.mac_to_dev_name("AA:BB:CC:DD:EE:FF")
        assert name == "TS-EEFF"

    def test_mac_to_dev_name_lowercase_input(self):
        name = esp_node_adapter.mac_to_dev_name("aa:bb:cc:dd:ee:ff")
        assert name == "TS-EEFF"

    def test_invalid_mac_raises(self):
        with pytest.raises(ValueError, match="MAC"):
            esp_node_adapter.mac_to_node_id("not-a-mac")

    def test_node_record_has_required_fields(self):
        record = esp_node_adapter.build_node_record(
            gateway_id="raspi-edge-01",
            mac="AA:BB:CC:DD:EE:FF",
            sensor_type="TS",
        )
        assert record["gateway_id"] == "raspi-edge-01"
        assert record["node_id"] == "aabbccddeeff"
        assert record["dev_name"] == "TS-EEFF"
        assert record["sensor_type"] == "TS"
        assert "mqtt_topic" in record

    def test_mqtt_topic_matches_firmware_pattern(self):
        record = esp_node_adapter.build_node_record(
            gateway_id="raspi-edge-01",
            mac="AA:BB:CC:DD:EE:FF",
            sensor_type="TS",
        )
        assert record["mqtt_topic"] == "hs109rs/ts/data"

    def test_different_sensor_types_produce_correct_topics(self):
        for sensor, expected_topic in [
            ("TS", "hs109rs/ts/data"),
            ("CO2", "hs109rs/co2/data"),
        ]:
            record = esp_node_adapter.build_node_record(
                gateway_id="gw-01",
                mac="11:22:33:44:55:66",
                sensor_type=sensor,
            )
            assert record["mqtt_topic"] == expected_topic


class TestWhitelistFormat:
    """Whitelist entries must be in the format expected by HubBrain."""

    def test_whitelist_entry_has_dev_id_field(self):
        entry = esp_node_adapter.build_whitelist_entry(
            mac="AA:BB:CC:DD:EE:FF",
            gateway_id="raspi-edge-01",
        )
        assert "DEV_ID" in entry
        assert entry["DEV_ID"] == "AA:BB:CC:DD:EE:FF"

    def test_whitelist_entry_has_gateway_id(self):
        entry = esp_node_adapter.build_whitelist_entry(
            mac="AA:BB:CC:DD:EE:FF",
            gateway_id="raspi-edge-01",
        )
        assert entry["gateway_id"] == "raspi-edge-01"

    def test_whitelist_entry_has_allowed_flag(self):
        entry = esp_node_adapter.build_whitelist_entry(
            mac="AA:BB:CC:DD:EE:FF",
            gateway_id="raspi-edge-01",
        )
        assert entry.get("allowed") is True

    def test_duplicate_node_across_gateways_raises(self):
        """Same MAC on different gateways must be caught to prevent collision."""
        entries = [
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-01", "allowed": True},
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-02", "allowed": True},
        ]
        with pytest.raises(ValueError, match="duplicate"):
            esp_node_adapter.validate_whitelist(entries)

    def test_unique_macs_across_gateways_passes(self):
        entries = [
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-01", "allowed": True},
            {"DEV_ID": "11:22:33:44:55:66", "gateway_id": "raspi-02", "allowed": True},
        ]
        esp_node_adapter.validate_whitelist(entries)  # must not raise

    def test_same_mac_same_gateway_is_fine(self):
        """Idempotent registration on same gateway must not raise."""
        entries = [
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-01", "allowed": True},
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-01", "allowed": True},
        ]
        esp_node_adapter.validate_whitelist(entries)  # must not raise


class TestFirmwareConstraintDoc:
    """Firmware onboarding constraint must be documented in the module."""

    def test_module_has_esp_onboarding_limitation_note(self):
        doc = esp_node_adapter.__doc__ or ""
        assert "secrets.h" in doc or "flash" in doc.lower() or "not supported" in doc.lower()
