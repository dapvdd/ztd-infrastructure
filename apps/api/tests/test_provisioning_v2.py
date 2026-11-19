"""Behavioral provisioning contracts; no production service connections."""

from datetime import UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.database import get_db
from src.main import app


@pytest.fixture(autouse=True)
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
    monkeypatch.setenv(
        "ZTD_PROVISIONING_ADMIN_TOKEN", "test-admin-token-with-enough-entropy"
    )
    monkeypatch.setenv(
        "ZTD_MONITORING_TOKEN", "test-monitoring-token-with-enough-entropy"
    )
    monkeypatch.setenv(
        "ZTD_MODULE_REPOSITORIES", "https://github.com/NICEganteng/modulraspipmld.git"
    )
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


ADMIN = {"Authorization": "Bearer test-admin-token-with-enough-entropy"}
MONITORING = {"Authorization": "Bearer test-monitoring-token-with-enough-entropy"}
PREFIX = "/api/v2/provisioning"


def enroll(client, device_id="raspi-test-01"):
    response = client.post(
        PREFIX + "/devices", headers=ADMIN, json={"device_id": device_id}
    )
    assert response.status_code == 201, response.text
    return (device_id, response.json()["password"])


def register(client, auth):
    return client.post(PREFIX + "/register", auth=auth, json={"hostname": auth[0]})


def test_registration_is_persistent_idempotent_and_gated():
    client = TestClient(app)
    auth = enroll(client)
    first = register(client, auth)
    assert first.status_code == 200
    assert first.json()["registration_status"] == "REGISTERED"
    assert first.json()["approval_status"] == "PENDING"
    assert register(client, auth).json() == first.json()
    assert client.get(PREFIX + "/status", auth=auth).json() == first.json()
    assert client.get(PREFIX + "/manifest", auth=auth).status_code == 403
    assert (
        client.post(
            PREFIX + "/devices", headers=ADMIN, json={"device_id": auth[0]}
        ).status_code
        == 409
    )
    assert len(client.get(PREFIX + "/devices", headers=ADMIN).json()) == 1
    assert "password" not in client.get(PREFIX + "/devices", headers=ADMIN).text


@pytest.mark.parametrize(
    "payload",
    [
        {"device_id": "bad"},
        {"device_id": "raspi-test-01", "approval_status": "APPROVED"},
    ],
)
def test_invalid_enrollment(payload):
    assert (
        TestClient(app)
        .post(PREFIX + "/devices", headers=ADMIN, json=payload)
        .status_code
        == 422
    )


