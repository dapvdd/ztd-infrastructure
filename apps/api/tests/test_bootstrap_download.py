"""Secret-free bootstrap boundary regression tests."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.routes.bootstrap import BootstrapRequest, build_script


def valid_request(**overrides):
    base = {
        "device_name": "raspi-lab-01",
        "connection_type": "Wired",
        "ztd_device_id": "raspi-lab-01",
        "provisioning_url": "https://provision.example",
        "monitoring_hub_id": "hub-lab-01",
        "monitoring_url": "https://monitor.example",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("field", ["wifi_password", "hub_key", "mqtt_password", "tailscale_auth_key", "private_key"])
def test_secret_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        BootstrapRequest(**valid_request(**{field: "never-send-this-secret"}))


@pytest.mark.parametrize("identity", ["", "other-id", "raspi-../../bad", "raspi-a\nBAD=1"])
def test_device_identity_is_required_and_validated(identity):
    values = valid_request()
    values["ztd_device_id"] = identity
    with pytest.raises(ValidationError):
        BootstrapRequest(**values)


def test_missing_device_identity_is_rejected():
    values = valid_request()
    del values["ztd_device_id"]
    with pytest.raises(ValidationError):
        BootstrapRequest(**values)


@pytest.mark.parametrize("url", ["http://plain.example", "https://user:secret@example.com", "https://example.com/?token=secret", "https://example.com/#secret"])
def test_server_urls_cannot_disable_tls_or_carry_credentials(url):
    values = valid_request()
    values["provisioning_url"] = url
    with pytest.raises(ValidationError):
        BootstrapRequest(**values)


def test_wifi_generation_does_not_require_password():
    values = valid_request()
    values.update(connection_type="Wi-Fi", wifi_ssid="Lab ' $(literal)")
    script = build_script(BootstrapRequest(**values))
    assert script.startswith("#!/bin/bash\n")
    assert "never-send-this-secret" not in script


def test_embedded_payload_contains_exact_authoritative_executables():
    import base64
    import hashlib
    import io
    import tarfile
    from src.routes import bootstrap
    payload, digest = bootstrap.agent_payload()
    archive = base64.b64decode(payload, validate=True)
    assert hashlib.sha256(archive).hexdigest() == digest
    root = Path(__file__).resolve().parents[2] / "agent"
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        for name in ("agent_v2.py", "hubbrain_adapter.py"):
            assert bundle.extractfile(name).read() == (root / name).read_bytes()
        assert bundle.extractfile("requirements.lock").read().count(b"--hash=sha256:") >= 8
        assert len([n for n in bundle.getnames() if n.endswith(".whl")]) >= 8


def test_payload_is_reproducible():
    from src.routes import bootstrap
    assert bootstrap.agent_payload() == bootstrap.agent_payload()


def test_installer_rejects_corrupt_payload_before_writing(tmp_path):
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "agent" / "bootstrap_install.py"
    assert path.is_file(), "Runtime installer must ship with executable payload"
    spec = importlib.util.spec_from_file_location("bootstrap_install", path)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    with pytest.raises(ValueError, match="integrity"):
        installer.unpack_payload(b"tampered", "0" * 64, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_runtime_installer_extracts_verified_payload(tmp_path):
    import base64
    import importlib.util
    from src.routes.bootstrap import agent_payload
    path = Path(__file__).resolve().parents[2] / "agent" / "bootstrap_install.py"
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("bootstrap_install", path)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    payload, digest = agent_payload()
    installer.unpack_payload(base64.b64decode(payload), digest, tmp_path)
    assert (tmp_path / "agent_v2.py").read_bytes() == (path.parent / "agent_v2.py").read_bytes()


def test_runtime_installer_is_idempotent_on_rerun(tmp_path):
    import base64
    import importlib.util
    from src.routes.bootstrap import agent_payload
    path = Path(__file__).resolve().parents[2] / "agent" / "bootstrap_install.py"
    spec = importlib.util.spec_from_file_location("bootstrap_install", path)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    payload, digest = agent_payload()
    installer.unpack_payload(base64.b64decode(payload), digest, tmp_path)
    # Re-running unpack_payload into the same destination must succeed idempotently
    installer.unpack_payload(base64.b64decode(payload), digest, tmp_path)
    assert (tmp_path / "agent_v2.py").is_file()


def test_script_contains_embedded_payload_and_verified_hash():
    req = BootstrapRequest(**valid_request())
    script = build_script(req)
    assert "PAYLOAD_SHA256=" in script
    assert "PAYLOAD_B64=" in script
    assert "sha256sum" in script
    assert "Expected $PAYLOAD_SHA256" in script


def test_script_has_runtime_prompts_and_networkmanager_stdin_security():
    req = BootstrapRequest(**valid_request(connection_type="Wi-Fi", wifi_ssid="TestSSID"))
    script = build_script(req)
    # Password must NOT be embedded as variable or cleartext
    assert "WIFI_PASSWORD=" not in script.split("echo \"======================================")[0]
    assert "read -r -s" in script
    # Secret must be passed via stdin to nmcli connection edit, avoiding command line arguments
    assert "nmcli connection edit" in script
    assert "set wifi-sec.psk $WIFI_PASSWORD" in script
    assert "unset WIFI_PASSWORD" in script


def test_script_has_atomic_writes_and_staging_cleanup():
    req = BootstrapRequest(**valid_request())
    script = build_script(req)
    assert "mktemp -d /tmp/ztd-payload." in script
    assert "trap cleanup_staging EXIT ERR" in script
    assert "agent.env.tmp." in script
    assert "ztd-agent-v2.service.tmp." in script
    assert "pip install --no-index" in script


def test_script_passes_bash_syntax_check():
    import os
    import shutil
    import subprocess
    req = BootstrapRequest(**valid_request(connection_type="Wi-Fi", wifi_ssid="TestSSID"))
    script = build_script(req)
    # Ensure git bash is found if on Windows
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    bash = shutil.which("bash") or (git_bash if os.path.isfile(git_bash) else None)
    if not bash:
        pytest.skip("bash not available on this environment")
    proc = subprocess.run([bash, "-n"], input=script, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"Bash syntax check failed: {proc.stderr}"


# ===========================================================================
# BFF Authenticated Generation Boundary Tests (Task 2)
# ===========================================================================

@pytest.fixture()
def bff_session_env(tmp_path, monkeypatch):
    secret = "x" * 48
    htpasswd = tmp_path / "htpasswd"
    htpasswd.write_text("admin:$apr1$ZtdTestS$hR7.FczfgYxiJy5SINIdd/\n", encoding="utf-8")
    monkeypatch.setenv("ZTD_DASHBOARD_SESSION_SECRET", secret)
    monkeypatch.setenv("ZTD_DASHBOARD_HTPASSWD", str(htpasswd))
    monkeypatch.setenv("ZTD_PROVISIONING_ADMIN_TOKEN", "test-admin-token-with-enough-entropy")
    monkeypatch.delenv("ZTD_COOKIE_SECURE", raising=False)
    from src.routes.dashboard_bff import _rate_limit_history
    _rate_limit_history.clear()
    yield secret
    _rate_limit_history.clear()


def _auth_client(client, secret, username="admin"):
    from itsdangerous import URLSafeTimedSerializer
    token = URLSafeTimedSerializer(secret, salt="ztd-dashboard-session").dumps({"u": username, "n": "1234567890abcdef"})
    client.cookies.set("ztd_session", token)
    return client


def test_bff_bootstrap_requires_authenticated_session(bff_session_env):
    from fastapi.testclient import TestClient
    from src.main import app
    client = TestClient(app)
    resp = client.post("/api/dashboard/bootstrap/raspberry", json=valid_request())
    assert resp.status_code == 401
    assert "Dashboard session required" in resp.text


def test_bff_bootstrap_authenticated_generates_script(bff_session_env):
    from fastapi.testclient import TestClient
    from src.main import app
    client = _auth_client(TestClient(app), bff_session_env)
    resp = client.post(
        "/api/dashboard/bootstrap/raspberry",
        json=valid_request(),
        headers={"Host": "localhost", "Origin": "http://localhost"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Content-Disposition") == 'attachment; filename="bootstrap-raspberry.sh"'
    assert "no-store" in resp.headers.get("Cache-Control", "")
    assert resp.headers.get("Pragma") == "no-cache"
    assert "nosniff" in resp.headers.get("X-Content-Type-Options", "")
    assert "text/x-shellscript" in resp.headers.get("Content-Type", "")
    assert resp.text.startswith("#!/bin/bash\n")
    assert "PAYLOAD_SHA256=" in resp.text


def test_bff_bootstrap_rejects_csrf(bff_session_env):
    from fastapi.testclient import TestClient
    from src.main import app
    client = _auth_client(TestClient(app), bff_session_env)
    # Sec-Fetch-Site: cross-site
    resp = client.post(
        "/api/dashboard/bootstrap/raspberry",
        json=valid_request(),
        headers={"sec-fetch-site": "cross-site"},
    )
    assert resp.status_code == 403

    # Malicious Origin
    resp2 = client.post(
        "/api/dashboard/bootstrap/raspberry",
        json=valid_request(),
        headers={"Host": "localhost", "Origin": "https://evil.attacker.com"},
    )
    assert resp2.status_code == 403


def test_bff_bootstrap_rejects_oversized_payload(bff_session_env):
    from fastapi.testclient import TestClient
    from src.main import app
    client = _auth_client(TestClient(app), bff_session_env)
    # Content-Length > 16KB
    headers = {"Host": "localhost", "Content-Length": "20000"}
    resp = client.post("/api/dashboard/bootstrap/raspberry", json=valid_request(), headers=headers)
    assert resp.status_code == 413


def test_bff_bootstrap_rate_limiting(bff_session_env):
    from fastapi.testclient import TestClient
    from src.main import app
    client = _auth_client(TestClient(app), bff_session_env)
    headers = {"Host": "localhost", "Origin": "http://localhost"}
    status_codes = []
    for _ in range(12):
        resp = client.post("/api/dashboard/bootstrap/raspberry", json=valid_request(), headers=headers)
        status_codes.append(resp.status_code)
    assert 429 in status_codes


def test_bff_bootstrap_rejects_secret_fields(bff_session_env):
    from fastapi.testclient import TestClient
    from src.main import app
    client = _auth_client(TestClient(app), bff_session_env)
    headers = {"Host": "localhost", "Origin": "http://localhost"}
    body = valid_request(wifi_password="super-secret-password")
    resp = client.post("/api/dashboard/bootstrap/raspberry", json=body, headers=headers)
    assert resp.status_code == 422
    assert "super-secret-password" not in resp.text


