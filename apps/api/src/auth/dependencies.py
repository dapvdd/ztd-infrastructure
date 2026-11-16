"""Sprint 5 — FastAPI dependencies for centralized auth + RBAC.

Cookie: ztd_session (HttpOnly; Secure when the request is HTTPS;
SameSite=Strict). The raw token is resolved against app_sessions on every
authenticated request (server-side revocation is immediate).

Errors:
    401 — not authenticated (missing/invalid/expired/revoked session)
    403 — authenticated but role forbidden
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, Request
from sqlalchemy.orm import Session as OrmSession

from src.auth.models import AppUser
from src.auth.service import AuthError, resolve_session
from src.database import get_db


def _is_secure_request(request: Request) -> bool:
    # Behind nginx TLS termination: trust X-Forwarded-Proto set by our own
    # nginx config (proxy_set_header X-Forwarded-Proto $scheme).
    xf = request.headers.get("x-forwarded-proto", "")
    if xf:
        return xf.split(",")[0].strip() == "https"
    return request.url.scheme == "https"


def _extract_token(request: Request) -> str | None:
    return request.cookies.get("ztd_session") or None


def set_session_cookie(response, token: str, request: Request) -> None:
    """Attach the session cookie with the correct security flags."""
    response.set_cookie(
        key="ztd_session",
        value=token,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="strict",
        path="/",
        max_age=8 * 3600,
    )


def clear_session_cookie(response, request: Request) -> None:
    response.delete_cookie(
        key="ztd_session", path="/", httponly=True,
        secure=_is_secure_request(request), samesite="strict",
    )


def get_current_user(
    request: Request,
    db: OrmSession = Depends(get_db),
) -> AppUser:
    """Resolve the session cookie into the active AppUser, or 401."""
    token = _extract_token(request)
    resolved = resolve_session(db, token)
    if resolved is None:
        raise AuthError("Sesi tidak valid atau telah berakhir.", status=401)
    _sess, user = resolved
    return user


def get_current_admin(
    user: AppUser = Depends(get_current_user),
) -> AppUser:
    if user.role != "ADMIN":
        raise AuthError("Forbidden: khusus ADMIN.", status=403)
    return user


RoleName = Literal["ADMIN", "VIEWER"]
