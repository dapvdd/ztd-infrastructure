"""Sprint 5 — /api/auth/* routes: login, logout, me, profile, user management.

Security posture (docs/SPRINT5-AUTH.md):
- Login: rate-limited, CSRF-checked (Origin/Host + Sec-Fetch-Site), session
  rotation on every login (new session row, fixation-proof).
- All state-changing requests require same-origin + valid session; admin
  endpoints additionally require role=ADMIN via dependency.
- No public signup. First admin comes from scripts/create-first-admin.py.
- No password hashes or tokens in any response.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from src.auth.dependencies import (
    clear_session_cookie,
    get_current_admin,
    get_current_user,
    set_session_cookie,
)
from src.auth.models import AppUser
from src.auth.service import (
    AuthError,
    audit,
    assert_not_last_admin,
    hash_password,
    is_rate_limited,
    mint_session,
    password_policy_error,
    reset_rate_limit,
    resolve_session,
    revoke_all_for_user,
    revoke_session,
    verify_password,
)
from src.database import get_db

router = APIRouter(prefix="/api/auth", tags=["Central Auth"])


# --------------------------------------------------------------------------
# Origin/CSRF guard (same rules as the BFF; shared shape, local copy to avoid
# cross-module coupling for now — see docs/SPRINT5-AUTH.md §CSRF).
# --------------------------------------------------------------------------
def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin:
        try:
            from urllib.parse import urlparse

            o = urlparse(origin)
            o_host = o.netloc
        except Exception:
            return False
        if o_host and host and o_host == host:
            return True
        return False
    site = request.headers.get("sec-fetch-site", "")
    return site in ("same-origin", "same-site", "none") if site else True


def _csrf_reject(request: Request) -> JSONResponse | None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if not _same_origin(request):
        return JSONResponse(
            status_code=403, content={"detail": "CSRF check failed: cross-origin request."}
        )
    return None


def _client_ip(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for", "")
    if xf:
        return xf.split(",")[0].strip()
    return request.client.host if request.client else ""


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    password: str = Field(min_length=1, max_length=256)
    role: str = Field(pattern="^(ADMIN|VIEWER)$")

    @field_validator("username")
    @classmethod
    def username_not_reserved(cls, v: str) -> str:
        if v.lower() in {"me", "session", "logout", "login", "users"}:
            raise ValueError("Username tidak boleh memakai nama rute.")
        return v


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(ADMIN|VIEWER)$")
    is_active: bool | None = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)


class GeneratedPasswordRequest(BaseModel):
    """Admin requests a generated password for a user (returned ONCE)."""
    username: str = Field(min_length=1, max_length=64)


# --------------------------------------------------------------------------
# Response shapes
# --------------------------------------------------------------------------
def _me_payload(user: AppUser) -> dict:
    return {"authenticated": True, "username": user.username, "role": user.role}


# --------------------------------------------------------------------------
# POST /api/auth/login
# --------------------------------------------------------------------------
@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf

    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")

    if is_rate_limited(payload.username, ip):
        audit(db, "RATE_LIMITED", detail={"username": payload.username},
              source_ip=ip, user_agent=ua)
        db.commit()
        return JSONResponse(
            status_code=429,
            content={"detail": "Terlalu banyak percobaan login. Coba lagi nanti."},
            headers={"Retry-After": "60"},
        )

    user = db.execute(
        select(AppUser).where(AppUser.username == payload.username)
    ).scalar_one_or_none()

    # Uniform failure: unknown user vs bad password vs disabled are identical
    # client-side (401 + generic message), but the audit trail distinguishes.
    ok_password = False
    if user is not None and user.is_active:
        ok_password = verify_password(payload.password, user.password_hash)

    if user is None or not ok_password:
        audit(db, "LOGIN_FAIL", detail={"username": payload.username},
              target=user, source_ip=ip, user_agent=ua)
        db.commit()
        return JSONResponse(
            status_code=401,
            content={"detail": "Username atau password salah."},
        )

    # Session rotation: mint a brand-new session (fixation-proof). No reuse
    # of any prior token value.
    token, _sess = mint_session(db, user, user_agent=ua)
    user.last_login_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    reset_rate_limit(payload.username, ip)
    audit(db, "LOGIN_OK", actor=user, source_ip=ip, user_agent=ua)
    db.commit()

    body = _me_payload(user)
    set_session_cookie(response, token, request)
    return body


# --------------------------------------------------------------------------
# POST /api/auth/logout
# --------------------------------------------------------------------------
@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf
    token = request.cookies.get("ztd_session")
    resolved = resolve_session(db, token)
    revoked = revoke_session(db, token)
    if resolved is not None:
        sess, user = resolved
        audit(db, "LOGOUT", actor=user, source_ip=_client_ip(request),
              user_agent=request.headers.get("user-agent", ""))
    db.commit()
    clear_session_cookie(response, request)
    return {"authenticated": False, "revoked": revoked}


# --------------------------------------------------------------------------
# GET /api/auth/me
# --------------------------------------------------------------------------
@router.get("/me")
def me(user: AppUser = Depends(get_current_user)):
    return _me_payload(user)


# --------------------------------------------------------------------------
# POST /api/auth/change-password  (self)
# --------------------------------------------------------------------------
@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: OrmSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf
    if not verify_password(payload.current_password, user.password_hash):
        audit(db, "PASSWORD_CHANGE_FAIL", actor=user,
              detail={"reason": "wrong-current"}, source_ip=_client_ip(request))
        db.commit()
        return JSONResponse(status_code=401, content={"detail": "Password saat ini salah."})
    policy = password_policy_error(payload.new_password)
    if policy:
        return JSONResponse(status_code=422, content={"detail": policy})
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    # Invalidate every OTHER session (own session survives this request).
    revoked = revoke_all_for_user(db, user.id, except_token=request.cookies.get("ztd_session"))
    audit(db, "PASSWORD_CHANGED", actor=user, target=user,
          detail={"other_sessions_revoked": revoked}, source_ip=_client_ip(request))
    db.commit()
    return {"changed": True, "other_sessions_revoked": revoked}


# --------------------------------------------------------------------------
# User management (ADMIN only)
# --------------------------------------------------------------------------
@router.get("/users")
def list_users(
    db: OrmSession = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
):
    rows = db.execute(select(AppUser).order_by(AppUser.username)).scalars().all()
    return {"users": [r.public_dict() for r in rows]}


@router.post("/users", status_code=201)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    db: OrmSession = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf
    exists = db.execute(
        select(AppUser).where(AppUser.username == payload.username)
    ).scalar_one_or_none()
    if exists is not None:
        return JSONResponse(status_code=409, content={"detail": "Username sudah dipakai."})
    policy = password_policy_error(payload.password)
    if policy:
        return JSONResponse(status_code=422, content={"detail": policy})
    user = AppUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit(db, "USER_CREATED", actor=admin, target=user,
          detail={"role": user.role}, source_ip=_client_ip(request))
    db.commit()
    return user.public_dict()


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    request: Request,
    db: OrmSession = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf
    target = db.get(AppUser, user_id)
    if target is None:
        return JSONResponse(status_code=404, content={"detail": "User tidak ditemukan."})

    changed = {}
    sessions_to_revoke = False

    if payload.role is not None and payload.role != target.role:
        if payload.role == "VIEWER":
            # demotion — last-admin protection
            assert_not_last_admin(db, target, "demote")
        changed["role"] = {"from": target.role, "to": payload.role}
        target.role = payload.role
        # Role change applies to active sessions immediately: keep the row but
        # resolve_session re-reads the user on every request, so the new role
        # is enforced on the next request. Revoke is NOT needed for role; but
        # spec says "Apply role changes to active sessions immediately" — the
        # DB is the source of truth so this is inherent. We audit it.

    if payload.is_active is not None and payload.is_active != target.is_active:
        if payload.is_active is False:
            # disable — last-admin protection
            assert_not_last_admin(db, target, "disable")
            sessions_to_revoke = True
        changed["is_active"] = {"from": target.is_active, "to": payload.is_active}
        target.is_active = payload.is_active

    if not changed:
        return target.public_dict()

    target.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    if sessions_to_revoke:
        revoke_all_for_user(db, target.id)
        changed["sessions_revoked"] = True
    action = "ROLE_CHANGED" if "role" in changed else "USER_UPDATED"
    if "is_active" in changed:
        action = "USER_DISABLED" if target.is_active is False else "USER_ENABLED"
    audit(db, action, actor=admin, target=target, detail=changed,
          source_ip=_client_ip(request))
    db.commit()
    return target.public_dict()


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    request: Request,
    db: OrmSession = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf
    target = db.get(AppUser, user_id)
    if target is None:
        return JSONResponse(status_code=404, content={"detail": "User tidak ditemukan."})
    policy = password_policy_error(payload.new_password)
    if policy:
        return JSONResponse(status_code=422, content={"detail": policy})
    target.password_hash = hash_password(payload.new_password)
    target.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    # Invalidate ALL sessions of the target (spec: reset kills sessions).
    revoked = revoke_all_for_user(db, target.id)
    audit(db, "PASSWORD_RESET", actor=admin, target=target,
          detail={"sessions_revoked": revoked}, source_ip=_client_ip(request))
    db.commit()
    return {"reset": True, "sessions_revoked": revoked}


@router.post("/users/{user_id}/revoke-sessions")
def admin_revoke_sessions(
    user_id: int,
    request: Request,
    db: OrmSession = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
):
    csrf = _csrf_reject(request)
    if csrf is not None:
        return csrf
    target = db.get(AppUser, user_id)
    if target is None:
        return JSONResponse(status_code=404, content={"detail": "User tidak ditemukan."})
    revoked = revoke_all_for_user(db, target.id)
    audit(db, "SESSION_REVOKED", actor=admin, target=target,
          detail={"sessions_revoked": revoked}, source_ip=_client_ip(request))
    db.commit()
    return {"revoked": revoked}


# --------------------------------------------------------------------------
# Audit trail (ADMIN read-only)
# --------------------------------------------------------------------------
@router.get("/audit-events")
def audit_events(
    limit: int = 100,
    db: OrmSession = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
):
    from src.auth.models import AppAuditEvent as E

    limit = max(1, min(limit, 500))
    rows = db.execute(
        select(E).order_by(E.id.desc()).limit(limit)
    ).scalars().all()
    return {
        "events": [
            {
                "id": r.id,
                "actor_username": r.actor_username,
                "action": r.action,
                "target_username": r.target_username,
                "detail": r.detail,
                "source_ip": r.source_ip,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
