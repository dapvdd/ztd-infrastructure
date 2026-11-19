"""Independent-review regressions against real API and persistence."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_provisioning_v2 import (
    ADMIN,
    MODULE,
    PREFIX,
    approve,
    decision,
    enroll,
    register,
)
from test_provisioning_v2 import isolated_db as isolated_db

from src.main import app
from src.provisioning.models import Assignment, RegisteredDevice


def test_delayed_revocation_invalidates_prior_grant():
    client = TestClient(app)
    auth = enroll(client)
    register(client, auth)
    original = decision()
    assert approve(client, auth, original).status_code == 200
    revoked = decision("REVOKED", 2)
    revoked["expires_at"] = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert approve(client, auth, revoked).status_code == 200
    assert client.get(PREFIX + "/manifest", auth=auth).status_code == 403
    assert approve(client, auth, revoked).status_code == 200
    assert approve(client, auth, original).status_code == 409
    assert client.get(PREFIX + "/status", auth=auth).json()["approval_revision"] == 2


def test_failed_assignment_does_not_commit_partial_state(isolated_db):
    client = TestClient(app)
    auth = enroll(client)
    for name in ("one", "two"):
        assert (
            client.put(
                PREFIX + f"/modules/{name}", headers=ADMIN, json=MODULE
            ).status_code
            == 200
        )
    path = PREFIX + f"/devices/{auth[0]}/assignments/"
    assert client.put(path + "one", headers=ADMIN, json={}).status_code == 200
    client.put(
        PREFIX + "/modules/one", headers=ADMIN, json={**MODULE, "approved": False}
    )
    assert client.put(path + "two", headers=ADMIN, json={}).status_code == 409
    with Session(isolated_db) as db:
        assert db.get(Assignment, (auth[0], "two")) is None
        assert db.get(RegisteredDevice, auth[0]).configuration_revision == 1


def test_replacement_approval_does_not_restore_withdrawn_snapshot():
    client = TestClient(app)
    auth = enroll(client)
    register(client, auth)
    approve(client, auth)
    module = PREFIX + "/modules/temperature"
    assignment = PREFIX + f"/devices/{auth[0]}/assignments/temperature"
    client.put(module, headers=ADMIN, json=MODULE)
    client.put(assignment, headers=ADMIN, json={})
    client.put(module, headers=ADMIN, json={**MODULE, "approved": False})
    client.put(module, headers=ADMIN, json={**MODULE, "commit": "b" * 40})
    assert client.get(PREFIX + "/manifest", auth=auth).status_code == 409
    assert client.put(assignment, headers=ADMIN, json={}).status_code == 200
    assert (
        client.get(PREFIX + "/manifest", auth=auth).json()["modules"][0]["commit"]
        == "b" * 40
    )
