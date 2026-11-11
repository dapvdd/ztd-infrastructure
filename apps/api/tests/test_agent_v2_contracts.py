"""
Unit tests for apps/agent/agent_v2.py pure-function contracts.

No network, no filesystem side-effects. Tests import agent_v2 pure
functions and verify state machine, retry logic, and manifest validation.
"""

import hashlib
import json
import sys
import os

import pytest

# agent_v2 lives in apps/agent, not in the api package
AGENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "agent")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

import agent_v2


class TestStateFile:
    """State JSON round-trips through load/save without mutation."""

    def test_load_missing_returns_default(self, tmp_path):
        state = agent_v2.load_state(str(tmp_path / "nonexistent.json"))
        assert state["approval_status"] == "PENDING"
        assert state["revision"] == 0
        assert state["manifest_hash"] is None
        assert state["applied_at"] is None

    def test_save_and_load_round_trip(self, tmp_path):
        path = str(tmp_path / "state.json")
        data = {
            "device_id": "raspi-test-01",
            "revision": 3,
            "approval_status": "APPROVED",
            "manifest_hash": "abc123",
            "applied_at": "2026-11-11T10:00:00+00:00",
        }
        agent_v2.save_state(path, data)
        loaded = agent_v2.load_state(path)
        assert loaded == data

    def test_state_file_is_not_world_readable(self, tmp_path):
        """State file must have permissions 0o600 (owner rw only)."""
        path = str(tmp_path / "state.json")
        agent_v2.save_state(path, {"device_id": "test", "revision": 0,
                                   "approval_status": "PENDING",
                                   "manifest_hash": None, "applied_at": None})
        import stat
        mode = os.stat(path).st_mode
        # On Windows, permission bits work differently; skip the check there.
        if os.name != "nt":
            assert not (mode & stat.S_IRGRP), "Group read must not be set"
            assert not (mode & stat.S_IROTH), "Other read must not be set"


class TestRetryBackoff:
    """Exponential backoff returns delay in configured bounds."""

    def test_first_attempt_minimum(self):
        delay = agent_v2.backoff_seconds(attempt=0, base=5, cap=300)
        assert delay == 5

    def test_second_attempt_doubles(self):
        delay = agent_v2.backoff_seconds(attempt=1, base=5, cap=300)
        assert delay == 10

    def test_third_attempt_quadruples(self):
        delay = agent_v2.backoff_seconds(attempt=2, base=5, cap=300)
        assert delay == 20

    def test_cap_is_respected(self):
        delay = agent_v2.backoff_seconds(attempt=100, base=5, cap=300)
        assert delay == 300

    def test_jitter_within_bounds(self):
        delay = agent_v2.backoff_seconds(attempt=1, base=5, cap=300, jitter=True)
        # With jitter: delay ∈ [base*2 * 0.5, base*2] = [5, 10]
        assert 5 <= delay <= 10


class TestManifestHash:
    """Manifest hash is deterministic and content-sensitive."""

    def test_same_content_same_hash(self):
        manifest = {
            "device_id": "raspi-test",
            "configuration_revision": 1,
            "modules": [{"name": "sensor", "repo_url": "https://example.com", "commit": "a" * 40}],
        }
        h1 = agent_v2.compute_manifest_hash(manifest)
        h2 = agent_v2.compute_manifest_hash(manifest)
        assert h1 == h2

    def test_different_revision_different_hash(self):
        base = {"device_id": "raspi-test", "configuration_revision": 1, "modules": []}
        modified = dict(base, configuration_revision=2)
        assert agent_v2.compute_manifest_hash(base) != agent_v2.compute_manifest_hash(modified)

    def test_hash_is_hex_string(self):
        h = agent_v2.compute_manifest_hash({"device_id": "x", "configuration_revision": 0, "modules": []})
        int(h, 16)  # must be valid hex

    def test_key_order_independent(self):
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert agent_v2.compute_manifest_hash(a) == agent_v2.compute_manifest_hash(b)


class TestApprovalGate:
    """Manifest should only be fetched when approval is APPROVED and not expired."""

    def test_approved_not_expired_permits_fetch(self):
        import datetime
        future = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)).isoformat()
        status = {
            "approval_status": "APPROVED",
            "approval_expires_at": future,
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is True

    def test_pending_blocks_fetch(self):
        import datetime
        future = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)).isoformat()
        status = {
            "approval_status": "PENDING",
            "approval_expires_at": future,
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is False

    def test_expired_approval_blocks_fetch(self):
        import datetime
        past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)).isoformat()
        status = {
            "approval_status": "APPROVED",
            "approval_expires_at": past,
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is False

    def test_missing_expires_at_blocks_fetch(self):
        status = {
            "approval_status": "APPROVED",
            "approval_expires_at": None,
            "registration_status": "REGISTERED",
        }
        assert agent_v2.should_fetch_manifest(status) is False

    def test_not_registered_blocks_fetch(self):
        import datetime
        future = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)).isoformat()
        status = {
            "approval_status": "APPROVED",
            "approval_expires_at": future,
            "registration_status": "ENROLLED",
        }
        assert agent_v2.should_fetch_manifest(status) is False


class TestMonitoringHandoff:
    """Config handoff produces correct HubBrain .env content."""

    def test_env_content_includes_all_required_keys(self):
        hub_config = {
            "hub_id": "hub-raspi-01",
            "hub_key": "secret-key-value",
            "server_url": "https://monitoring.example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 8883,
            "mqtt_user": "hub-raspi-01",
            "mqtt_pass": "mqtt-secret",
        }
        env_content = agent_v2.render_hubbrain_env(hub_config)
        assert "HUB_ID=hub-raspi-01" in env_content
        assert "HUB_KEY=secret-key-value" in env_content
        assert "SERVER_URL=https://monitoring.example.com" in env_content
        assert "MQTT_HOST=mqtt.example.com" in env_content
        assert "MQTT_PORT=8883" in env_content

    def test_env_content_no_unquoted_specials(self):
        """Values with spaces or specials must be safely quoted in the .env file."""
        hub_config = {
            "hub_id": "hub-01",
            "hub_key": "key with spaces",
            "server_url": "https://example.com",
            "mqtt_host": "mqtt.example.com",
            "mqtt_port": 1883,
            "mqtt_user": "user",
            "mqtt_pass": "pass",
        }
        env_content = agent_v2.render_hubbrain_env(hub_config)
        # Key with spaces must be quoted
        assert 'HUB_KEY="key with spaces"' in env_content or "HUB_KEY='key with spaces'" in env_content


class TestBuildRegistrationPayload:
    """Registration payload construction."""

    def test_hostname_matches_device_id(self):
        payload = agent_v2.build_registration_payload("raspi-edge-01")
        assert payload["hostname"] == "raspi-edge-01"

    def test_device_id_in_payload(self):
        payload = agent_v2.build_registration_payload("raspi-edge-01")
        assert "hostname" in payload
