"""
Tests for apps/agent/hubbrain_adapter.py

Covers:
- .env file generation (content, permissions)
- Explicit block of automated HubGate credential issuance
- Validation of required env keys
- systemd drop-in rendering
"""

import os
import stat
import sys

import pytest

AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "agent")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

import hubbrain_adapter


class TestEnvFileGeneration:
    """Hub .env is written with correct content and restricted permissions."""

    def _config(self, **overrides) -> dict:
        base = {
            "hub_id": "hub-raspi-01",
            "hub_key": "super-secret-key-32-chars-minimum!",
            "server_url": "https://monitoring.example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
            "mqtt_user": "hub-raspi-01",
            "mqtt_pass": "mqtt-pass-secret",
        }
        return {**base, **overrides}

    def test_env_file_contains_hub_id(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        content = open(path).read()
        assert "HUB_ID=hub-raspi-01" in content

    def test_env_file_contains_hub_key(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        content = open(path).read()
        assert "HUB_KEY=" in content
        assert "super-secret-key-32-chars-minimum!" in content

    def test_env_file_contains_server_url(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        content = open(path).read()
        assert "SERVER_URL=https://monitoring.example.com" in content

    def test_env_file_contains_mqtt_config(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        content = open(path).read()
        assert "MQTT_HOST=mqtt.example.com" in content
        assert "MQTT_PORT=8883" in content

    def test_env_file_permissions_owner_only(self, tmp_path):
        """Hub .env must not be world- or group-readable."""
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        if os.name != "nt":
            mode = os.stat(path).st_mode
            assert not (mode & stat.S_IRGRP), "Group read must not be set"
            assert not (mode & stat.S_IROTH), "Other read must not be set"

    def test_missing_required_key_raises(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        config = self._config()
        del config["hub_key"]
        with pytest.raises((KeyError, ValueError)):
            hubbrain_adapter.write_hubbrain_env(config, path)

    def test_empty_hub_id_raises(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        config = self._config(hub_id="")
        with pytest.raises(ValueError, match="hub_id"):
            hubbrain_adapter.write_hubbrain_env(config, path)

    def test_empty_hub_key_raises(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        config = self._config(hub_key="")
        with pytest.raises(ValueError, match="hub_key"):
            hubbrain_adapter.write_hubbrain_env(config, path)


class TestAutoIssuanceBlock:
    """Automated HubGate credential issuance must be explicitly rejected."""

    def test_issue_credentials_raises_not_supported(self):
        """Calling the auto-issuance function must always raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="HubGate credential issuance"):
            hubbrain_adapter.issue_hubgate_credentials(
                provisioning_url="https://monitoring.example.com",
                device_id="raspi-01",
            )

    def test_issue_credentials_docstring_mentions_manual_process(self):
        doc = hubbrain_adapter.issue_hubgate_credentials.__doc__ or ""
        assert "manual" in doc.lower() or "not supported" in doc.lower()


class TestSystemdDropIn:
    """systemd drop-in references the .env file correctly."""

    def test_dropin_references_env_path(self):
        dropin = hubbrain_adapter.render_systemd_dropin("/etc/ztd/hubbrain.env")
        assert "/etc/ztd/hubbrain.env" in dropin
        assert "EnvironmentFile" in dropin

    def test_dropin_has_unit_section(self):
        dropin = hubbrain_adapter.render_systemd_dropin("/etc/ztd/hubbrain.env")
        assert "[Service]" in dropin


class TestConfigValidation:
    """validate_hub_config enforces required fields and types."""

    def test_valid_config_passes(self):
        config = {
            "hub_id": "hub-01",
            "hub_key": "key-value",
            "server_url": "https://example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
            "mqtt_user": "hub-01",
            "mqtt_pass": "pass",
        }
        hubbrain_adapter.validate_hub_config(config)  # must not raise

    def test_invalid_mqtt_port_raises(self):
        config = {
            "hub_id": "hub-01",
            "hub_key": "key-value",
            "server_url": "https://example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 99999,
            "mqtt_user": "hub-01",
            "mqtt_pass": "pass",
        }
        with pytest.raises(ValueError, match="mqtt_port"):
            hubbrain_adapter.validate_hub_config(config)

    def test_non_https_server_url_raises(self):
        config = {
            "hub_id": "hub-01",
            "hub_key": "key-value",
            "server_url": "http://insecure.example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
            "mqtt_user": "hub-01",
            "mqtt_pass": "pass",
        }
        with pytest.raises(ValueError, match="server_url"):
            hubbrain_adapter.validate_hub_config(config)
