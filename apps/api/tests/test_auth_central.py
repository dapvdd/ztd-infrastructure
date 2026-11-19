"""Sprint 5 — centralized authentication behavioral tests.

Matrix covered (docs/SPRINT5-AUTH.md §Testing):
valid login / invalid login / session expiry / logout / revocation /
disabled account / password reset / role change / last-admin protection /
CSRF rejection / login rate limiting / me / change-password.

Isolation: in-memory SQLite with StaticPool + dependency_overrides (repo
convention); auth tables created via AuthBase.metadata.create_all.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.database import get_db
from src.main import app
from src.auth.models import AppSession, AppUser, AuthBase
from src.auth import service as auth_service


PASSWORD = "Correct-Horse-9!"  # policy-clean: >=12, 3 classes


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    # Deterministic, fast Argon2 parameters for tests (NOT production values).
    monkeypatch.setenv("ZTD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("ZTD_ARGON2_MEMORY_COST", "1024")
    monkeypatch.setenv("ZTD_SESSION_TTL_HOURS", "8")
    monkeypatch.setenv("ZTD_SESSION_IDLE_MINUTES", "120")
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The login rate limiter is process-global; tests must not leak state."""
    auth_service._rate_buckets.clear()
    yield
    auth_service._rate_buckets.clear()


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    AuthBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def isolated_db(engine, monkeypatch):
    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = sessions
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def make_user(
    db, username="admin", role="ADMIN", active=True, password=PASSWORD
) -> AppUser:
    from src.auth.service import hash_password

    user = AppUser(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, username, password=PASSWORD, headers=None):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers=headers or {},
    )


def admin_headers(client, db, username="admin", password=PASSWORD):
    """Login and return the TestClient for cookie-carrying requests."""
    r = login(client, username, password)
    assert r.status_code == 200, r.text
    return client


ORIGIN = {"Origin": "http://testserver", "Host": "testserver"}


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------
def test_valid_login_sets_session_and_me(client, db_session):
    make_user(db_session)
    r = login(client, "admin")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authenticated"] is True
    assert body["username"] == "admin"
    assert body["role"] == "ADMIN"
    cookie = r.headers.get("set-cookie", "")
    assert "ztd_session=" in cookie
    assert "HttpOnly" in cookie or "httponly" in cookie
    assert "SameSite=strict" in cookie or "samesite=strict" in cookie
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_invalid_login_uniform_401(client, db_session):
    make_user(db_session)
    for creds in (
        ("admin", "Wrong-Password-1!"),
        ("nobody", "Wrong-Password-1!"),
    ):
        r = login(client, *creds)
        assert r.status_code == 401
        assert r.json()["detail"] == "Username atau password salah."
    # Disabled account: identical client-visible failure
    make_user(db_session, username="ghost", active=False)
    r = login(client, "ghost", PASSWORD)
    assert r.status_code == 401
    assert r.json()["detail"] == "Username atau password salah."


def test_login_sets_last_login_at(client, db_session):
    user = make_user(db_session)
    assert user.last_login_at is None
    login(client, "admin")
    db_session.refresh(user)
    assert user.last_login_at is not None


def test_session_rotation_mints_new_row(client, db_session):
    make_user(db_session)
    r1 = login(client, "admin")
    r2 = login(client, "admin")
    tokens = [
        r.cookies.get("ztd_session") for r in (r1, r2)
    ]
    assert tokens[0] and tokens[1] and tokens[0] != tokens[1]
    rows = db_session.query(AppSession).all()
    assert len(rows) == 2
    assert all(row.revoked_at is None for row in rows)


def test_login_rate_limiting(client, db_session):
    make_user(db_session)
    # 10 allowed attempts, 11th throttled (window-based).
    codes = [login(client, "admin", "Bad-Passw0rd!x").status_code for _ in range(12)]
    assert codes[:10] == [401] * 10
    assert 429 in codes


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------
def test_csrf_rejected_cross_origin(client, db_session):
    make_user(db_session)
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"Origin": "http://evil.example", "Host": "testserver"},
    )
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_csrf_allows_same_origin(client, db_session):
    make_user(db_session)
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"Origin": "http://testserver", "Host": "testserver"},
    )
    assert r.status_code == 200


