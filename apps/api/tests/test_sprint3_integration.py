"""
Sprint 3 Integration Test Harness — 18 scenario suite.

All tests run locally with isolated SQLite and mocked HTTP.
No real network connections, no production DB, no hardware required.

Scenarios covered:
 1. Bootstrap script contains ZTD identity fields
 2. Bootstrap shell injection prevention
 3. Agent state defaults on missing file
 4. Agent state round-trip save/load
 5. Agent backoff cap respected
 6. Agent manifest hash stability
 7. Agent approval gate: approved + not expired → fetch
 8. Agent approval gate: pending → no fetch
 9. Agent approval gate: expired → no fetch
10. HubBrain env file written correctly
11. HubBrain auto-issuance blocked
12. HubBrain config validation rejects non-https
13. ESP MAC normalization
14. ESP whitelist entry format
15. ESP cross-gateway duplicate rejection
16. Provisioning API: enrollment → register → status (HTTP contract)
17. Provisioning API: manifest blocked without approval
18. Dual-server status classification (provisioning + monitoring)
"""

import datetime
import hashlib
import json
import os
import sys
import stat

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# --- infrastructure worktree (api package) ---
from src.database import get_db
from src.main import app

# --- agent and adapter modules ---
AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "agent")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

import agent_v2
import hubbrain_adapter
import esp_node_adapter

import importlib


def _b64(user: str, password: str) -> str:
    import base64
    return base64.b64encode(f"{user}:{password}".encode()).decode()

# --- monitoringStatus pure helpers (from dashboard — inline here for self-containment) ---
from apps.agent import agent_v2 as _agent_v2  # noqa: F401 — verify importable


# ============================================================
# Shared fixtures
# ============================================================

@pytest.fixture()
def isolated_db(monkeypatch):
    from src.provisioning.models import ProvisioningBase
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    ProvisioningBase.metadata.create_all(engine)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = sessions
    monkeypatch.setenv("ZTD_PROVISIONING_ADMIN_TOKEN", "test-admin-token-with-enough-entropy")
    monkeypatch.setenv("ZTD_MONITORING_TOKEN", "test-monitoring-token-with-enough-entropy")
    monkeypatch.setenv("ZTD_MODULE_REPOSITORIES", "https://github.com/NICEganteng/modulraspipmld.git")
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client(isolated_db):
    return TestClient(app)


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


def _future(hours=1) -> str:
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=hours)).isoformat()


def _past() -> str:
    return (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)).isoformat()


# ============================================================
# Scenario 1: Bootstrap script contains ZTD identity fields
# ============================================================

class TestScenario01_BootstrapZTDFields:
    def test_all_four_new_fields_appear_in_script(self):
        from src.routes.bootstrap import build_script, BootstrapRequest
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


# ============================================================
# Scenario 2: Bootstrap shell injection prevention
# ============================================================

class TestScenario02_BootstrapShellInjection:
    def test_shell_metacharacters_in_provisioning_url_are_quoted(self):
        from src.routes.bootstrap import build_script, BootstrapRequest
        req = BootstrapRequest(**_wifi_base(
            provisioning_url="https://host.example.com/$(rm -rf /)",
        ))
        script = build_script(req)
        assert "'https://host.example.com/$(rm -rf /)'" in script
        assert "PROVISIONING_URL=https://host.example.com/$(rm" not in script


# ============================================================
# Scenario 3: Agent state defaults on missing file
# ============================================================

class TestScenario03_AgentStateDefaults:
    def test_missing_state_file_returns_default(self, tmp_path):
        state = agent_v2.load_state(str(tmp_path / "nonexistent.json"))
        assert state["approval_status"] == "PENDING"
        assert state["revision"] == 0
        assert state["manifest_hash"] is None


# ============================================================
# Scenario 4: Agent state round-trip
# ============================================================

class TestScenario04_AgentStateRoundTrip:
    def test_save_and_load_preserves_all_fields(self, tmp_path):
        path = str(tmp_path / "state.json")
        data = {
            "device_id": "raspi-int-01",
            "revision": 7,
            "approval_status": "APPROVED",
            "manifest_hash": "deadbeef" * 8,
            "applied_at": "2026-11-11T10:00:00+00:00",
        }
        agent_v2.save_state(path, data)
        assert agent_v2.load_state(path) == data


# ============================================================
# Scenario 5: Agent backoff cap
# ============================================================

class TestScenario05_AgentBackoff:
    def test_cap_is_300_seconds(self):
        for attempt in range(100, 110):
            assert agent_v2.backoff_seconds(attempt, base=5, cap=300) == 300

    def test_jitter_never_exceeds_cap(self):
        for _ in range(50):
            delay = agent_v2.backoff_seconds(10, base=5, cap=300, jitter=True)
            assert delay <= 300


