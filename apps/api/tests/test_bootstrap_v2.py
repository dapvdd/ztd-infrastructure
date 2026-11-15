"""Tests for Sprint 3 bootstrap extension: ZTD identity and dual-server config fields."""

import os
import shutil
import subprocess
import sys

import pytest

# Ensure apps/api is on sys.path so 'src' imports work from any CWD
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from fastapi.testclient import TestClient
from src.main import app
from src.routes.bootstrap import build_script, BootstrapRequest


def _wifi_base(**extra) -> dict:
    return {
        "device_name": "raspi-test-01",
        "connection_type": "Wi-Fi",
        "wifi_type": "Personal",
        "wifi_ssid": "TestNet",
        "ip_mode": "DHCP",
        "ztd_device_id": "raspi-test-01",
        "provisioning_url": "https://100.105.163.126",
        "monitoring_hub_id": "hs109rs-hub-01",
        "monitoring_url": "https://192.168.72.245",
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

    def test_identity_fields_are_validated(self):
        with pytest.raises(Exception):
            BootstrapRequest(device_name="raspi-test-01", connection_type="Wi-Fi", wifi_ssid="TestNet")

    def test_shell_injection_prevention_in_new_fields(self):
        """Server URLs with invalid characters are rejected before interpolation."""
        with pytest.raises(Exception):
            BootstrapRequest(**_wifi_base(
                ztd_device_id="raspi-safe",
                provisioning_url="https://host.example.com/$(rm -rf /)",
            ))

    def test_control_characters_rejected_in_new_fields(self):
        req = BootstrapRequest(**_wifi_base())
        with pytest.raises(Exception):
            req.ztd_device_id = "raspi\x00bad"
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


class TestBootstrapInstallsAgentV2:
    """F-01: the generated script must actually install and start Agent V2."""

    def _script(self, **extra) -> str:
        return build_script(BootstrapRequest(**_wifi_base(**extra)))

    def test_script_contains_agent_install_section(self):
        script = self._script(ztd_device_id="raspi-edge-01")
        assert "install_ztd_agent_v2" in script

    def test_script_writes_agent_env_with_identity_fields(self):
        script = self._script(
            ztd_device_id="raspi-edge-01",
            provisioning_url="https://100.105.163.126",
            monitoring_hub_id="hs109rs-hub-01",
            monitoring_url="https://192.168.72.245",
        )
        assert "/etc/ztd/agent.env" in script
        assert "ZTD_DEVICE_ID=raspi-edge-01" in script
        # agent.env maps header vars into ZTD_* names; expansion happens at runtime
        assert "ZTD_PROVISIONING_URL=$PROVISIONING_URL" in script
        assert "ZTD_MONITORING_HUB_ID=$MONITORING_HUB_ID" in script
        assert "ZTD_MONITORING_URL=$MONITORING_URL" in script
        # header var itself is shlex-quoted
        assert "PROVISIONING_URL=https://100.105.163.126" in script

    def test_script_enables_systemd_unit(self):
        script = self._script(ztd_device_id="raspi-edge-01")
        assert "systemctl enable --now ztd-agent-v2" in script

    def test_script_provisions_ztd_user_and_group(self):
        """Must ensure system user 'ztd' and group 'ztd' exist on fresh Pi before chown."""
        script = self._script(
            ztd_device_id="raspi-edge-01",
            provisioning_url="https://100.105.163.126",
        )
        assert "groupadd -r ztd" in script
        assert "useradd -r -g ztd" in script

    def test_script_installs_systemd_unit_file(self):
        """Must write /etc/systemd/system/ztd-agent-v2.service and reload daemon."""
        script = self._script(
            ztd_device_id="raspi-edge-01",
            provisioning_url="https://100.105.163.126",
        )
        assert "/etc/systemd/system/ztd-agent-v2.service" in script
        assert "systemctl daemon-reload" in script
        assert "ExecStart=/usr/bin/python3 /opt/ztd/agent_v2.py" in script

    def test_agent_block_guarded_by_device_id(self):
        script = self._script()
        # The install function is always defined but must no-op without identity.
        assert '[ -z "$ZTD_DEVICE_ID" ]' in script
        assert "skipping Agent V2 installation" in script

    def test_agent_block_does_not_touch_legacy_agent(self):
        script = self._script(ztd_device_id="raspi-edge-01")
        assert "iot-agent.service" not in script

    def test_generated_script_passes_bash_syntax_check(self):
        script = self._script(
            ztd_device_id="raspi-edge-01",
            provisioning_url="https://100.105.163.126",
        )
        # Prefer real Git-for-Windows bash; the WindowsApps bash.EXE is a WSL
        # stub that exits 1 ("no installed distributions") without parsing.
        # normcase because Windows paths are case-insensitive.
        wsl_stub = os.path.normcase(
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\bash.exe")
        )
        found = shutil.which("bash")
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        bash = (
            found
            if found and os.path.normcase(os.path.abspath(found)) != wsl_stub
            else (git_bash if os.path.isfile(git_bash) else None)
        )
        if not bash:
            pytest.skip("bash not available on this platform")
        proc = subprocess.run(
            [bash, "-n"], input=script, capture_output=True, text=True, timeout=30
        )
        assert proc.returncode == 0, proc.stderr