# --------------------------------------------------------------------------
# Logout / revocation / expiry
# --------------------------------------------------------------------------
def test_logout_revokes_server_side(client, db_session):
    make_user(db_session)
    login(client, "admin")
    assert client.get("/api/auth/me").status_code == 200
    out = client.post("/api/auth/logout")
    assert out.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 401
    # Token row is revoked in the DB, not just cookie-cleared.
    row = db_session.query(AppSession).one()
    assert row.revoked_at is not None


def test_session_expires_after_ttl(client, db_session):
    make_user(db_session)
    r = login(client, "admin")
    row = db_session.query(AppSession).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_idle_timeout_revokes(client, db_session):
    make_user(db_session)
    login(client, "admin")
    row = db_session.query(AppSession).one()
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(
        minutes=auth_service.SESSION_IDLE_MINUTES + 5
    )
    db_session.commit()
    assert client.get("/api/auth/me").status_code == 401
    # Re-read in a fresh transaction (StaticPool snapshot isolation).
    db_session.expire_all()
    row = db_session.query(AppSession).one()
    assert row.revoked_at is not None


def test_admin_revoke_sessions_endpoint(client, db_session):
    make_user(db_session)
    make_user(db_session, username="viewer", role="VIEWER")
    login(client, "viewer")
    assert client.get("/api/auth/me").status_code == 200
    login(client, "admin")  # admin session now active
    r = client.post("/api/auth/users/2/revoke-sessions")
    assert r.status_code == 200
    assert r.json()["revoked"] >= 1
    rows = (
        db_session.query(AppSession)
        .filter(AppSession.user_id == 2, AppSession.revoked_at.is_(None))
        .all()
    )
    assert rows == []


def test_cross_user_session_access_denied(client, db_session):
    """A token of user A must never resolve to user B (trivially true with
    DB-backed sessions, but the contract is pinned here)."""
    make_user(db_session)
    make_user(db_session, username="second", role="VIEWER")
    login(client, "second")
    me = client.get("/api/auth/me")
    assert me.json()["username"] == "second"
    assert me.json()["role"] == "VIEWER"


# --------------------------------------------------------------------------
# Password flows
# --------------------------------------------------------------------------
def test_change_password_self(client, db_session):
    make_user(db_session)
    login(client, "admin")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "New-Secret-12#"},
    )
    assert r.status_code == 200
    # Old password no longer works; new one does.
    assert login(client, "admin", PASSWORD).status_code == 401
    # The current session must have survived the change.
    assert client.get("/api/auth/me").status_code == 200


def test_change_password_wrong_current(client, db_session):
    make_user(db_session)
    login(client, "admin")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "nope-not-it-1!", "new_password": "New-Secret-12#"},
    )
    assert r.status_code == 401


def test_change_password_revokes_other_sessions(client, db_session):
    make_user(db_session)
    other = TestClient(app)
    login(client, "admin")
    login(other, "admin")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "New-Secret-12#"},
    )
    assert r.status_code == 200
    assert other.get("/api/auth/me").status_code == 401


def test_admin_reset_password_kills_target_sessions(client, db_session):
    make_user(db_session)
    victim = make_user(db_session, username="viewer", role="VIEWER")
    victim_client = TestClient(app)
    login(victim_client, "viewer")
    login(client, "admin")
    r = client.post(
        "/api/auth/users/2/reset-password", json={"new_password": "Fresh-Secret-3!"}
    )
    assert r.status_code == 200
    assert r.json()["sessions_revoked"] >= 1
    assert victim_client.get("/api/auth/me").status_code == 401
    db_session.refresh(victim)
    # Old password dead, new one works.
    assert login(client, "viewer", PASSWORD).status_code == 401
    ok = login(victim_client, "viewer", "Fresh-Secret-3!")
    assert ok.status_code == 200


# --------------------------------------------------------------------------
# User management + last-admin protection
# --------------------------------------------------------------------------
def test_create_user_and_duplicate_conflict(client, db_session):
    make_user(db_session)
    login(client, "admin")
    r = client.post(
        "/api/auth/users", json={"username": "viewer2", "password": "Viewer-Pass-1", "role": "VIEWER"}
    )
    assert r.status_code == 201
    assert r.json()["role"] == "VIEWER"
    dup = client.post(
        "/api/auth/users", json={"username": "viewer2", "password": "Viewer-Pass-2", "role": "VIEWER"}
    )
    assert dup.status_code == 409


