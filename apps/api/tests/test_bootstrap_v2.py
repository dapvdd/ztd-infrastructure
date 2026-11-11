"""Tests for Sprint 3 bootstrap extension: ZTD identity and dual-server config fields."""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.routes.bootstrap import build_script, BootstrapRequest


def _wifi_base(**extra) -> dict:
    return {
        "device_name": "raspi-test-01",
        "connection_type": "Wi-Fi",
        "wifi_type": "Personal",
        "wifi_ssid": "TestNet",
        "wifi_password": "password123",
        "ip_mode": "DHCP",
        **extra,
    }


class TestBootstrapV2Fields:
    """ZTD identity and dual-server config are injected as shlex-quoted vars."""

    def test_device_id_injected_in_script(self):
        req = BootstrapRequest(
            **_wifi_base(ztd_device_id="raspi-abc123")
        )
        script = build_script(req)
        # shlex.quote on safe alphanumeric strings doesn't add quotes
        assert "ZTD_DEVICE_ID=raspi-abc123" in script

    def test_provisioning_url_injected(self):
        req = BootstrapRequest(
            **_wifi_base(provisioning_url="https://100.105.163.126")
        )
        script = build_script(req)
        assert "PROVISIONING_URL=https://100.105.163.126" in script

    def test_monitoring_hub_id_injected(self):
        req = BootstrapRequest(
            **_wifi_base(monitoring_hub_id="hs109rs-hub-01")
        )
        script = build_script(req)
        assert "MONITORING_HUB_ID=hs109rs-hub-01" in script

    def test_monitoring_url_injected(self):
        req = BootstrapRequest(
            **_wifi_base(monitoring_url="https://192.168.1.100")
        )
        script = build_script(req)
        assert "MONITORING_URL=https://192.168.1.100" in script

    def test_all_new_fields_together(self):
        req = BootstrapRequest(**_wifi_base(
            ztd_device_id="raspi-edge-01",
            provisioning_url="https://100.105.163.126",
            monitoring_hub_id="hs109rs-hub-01",
            monitoring_url="https://192.168.72.245",
        ))
        script = build_script(req)
        assert "ZTD_DEVICE_ID=raspi-edge-01" in script
        assert "PROVISIONING_URL=https://100.105.163.126" in script
        assert "MONITORING_HUB_ID=hs109rs-hub-01" in script
        assert "MONITORING_URL=https://192.168.72.245" in script

    def test_new_fields_are_optional_defaults_empty(self):
        req = BootstrapRequest(**_wifi_base())
        script = build_script(req)
        # shlex.quote('') = "''" — empty string
        assert "ZTD_DEVICE_ID=''" in script
        assert "PROVISIONING_URL=''" in script
        assert "MONITORING_HUB_ID=''" in script
        assert "MONITORING_URL=''" in script

    def test_shell_injection_prevention_in_new_fields(self):
        """Control characters and shell metacharacters in new fields must be quoted safely."""
        req = BootstrapRequest(**_wifi_base(
            ztd_device_id="raspi-safe",
            provisioning_url="https://host.example.com/$(rm -rf /)",
        ))
        script = build_script(req)
        # Security property: the injection payload must be single-quoted so the shell
        # treats it as a literal string, not an executable command substitution.
        # The URL appears single-quoted (shlex.quote detects shell metacharacters).
        assert "'https://host.example.com/$(rm -rf /)'" in script
        # Double-check: the value is NOT assigned bare (which would execute the substitution)
        assert "PROVISIONING_URL=https://host.example.com/$(rm" not in script

    def test_control_characters_rejected_in_new_fields(self):
        req = BootstrapRequest(**_wifi_base())
        req.ztd_device_id = "raspi\x00bad"
        with pytest.raises(Exception):
            build_script(req)

    def test_api_endpoint_accepts_new_fields(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/bootstrap/raspberry",
            json=_wifi_base(
                ztd_device_id="raspi-api-test",
                provisioning_url="https://100.105.163.126",
            ),
        )
        assert resp.status_code == 200
        assert "ZTD_DEVICE_ID=raspi-api-test" in resp.text
        assert "PROVISIONING_URL=https://100.105.163.126" in resp.text
