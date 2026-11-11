"""Enrolled devices cannot bypass approval through the legacy MQTT API."""

from fastapi.testclient import TestClient
from test_provisioning_v2 import enroll
from test_provisioning_v2 import isolated_db as isolated_db

from src.main import app


def test_legacy_config_and_delete_reject_enrolled_device():
    client = TestClient(app)
    auth = enroll(client)
    assert (
        client.post(
            f"/api/v1/devices/{auth[0]}/config", json={"modules": []}
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/devices/{auth[0]}").status_code == 409