def test_invalid_registration_and_credentials():
    client = TestClient(app)
    auth = enroll(client)
    assert (
        client.post(
            PREFIX + "/register", auth=auth, json={"hostname": "wrong"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            PREFIX + "/register",
            auth=auth,
            json={"hostname": auth[0], "approval_status": "APPROVED"},
        ).status_code
        == 422
    )
    assert (
        client.get(PREFIX + "/status", auth=(auth[0], "incorrect")).status_code == 401
    )
    assert client.get(PREFIX + "/manifest").status_code == 401
    assert client.get(PREFIX + "/devices", auth=auth).status_code == 401


def decision(status="APPROVED", revision=1):
    from datetime import datetime, timedelta

    return {
        "schema_version": "1",
        "event_id": f"event-{revision}",
        "revision": revision,
        "status": status,
        "actor": "monitoring:technician-7",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }


def approve(client, auth, payload=None):
    return client.put(
        PREFIX + f"/integrations/monitoring/devices/{auth[0]}/approval",
        headers=MONITORING,
        json=payload or decision(),
    )


def test_external_approval_replay_revocation_and_manifest():
    client = TestClient(app)
    auth = enroll(client)
    register(client, auth)
    payload = decision()
    assert approve(client, auth, payload).status_code == 200
    manifest = client.get(PREFIX + "/manifest", auth=auth)
    assert manifest.status_code == 200
    assert manifest.json()["modules"] == []
    assert manifest.json()["assignment_status"] == "EMPTY"
    assert manifest.json()["schema_version"] == "2"
    assert client.get(PREFIX + "/manifest", auth=auth).json() == manifest.json()
    assert approve(client, auth, payload).status_code == 200
    assert approve(client, auth, decision("REVOKED", 1)).status_code == 409
    assert approve(client, auth, decision("REVOKED", 2)).status_code == 200
    assert client.get(PREFIX + "/manifest", auth=auth).status_code == 403
    assert approve(client, auth, payload).status_code == 409
    assert approve(client, auth, decision("APPROVED", 3)).status_code == 409


def test_approval_requires_monitoring_identity_and_registration(monkeypatch):
    client = TestClient(app)
    auth = enroll(client)
    path = PREFIX + f"/integrations/monitoring/devices/{auth[0]}/approval"
    assert client.put(path, auth=auth, json=decision()).status_code == 401
    assert client.put(path, headers=ADMIN, json=decision()).status_code == 401
    assert approve(client, auth).status_code == 409
    register(client, auth)
    monkeypatch.delenv("ZTD_MONITORING_TOKEN")
    assert approve(client, auth).status_code == 503
    assert client.get(PREFIX + "/manifest", auth=auth).status_code == 403


def test_rejected_and_expired_devices_cannot_fetch_manifest():
    from datetime import datetime, timedelta

    client = TestClient(app)
    auth = enroll(client)
    register(client, auth)
    assert approve(client, auth, decision("REJECTED")).status_code == 200
    assert client.get(PREFIX + "/manifest", auth=auth).status_code == 403
    second = enroll(client, "raspi-test-02")
    register(client, second)
    payload = decision()
    payload["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert approve(client, second, payload).status_code == 422


MODULE = {
    "repo_url": "https://github.com/NICEganteng/modulraspipmld.git",
    "commit": "a" * 40,
    "approved": True,
}


def test_assignments_are_authorized_validated_and_synchronized():
    client = TestClient(app)
    auth = enroll(client)
    register(client, auth)
    approve(client, auth)
    path = PREFIX + f"/devices/{auth[0]}/assignments/temperature"
    assert (
        client.put(PREFIX + "/modules/temperature", auth=auth, json=MODULE).status_code
        == 401
    )
    assert client.put(path, headers=ADMIN, json={}).status_code == 404
    assert (
        client.put(
            PREFIX + "/modules/temperature", headers=ADMIN, json=MODULE
        ).status_code
        == 200
    )
    assert client.put(path, auth=auth, json={}).status_code == 401
    assigned = client.put(
        path, headers=ADMIN, json={"configuration": {"sample_interval_seconds": 30}}
    )
    assert assigned.status_code == 200
    first = client.get(PREFIX + "/manifest", auth=auth).json()
    assert first["modules"][0]["commit"] == "a" * 40
    assert first["modules"][0]["configuration"] == {"sample_interval_seconds": 30}
    assert (
        client.put(
            path, headers=ADMIN, json={"configuration": {"sample_interval_seconds": 30}}
        ).status_code
        == 200
    )
    assert client.get(PREFIX + "/manifest", auth=auth).json() == first
    assert (
        client.put(
            path, headers=ADMIN, json={"configuration": {"password": "forbidden"}}
        ).status_code
        == 422
    )
    assert (
        client.put(
            PREFIX + "/modules/temperature",
            headers=ADMIN,
            json={**MODULE, "commit": "b" * 40},
        ).status_code
        == 200
    )
    updated = client.get(PREFIX + "/manifest", auth=auth).json()
    assert updated["modules"][0]["commit"] == "a" * 40  # assignments pin snapshots
    assert client.put(path, headers=ADMIN, json={}).status_code == 200
    assert (
        client.get(PREFIX + "/manifest", auth=auth).json()["modules"][0]["commit"]
        == "b" * 40
    )
    assert client.delete(path, headers=ADMIN).status_code == 204
    assert client.delete(path, headers=ADMIN).status_code == 204
    assert client.get(PREFIX + "/manifest", auth=auth).json()["modules"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"repo_url": "https://evil.example/a.git"},
        {"commit": "main"},
        {"repo_url": "file:///tmp/repo"},
    ],
)
def test_catalog_rejects_untrusted_sources(change):
    assert (
        TestClient(app)
        .put(PREFIX + "/modules/temperature", headers=ADMIN, json={**MODULE, **change})
        .status_code
        == 422
    )


def test_cross_device_manifest_denied():
    client = TestClient(app)
    auth = enroll(client)
    other = enroll(client, "raspi-other-01")
    register(client, auth)
    approve(client, auth)
    assert (
        client.get(
            PREFIX + "/manifest", auth=auth, params={"device_id": other[0]}
        ).status_code
        == 403
    )
    assert client.get(PREFIX + f"/devices/{other[0]}", auth=auth).status_code == 401


def test_unknown_device_cannot_register() -> None:
    # Removing device authentication would let arbitrary identities enroll.
    client = TestClient(app)
    response = client.post(
        "/api/v2/provisioning/register",
        auth=("raspi-unknown", "not-a-device-credential"),
        json={"hostname": "raspi-unknown"},
    )
    assert response.status_code == 401


def test_enrollment_requires_admin() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v2/provisioning/devices", json={"device_id": "raspi-test-01"}
    )
    assert response.status_code == 401