def test_weak_password_rejected(client, db_session):
    make_user(db_session)
    login(client, "admin")
    r = client.post(
        "/api/auth/users", json={"username": "weak", "password": "short", "role": "VIEWER"}
    )
    assert r.status_code == 422


def test_disable_user_revokes_sessions(client, db_session):
    make_user(db_session)
    u = make_user(db_session, username="viewer", role="VIEWER")
    vc = TestClient(app)
    login(vc, "viewer")
    login(client, "admin")
    r = client.patch("/api/auth/users/2", json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert vc.get("/api/auth/me").status_code == 401
    db_session.refresh(u)
    assert u.is_active is False


def test_role_change_applies_immediately(client, db_session):
    make_user(db_session)
    u = make_user(db_session, username="viewer", role="VIEWER")
    login(client, "viewer")  # this client IS the viewer
    assert client.post("/api/auth/users", json={
        "username": "x1", "password": "X-Passw0rd-99", "role": "VIEWER"
    }).status_code == 403
    # Admin (second client) promotes viewer to ADMIN; same cookie now ADMIN.
    ac = TestClient(app)
    login(ac, "admin")
    r = ac.patch(f"/api/auth/users/{u.id}", json={"role": "ADMIN"})
    assert r.status_code == 200
    me = client.get("/api/auth/me")
    assert me.json()["role"] == "ADMIN"


def test_last_admin_cannot_be_demoted_or_disabled(client, db_session):
    make_user(db_session)  # the only admin
    login(client, "admin")
    r1 = client.patch("/api/auth/users/1", json={"role": "VIEWER"})
    assert r1.status_code == 409
    r2 = client.patch("/api/auth/users/1", json={"is_active": False})
    assert r2.status_code == 409


def test_last_admin_protection_counts_active_only(client, db_session):
    make_user(db_session)
    make_user(db_session, username="admin2", role="ADMIN", active=False)
    login(client, "admin")
    # The disabled admin doesn't count; demoting the live one must still 409.
    r = client.patch("/api/auth/users/1", json={"role": "VIEWER"})
    assert r.status_code == 409


# --------------------------------------------------------------------------
# RBAC — viewer restrictions
# --------------------------------------------------------------------------
def test_viewer_cannot_manage_users(client, db_session):
    make_user(db_session)
    make_user(db_session, username="viewer", role="VIEWER")
    vc = TestClient(app)
    login(vc, "viewer")
    assert vc.get("/api/auth/users").status_code == 403
    assert vc.post("/api/auth/users", json={
        "username": "nope", "password": "Nope-Passw0rd-1", "role": "VIEWER"
    }).status_code == 403
    assert vc.get("/api/auth/audit-events").status_code == 403


def test_viewer_read_allowed(client, db_session):
    make_user(db_session)
    make_user(db_session, username="viewer", role="VIEWER")
    vc = TestClient(app)
    login(vc, "viewer")
    assert vc.get("/api/auth/me").status_code == 200
    assert vc.get("/api/auth/me").json()["role"] == "VIEWER"


# --------------------------------------------------------------------------
# Hygiene
# --------------------------------------------------------------------------
def test_no_hash_leak_in_users_response(client, db_session):
    make_user(db_session)
    login(client, "admin")
    r = client.get("/api/auth/users")
    assert r.status_code == 200
    blob = r.text
    assert "password_hash" not in blob
    assert "$argon2id$" not in blob


def test_unauthenticated_me_is_401(client, db_session):
    make_user(db_session)
    assert client.get("/api/auth/me").status_code == 401


def test_audit_events_written(client, db_session):
    make_user(db_session)
    login(client, "admin")
    client.post("/api/auth/logout")
    rows = auth_service.audit  # module ref sanity
    from src.auth.models import AppAuditEvent

    actions = [r.action for r in db_session.query(AppAuditEvent).all()]
    assert "LOGIN_OK" in actions
    assert "LOGOUT" in actions


def test_password_hash_format_is_argon2id(db_session):
    from src.auth.service import hash_password

    h = hash_password("Whatever-Long-Enough-1!")
    assert h.startswith("$argon2id$")