# ============================================================
# Scenario 6: Manifest hash stability
# ============================================================

class TestScenario06_ManifestHash:
    def test_hash_stable_across_calls(self):
        m = {"device_id": "raspi-01", "configuration_revision": 3, "modules": []}
        h1 = agent_v2.compute_manifest_hash(m)
        h2 = agent_v2.compute_manifest_hash(m)
        assert h1 == h2 and len(h1) == 64

    def test_hash_changes_on_revision_bump(self):
        base = {"device_id": "raspi-01", "configuration_revision": 1, "modules": []}
        h1 = agent_v2.compute_manifest_hash(base)
        h2 = agent_v2.compute_manifest_hash({**base, "configuration_revision": 2})
        assert h1 != h2


# ============================================================
# Scenario 7: Approval gate — approved + not expired
# ============================================================

class TestScenario07_ApprovalGatePermits:
    def test_approved_not_expired_returns_true(self):
        status = {
            "approval_status": "APPROVED",
            "approval_expires_at": _future(),
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is True


# ============================================================
# Scenario 8: Approval gate — pending
# ============================================================

class TestScenario08_ApprovalGatePending:
    def test_pending_returns_false(self):
        status = {
            "approval_status": "PENDING",
            "approval_expires_at": _future(),
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is False


# ============================================================
# Scenario 9: Approval gate — expired
# ============================================================

class TestScenario09_ApprovalGateExpired:
    def test_expired_returns_false(self):
        status = {
            "approval_status": "APPROVED",
            "approval_expires_at": _past(),
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is False


# ============================================================
# Scenario 10: HubBrain env file written correctly
# ============================================================

class TestScenario10_HubBrainEnvFile:
    def _config(self):
        return {
            "hub_id": "hub-raspi-01",
            "hub_key": "super-secret-key-value",
            "server_url": "https://monitoring.example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
            "mqtt_user": "hub-raspi-01",
            "mqtt_pass": "mqtt-pass",
        }

    def test_env_file_has_all_required_vars(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        content = open(path).read()
        for key in ("HUB_ID", "HUB_KEY", "SERVER_URL", "MQTT_HOST", "MQTT_PORT"):
            assert key in content

    def test_env_file_permissions(self, tmp_path):
        path = str(tmp_path / "hubbrain.env")
        hubbrain_adapter.write_hubbrain_env(self._config(), path)
        if os.name != "nt":
            mode = os.stat(path).st_mode
            assert not (mode & stat.S_IRGRP)
            assert not (mode & stat.S_IROTH)


# ============================================================
# Scenario 11: HubBrain auto-issuance blocked
# ============================================================

class TestScenario11_HubBrainAutoIssuanceBlocked:
    def test_issue_credentials_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            hubbrain_adapter.issue_hubgate_credentials(
                provisioning_url="https://monitoring.example.com",
                device_id="raspi-01",
            )


# ============================================================
# Scenario 12: HubBrain config validation — non-https
# ============================================================

class TestScenario12_HubBrainValidationNonHttps:
    def test_non_https_server_url_raises(self):
        config = {
            "hub_id": "hub-01",
            "hub_key": "key",
            "server_url": "http://insecure.example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
            "mqtt_user": "user",
            "mqtt_pass": "pass",
        }
        with pytest.raises(ValueError, match="server_url"):
            hubbrain_adapter.validate_hub_config(config)


# ============================================================
# Scenario 13: ESP MAC normalization
# ============================================================

class TestScenario13_ESPMACNormalization:
    def test_colon_mac_to_node_id(self):
        assert esp_node_adapter.mac_to_node_id("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"

    def test_hyphen_mac_to_node_id(self):
        assert esp_node_adapter.mac_to_node_id("AA-BB-CC-DD-EE-FF") == "aabbccddeeff"

    def test_dev_name_matches_firmware(self):
        assert esp_node_adapter.mac_to_dev_name("AA:BB:CC:DD:EE:FF") == "TS-EEFF"


# ============================================================
# Scenario 14: ESP whitelist entry format
# ============================================================

class TestScenario14_ESPWhitelistFormat:
    def test_entry_has_dev_id_and_allowed(self):
        entry = esp_node_adapter.build_whitelist_entry("AA:BB:CC:DD:EE:FF", "raspi-01")
        assert entry["DEV_ID"] == "AA:BB:CC:DD:EE:FF"
        assert entry["allowed"] is True
        assert entry["gateway_id"] == "raspi-01"

    def test_mqtt_topic_matches_firmware(self):
        record = esp_node_adapter.build_node_record("raspi-01", "AA:BB:CC:DD:EE:FF", "TS")
        assert record["mqtt_topic"] == "hs109rs/ts/data"


# ============================================================
# Scenario 15: ESP cross-gateway duplicate rejection
# ============================================================

class TestScenario15_ESPDuplicateDetection:
    def test_same_mac_different_gateways_raises(self):
        entries = [
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-01", "allowed": True},
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-02", "allowed": True},
        ]
        with pytest.raises(ValueError, match="duplicate"):
            esp_node_adapter.validate_whitelist(entries)

    def test_unique_macs_pass(self):
        entries = [
            {"DEV_ID": "AA:BB:CC:DD:EE:FF", "gateway_id": "raspi-01", "allowed": True},
            {"DEV_ID": "11:22:33:44:55:66", "gateway_id": "raspi-02", "allowed": True},
        ]
        esp_node_adapter.validate_whitelist(entries)  # must not raise


# ============================================================
# Scenario 16: Provisioning API — enrollment → register → status
# ============================================================

class TestScenario16_ProvisioningAPIContract:
    def test_enroll_then_register_then_status(self, client):
        # Enroll
        enroll_resp = client.post(
            "/api/v2/provisioning/devices",
            json={"device_id": "raspi-int-test"},
            headers={"Authorization": "Bearer test-admin-token-with-enough-entropy"},
        )
        assert enroll_resp.status_code == 201
        password = enroll_resp.json()["password"]
        assert password  # one-time password issued

        # Register
        import base64
        creds = base64.b64encode(b"raspi-int-test:" + password.encode()).decode()
        reg_resp = client.post(
            "/api/v2/provisioning/register",
            json={"hostname": "raspi-int-test"},
            headers={"Authorization": f"Basic {creds}"},
        )
        assert reg_resp.status_code == 200
        assert reg_resp.json()["registration_status"] == "REGISTERED"

        # Status
        status_resp = client.get(
            "/api/v2/provisioning/status",
            headers={"Authorization": f"Basic {creds}"},
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["approval_status"] == "PENDING"


# ============================================================
# Scenario 17: Provisioning API — manifest blocked without approval
# ============================================================

class TestScenario17_ManifestBlockedWithoutApproval:
    def test_manifest_returns_403_when_pending(self, client):
        # Enroll + register
        enroll_resp = client.post(
            "/api/v2/provisioning/devices",
            json={"device_id": "raspi-manifest-test"},
            headers={"Authorization": "Bearer test-admin-token-with-enough-entropy"},
        )
        password = enroll_resp.json()["password"]

        import base64
        creds = base64.b64encode(b"raspi-manifest-test:" + password.encode()).decode()
        client.post(
            "/api/v2/provisioning/register",
            json={"hostname": "raspi-manifest-test"},
            headers={"Authorization": f"Basic {creds}"},
        )

        # Fetch manifest without approval → 403
        manifest_resp = client.get(
            "/api/v2/provisioning/manifest",
            headers={"Authorization": f"Basic {creds}"},
        )
        assert manifest_resp.status_code == 403


# ============================================================
# Scenario 21 (F-03): Agent runtime dependencies are declared
# ============================================================

class TestScenario21_AgentRequirements:
    AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "agent")

    def _requirements(self) -> str:
        path = os.path.join(os.path.abspath(self.AGENT_DIR), "requirements.txt")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_httpx_declared(self):
        assert "httpx" in self._requirements()

    def test_paho_mqtt_declared(self):
        assert "paho-mqtt" in self._requirements()

    def test_importable_after_install(self):
        """httpx must be importable in the test environment (it drives the loop)."""
        importlib.import_module("httpx")


# ============================================================
# Scenario 19 (F-02): Manifest carries non-secret hub_config
# ============================================================

class TestScenario19_ManifestHubConfig:
    def test_manifest_includes_hub_config_when_env_set(self, client, monkeypatch):
        monkeypatch.setenv("ZTD_HUBBRAIN_HUB_ID", "hs109rs-hub-01")
        monkeypatch.setenv("ZTD_HUBBRAIN_SERVER_URL", "https://monitoring.example.com")
        monkeypatch.setenv("ZTD_HUBBRAIN_MQTT_HOST", "mqtt.example.com")
        monkeypatch.setenv("ZTD_HUBBRAIN_MQTT_PORT", "8883")
        password, _ = self._enroll_register_approve(client)
        manifest_resp = client.get(
            "/api/v2/provisioning/manifest",
            headers={"Authorization": f"Basic {_b64('raspi-hubtest', password)}"},
        )
        assert manifest_resp.status_code == 200
        hub = manifest_resp.json().get("hub_config")
        assert hub == {
            "hub_id": "hs109rs-hub-01",
            "server_url": "https://monitoring.example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
        }

    def test_manifest_omits_hub_config_when_env_unset(self, client, monkeypatch):
        for var in ("ZTD_HUBBRAIN_HUB_ID", "ZTD_HUBBRAIN_SERVER_URL",
                    "ZTD_HUBBRAIN_MQTT_HOST", "ZTD_HUBBRAIN_MQTT_PORT"):
            monkeypatch.delenv(var, raising=False)
        password, _ = self._enroll_register_approve(client)
        manifest_resp = client.get(
            "/api/v2/provisioning/manifest",
            headers={"Authorization": f"Basic {_b64('raspi-hubtest', password)}"},
        )
        assert manifest_resp.status_code == 200
        assert manifest_resp.json().get("hub_config") is None

    def test_manifest_hub_config_never_contains_secrets(self, client, monkeypatch):
        """F-02 core security property: no HUB_KEY / MQTT_PASS ever in the manifest."""
        monkeypatch.setenv("ZTD_HUBBRAIN_HUB_ID", "hs109rs-hub-01")
        monkeypatch.setenv("ZTD_HUBBRAIN_SERVER_URL", "https://monitoring.example.com")
        monkeypatch.setenv("ZTD_HUBBRAIN_MQTT_HOST", "mqtt.example.com")
        monkeypatch.setenv("ZTD_HUBBRAIN_MQTT_PORT", "8883")
        # Placing a would-be secret in an env var the manifest pipeline reads:
        # the only env vars hub_config_from_env() consumes are the four
        # non-secret ones. Prove no other env value leaks into the response.
        monkeypatch.setenv("ZTD_HUBBRAIN_HUB_KEY", "SHOULD-NOT-APPEAR-hub-secret")
        monkeypatch.setenv("ZTD_HUBBRAIN_MQTT_PASS", "SHOULD-NOT-APPEAR-mqtt-secret")
        password, _ = self._enroll_register_approve(client)
        manifest_resp = client.get(
            "/api/v2/provisioning/manifest",
            headers={"Authorization": f"Basic {_b64('raspi-hubtest', password)}"},
        )
        body = manifest_resp.json()
        blob = json.dumps(body)
        assert "hub_key" not in blob.lower()
        assert "mqtt_pass" not in blob.lower()
        assert "SHOULD-NOT-APPEAR" not in blob

    def _enroll_register_approve(self, client) -> tuple[str, dict]:
        from src.provisioning.auth import credential_hash
        from src.provisioning.models import ProvisioningBase, RegisteredDevice
        from test_provisioning_v2 import approve
        # enroll + register via API, then approve via monitoring endpoint
        enroll = client.post(
            "/api/v2/provisioning/devices",
            json={"device_id": "raspi-hubtest"},
            headers={"Authorization": "Bearer test-admin-token-with-enough-entropy"},
        )
        assert enroll.status_code == 201
        password = enroll.json()["password"]
        client.post(
            "/api/v2/provisioning/register",
            json={"hostname": "raspi-hubtest"},
            headers={"Authorization": f"Basic {_b64('raspi-hubtest', password)}"},
        )
        approve(client, ("raspi-hubtest", password))
        return password, {}



class TestScenario18_DualServerStatusClassification:
    """Pure logic — mirrors dashboard monitoringStatus.mjs behavior in Python."""

    def _classify(self, device: dict) -> dict:
        """Python mirror of classifyDualServerStatus JS function."""
        reg = str(device.get("registration_status", "")).upper()
        approval = str(device.get("approval_status", "")).upper()
        expires_raw = device.get("approval_expires_at")

        provisioning = "connected" if reg == "REGISTERED" else "pending"

        monitoring = "unlinked"
        if approval == "APPROVED" and expires_raw:
            try:
                expires = datetime.datetime.fromisoformat(expires_raw)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=datetime.UTC)
                monitoring = "linked" if expires > datetime.datetime.now(datetime.UTC) else "unlinked"
            except (ValueError, TypeError):
                pass
        elif approval == "PENDING":
            monitoring = "pending"

        return {"provisioning": provisioning, "monitoring": monitoring}

    def test_registered_approved_not_expired_is_connected_linked(self):
        result = self._classify({
            "registration_status": "REGISTERED",
            "approval_status": "APPROVED",
            "approval_expires_at": _future(),
        })
        assert result == {"provisioning": "connected", "monitoring": "linked"}

    def test_enrolled_pending_is_pending_pending(self):
        result = self._classify({
            "registration_status": "ENROLLED",
            "approval_status": "PENDING",
            "approval_expires_at": None,
        })
        assert result["provisioning"] == "pending"
        assert result["monitoring"] == "pending"

    def test_registered_expired_is_connected_unlinked(self):
        result = self._classify({
            "registration_status": "REGISTERED",
            "approval_status": "APPROVED",
            "approval_expires_at": _past(),
        })
        assert result == {"provisioning": "connected", "monitoring": "unlinked"}

    def test_registered_revoked_is_connected_unlinked(self):
        result = self._classify({
            "registration_status": "REGISTERED",
            "approval_status": "REVOKED",
            "approval_expires_at": None,
        })
        assert result == {"provisioning": "connected", "monitoring": "unlinked"}
