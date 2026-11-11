"""Opt-in real PostgreSQL migration/concurrency checks in a unique test schema."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from test_provisioning_v2 import ADMIN, MODULE, PREFIX, approve, register

from src.database import get_db
from src.main import app


@pytest.fixture
def postgres(monkeypatch):
    url = os.environ.get("ZTD_TEST_POSTGRES_URL")
    if not url:
        pytest.skip(
            "Set ZTD_TEST_POSTGRES_URL to an isolated local PostgreSQL database"
        )
    base = create_engine(url)
    assert base.url.host in {
        "127.0.0.1",
        "localhost",
    }, "Tests only accept local PostgreSQL"
    schema = "ztd_test_" + uuid.uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    migration_dir = Path(__file__).resolve().parents[3] / "postgres" / "migrations"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(
            (migration_dir / "003_provisioning_v2.up.sql").read_text()
        )

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
    monkeypatch.setenv("ZTD_MODULE_REPOSITORIES", MODULE["repo_url"])
    try:
        yield engine
        with engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.exec_driver_sql(
                (migration_dir / "003_provisioning_v2.down.sql").read_text()
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables WHERE table_schema = :schema"
                    ),
                    {"schema": schema},
                ).scalar_one()
                == 0
            )
            connection.exec_driver_sql(
                (migration_dir / "003_provisioning_v2.up.sql").read_text()
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_postgres_concurrent_enrollment_registration_and_assignment(postgres):
    def enrollment(_):
        return TestClient(app).post(
            PREFIX + "/devices",
            headers=ADMIN,
            json={"device_id": "raspi-concurrent-01"},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(enrollment, range(8)))
    assert sorted(response.status_code for response in responses) == [201] + [409] * 7
    password = next(
        response.json()["password"]
        for response in responses
        if response.status_code == 201
    )
    auth = ("raspi-concurrent-01", password)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: register(TestClient(app), auth), range(8)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    client = TestClient(app)
    assert approve(client, auth).status_code == 200
    assert (
        client.put(
            PREFIX + "/modules/temperature", headers=ADMIN, json=MODULE
        ).status_code
        == 200
    )
    path = PREFIX + f"/devices/{auth[0]}/assignments/temperature"
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(
                lambda _: TestClient(app).put(path, headers=ADMIN, json={}), range(8)
            )
        )
    assert all(response.status_code == 200 for response in responses)
    manifest = client.get(PREFIX + "/manifest", auth=auth).json()
    assert manifest["configuration_revision"] == 1
    assert len(manifest["modules"]) == 1


def test_postgres_migration_preserves_legacy_tables(postgres):
    with postgres.begin() as connection:
        connection.execute(text("CREATE TABLE devices (id varchar(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO devices VALUES ('legacy-test')"))
    # The fixture expects only v2 tables after downgrade; inspect legacy separately.
    migration_dir = Path(__file__).resolve().parents[3] / "postgres" / "migrations"
    with postgres.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.exec_driver_sql(
            (migration_dir / "003_provisioning_v2.down.sql").read_text()
        )
        assert (
            connection.execute(text("SELECT id FROM devices")).scalar_one()
            == "legacy-test"
        )
        connection.exec_driver_sql(
            (migration_dir / "003_provisioning_v2.up.sql").read_text()
        )
        connection.execute(text("DROP TABLE devices"))
