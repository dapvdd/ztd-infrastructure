"""Tests for the dashboard BFF session boundary (F-04, F-05).

Security properties verified:
- Login validates against an nginx htpasswd file; wrong creds are 401.
- Session cookies are HMAC-signed, HttpOnly, SameSite=Strict.
- Fail closed: no secret or no htpasswd file configured => 503.
- The admin bearer token NEVER appears in any response body.
- Proxied provisioning calls require a valid session; unauthenticated calls 401.
- With a session, upstream calls carry `Authorization: Bearer <admin token>`
  injected server-side only.
"""

import base64
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.main import app  # noqa: E402

SESSION = "/api/dashboard/session"
PROXY = "/api/dashboard/v2/provisioning/devices"
COOKIE_NAME = "ztd_session"

ADMIN_TOKEN = "test-admin-token-with-enough-entropy"

HTPASSWD = (
    # admin:adminpass123 (apr1, generated via: openssl passwd -apr1 -salt ZtdTestSalt adminpass123)
    "admin:$apr1$ZtdTestS$hR7.FczfgYxiJy5SINIdd/\n"
)


def _htpasswd_path(tmp_path, content=HTPASSWD):
    p = tmp_path / "htpasswd"
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture()
def bff_env(tmp_path, monkeypatch):
    # DB isolation — same pattern as test_provisioning_v2.isolated_db: the
    # proxy forwards into the provisioning API, which needs a database.
    from src.database import get_db
    from src.provisioning.models import ProvisioningBase

    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    ProvisioningBase.metadata.create_all(engine)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = sessions
    monkeypatch.setenv("ZTD_PROVISIONING_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("ZTD_MONITORING_TOKEN", "test-monitoring-token-with-enough-entropy")
    monkeypatch.setenv("ZTD_MODULE_REPOSITORIES", "https://github.com/NICEganteng/modulraspipmld.git")
    monkeypatch.setenv("ZTD_DASHBOARD_SESSION_SECRET", "x" * 48)
    monkeypatch.setenv("ZTD_DASHBOARD_HTPASSWD", _htpasswd_path(tmp_path))
    monkeypatch.delenv("ZTD_COOKIE_SECURE", raising=False)
    yield
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(bff_env):
    return TestClient(app)


def _login(client, user="admin", password="adminpass123"):
    return client.post(SESSION, json={"username": user, "password": password})


class TestLogin:
    def test_valid_credentials_issue_cookie(self, client):
        resp = _login(client)
        assert resp.status_code == 200
        assert COOKIE_NAME in resp.cookies

    def test_wrong_password_rejected(self, client):
        resp = _login(client, password="wrong")
        assert resp.status_code == 401

    def test_unknown_user_rejected(self, client):
        resp = _login(client, user="nobody")
        assert resp.status_code == 401

    def test_malformed_body_rejected(self, client):
        resp = client.post(SESSION, json={"user": "admin"})
        assert resp.status_code == 422


class TestCookieSecurity:
    def test_cookie_flags(self, client):
        resp = _login(client)
        set_cookie = resp.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie or "SameSite=Strict" in set_cookie

    def test_cookie_secure_flag_when_enabled(self, bff_env, monkeypatch):
        monkeypatch.setenv("ZTD_COOKIE_SECURE", "1")
        client = TestClient(app)
        resp = _login(client)
        assert "Secure" in resp.headers["set-cookie"]

    def test_logout_clears_session(self, client):
        _login(client)
        resp = client.delete(SESSION)
        assert resp.status_code == 204
        me = client.get(SESSION)
        assert me.status_code == 401


class TestFailClosed:
    def test_missing_secret_503(self, bff_env, monkeypatch):
        monkeypatch.delenv("ZTD_DASHBOARD_SESSION_SECRET", raising=False)
        client = TestClient(app)
        assert _login(client).status_code == 503

    def test_short_secret_503(self, bff_env, monkeypatch):
        monkeypatch.setenv("ZTD_DASHBOARD_SESSION_SECRET", "short")
        client = TestClient(app)
        assert _login(client).status_code == 503

    def test_missing_htpasswd_503(self, bff_env, monkeypatch):
        monkeypatch.setenv("ZTD_DASHBOARD_HTPASSWD", str(
            __import__("pathlib").Path("Z:/nonexistent/htpasswd")))
        client = TestClient(app)
        assert _login(client).status_code == 503


class TestProxyAuth:
    def test_proxy_requires_session(self, client):
        assert client.get(PROXY).status_code == 401

    def test_proxy_with_session_succeeds(self, client):
        _login(client)
        resp = client.get(PROXY)
        assert resp.status_code == 200

    def test_upstream_receives_admin_bearer(self, client, monkeypatch):
        captured = {}

        import src.routes.dashboard_bff as bff

        def fake_upstream(path, headers):
            captured["authorization"] = headers.get("Authorization", "")
            return 200, [{"device_id": "raspi-x", "registration_status": "ENROLLED",
                          "approval_status": "PENDING", "approval_revision": 0,
                          "configuration_revision": 0}]

        monkeypatch.setattr(bff, "_provisioning_request", fake_upstream)
        _login(client)
        resp = client.get(PROXY)
        assert resp.status_code == 200
        assert captured["authorization"] == f"Bearer {ADMIN_TOKEN}"

    def test_admin_token_never_in_any_response_body(self, client):
        for resp in (_login(client), client.get(PROXY), client.get(SESSION)):
            assert ADMIN_TOKEN not in resp.text
