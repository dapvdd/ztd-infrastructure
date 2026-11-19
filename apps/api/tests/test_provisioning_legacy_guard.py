"""Enrolled devices cannot bypass approval through the legacy MQTT API.

Sprint 5 note: the legacy device endpoints now require an ADMIN dashboard
session (RBAC); this test logs in as an in-memory admin first. The 409
approval-guard behavior under test is unchanged.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from test_provisioning_v2 import isolated_db as isolated_db  # noqa: F401

from src.main import app


@pytest.fixture()
def admin_client(isolated_db, monkeypatch):
    """Provisioning-only fixture + an ADMIN central-auth session.

    NOTE: the isolated_db fixture from test_provisioning_v2 creates the
    provisioning tables against ITS engine and wires get_db to it. We must
    reuse THAT engine for the auth tables too, or provisioning data written
    through get_db and the auth lookup would hit different databases.
    """
    from src.database import get_db
    from src.auth.models import AppUser, AuthBase
    from src.auth import service as auth_service
    from src.auth.service import hash_password

    # Reuse the SAME engine the isolated_db fixture installed via the
    # dependency override: pull it back out of the generator closure.
    override = app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    try:
        bind = db.get_bind()
        AuthBase.metadata.create_all(bind)
    finally:
        try:
            gen.close()
        except Exception:
            pass

    auth_service._rate_buckets.clear()
    monkeypatch.setenv("ZTD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("ZTD_ARGON2_MEMORY_COST", "1024")
    try:
        with Session(bind) as s:
            s.add(AppUser(
                username="admin",
                password_hash=hash_password("Correct-Horse-9!"),
                role="ADMIN", is_active=True,
            ))
            s.commit()
        client = TestClient(app)
        r = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Correct-Horse-9!"},
        )
        assert r.status_code == 200, r.text
        yield client
    finally:
        app.dependency_overrides.clear()
        auth_service._rate_buckets.clear()


def test_legacy_config_and_delete_reject_enrolled_device(admin_client):
    client = admin_client
    auth = _enroll(client)
    assert (
        client.post(
            f"/api/v1/devices/{auth[0]}/config", json={"modules": []}
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/devices/{auth[0]}").status_code == 409


def _enroll(client):
    from test_provisioning_v2 import enroll as _enroll_impl

    return _enroll_impl(client)
