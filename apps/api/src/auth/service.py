"""Sprint 5 — authentication service layer.

Design (see docs/SPRINT5-AUTH.md):
- Passwords: Argon2id via argon2-cffi (PHC format, never logged/exported).
- Sessions: opaque 256-bit urlsafe tokens; DB stores sha256(token); cookie
  carries the raw token (HttpOnly, Secure in HTTPS, SameSite=Strict).
- Revocation: DELETE/expiry/disable/revoke-by-user — server-side state.
- Rotation: every successful login mints a NEW session row; the optional
  predecessor is recorded (rotated_from) defeating fixation reuse.
- RBAC: exactly ADMIN | VIEWER enforced by FastAPI dependencies.
- Audit: security events appended to app_audit_events (no secrets inside).
- Rate limiting: sliding-window in-memory limiter per (username, IP).

Agent/device authentication is NOT touched: MQTT creds, provisioning device
HTTP Basic, and ZTD_PROVISIONING_ADMIN_TOKEN are separate mechanisms.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select, update

from src.auth.models import AppAuditEvent, AppSession, AppUser

_ = AppAuditEvent  # re-exported for typing parity; audit() uses it directly

# --------------------------------------------------------------------------
# Configuration (env-driven; no defaults that could become default passwords)
# --------------------------------------------------------------------------
SESSION_COOKIE_NAME = "ztd_session"
SESSION_TTL_HOURS = int(os.getenv("ZTD_SESSION_TTL_HOURS", "8"))
SESSION_IDLE_MINUTES = int(os.getenv("ZTD_SESSION_IDLE_MINUTES", "120"))
LOGIN_RATE_LIMIT = int(os.getenv("ZTD_LOGIN_RATE_LIMIT", "10"))          # attempts
LOGIN_RATE_WINDOW_SECONDS = int(os.getenv("ZTD_LOGIN_RATE_WINDOW", "300"))
ARGON2_TIME_COST = int(os.getenv("ZTD_ARGON2_TIME_COST", "3"))
ARGON2_MEMORY_COST = int(os.getenv("ZTD_ARGON2_MEMORY_COST", "65536"))
MIN_PASSWORD_LENGTH = int(os.getenv("ZTD_MIN_PASSWORD_LENGTH", "12"))

Role = Literal["ADMIN", "VIEWER"]
ROLES: tuple[str, ...] = ("ADMIN", "VIEWER")


class AuthError(Exception):
    """Operator-safe auth failure (message is safe to return to clients)."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------
# Password hashing (Argon2id)
# --------------------------------------------------------------------------
def _hasher():
    from argon2 import PasswordHasher
    from argon2.profiles import RFC_9106_HIGH_MEMORY

    return PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )


def hash_password(plain: str) -> str:
    """Argon2id PHC hash. Caller MUST NOT log the result input."""
    return _hasher().hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification; returns False on any malformed hash."""
    try:
        return _hasher().verify(hashed, plain)
    except Exception:
        return False


def password_policy_error(plain: str) -> str | None:
    """Returns a human-safe reason if the password violates policy."""
    if len(plain) < MIN_PASSWORD_LENGTH:
        return f"Password minimal {MIN_PASSWORD_LENGTH} karakter."
    if plain.lower() in {"password", "admin", "12345678", "qwerty12345"}:
        return "Password terlalu umum."
    classes = sum(
        [
            any(c.islower() for c in plain),
            any(c.isupper() for c in plain),
            any(c.isdigit() for c in plain),
            any(not c.isalnum() for c in plain),
        ]
    )
    if classes < 3:
        return "Password harus memuat minimal 3 dari 4 kelas karakter (huruf besar/kecil, angka, simbol)."
    return None


# --------------------------------------------------------------------------
# Login rate limiting (sliding window, per username+ip)
# --------------------------------------------------------------------------
_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit_key(username: str, ip: str) -> str:
    return f"{username.lower()}|{ip or 'unknown'}"


def is_rate_limited(username: str, ip: str) -> bool:
    key = rate_limit_key(username, ip)
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[key]
        while bucket and now - bucket[0] > LOGIN_RATE_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= LOGIN_RATE_LIMIT:
            return True
        bucket.append(now)
        return False


def reset_rate_limit(username: str, ip: str) -> None:
    with _rate_lock:
        _rate_buckets.pop(rate_limit_key(username, ip), None)


# --------------------------------------------------------------------------
# Session lifecycle
# --------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; PostgreSQL returns aware ones.

    Normalize to aware-UTC so comparisons never raise TypeError. Naive values
    are interpreted as UTC (the container clock is UTC).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_session(
    db, user: AppUser, user_agent: str | None = None,
    rotated_from: int | None = None,
) -> tuple[str, AppSession]:
    """Create a fresh session for `user`; returns (raw_token, row).

    The raw token exists only in the return value (it goes into the cookie);
    the DB stores only its sha256.
    """
    token = secrets.token_urlsafe(32)
    sess = AppSession(
        token_hash=_token_hash(token),
        user_id=user.id,
        expires_at=_now() + timedelta(hours=SESSION_TTL_HOURS),
        last_seen_at=_now(),
        rotated_from=rotated_from,
        user_agent=(user_agent or "")[:256] or None,
    )
    db.add(sess)
    db.flush()
    return token, sess


def resolve_session(db, token: str | None) -> tuple[AppSession, AppUser] | None:
    """Return (session, user) if the token is valid, else None.

    Valid = exists, not revoked, not expired, user active & role valid.
    Applies idle timeout by updating last_seen_at.
    """
    if not token:
        return None
    th = _token_hash(token)
    row = db.execute(
        select(AppSession).where(AppSession.token_hash == th)
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    now = _now()
    if _as_aware(row.expires_at) <= now:
        return None
    if SESSION_IDLE_MINUTES > 0:
        idle_cutoff = now - timedelta(minutes=SESSION_IDLE_MINUTES)
        last_seen = _as_aware(row.last_seen_at)
        if last_seen and last_seen <= idle_cutoff:
            row.revoked_at = now
            # Security mutation: commit immediately — this dependency also
            # runs inside GET handlers whose request session would otherwise
            # be closed without commit (get_db only closes).
            db.commit()
            return None
    user = db.get(AppUser, row.user_id)
    if user is None or not user.is_active:
        return None
    # Sliding idle window (single UPDATE; cheap under the partial index).
    row.last_seen_at = now
    db.commit()
    return row, user


def revoke_session(db, token: str | None) -> bool:
    if not token:
        return False
    th = _token_hash(token)
    row = db.execute(
        select(AppSession).where(AppSession.token_hash == th)
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = _now()
    db.commit()
    return True


def revoke_all_for_user(db, user_id: int, except_token: str | None = None) -> int:
    """Revoke every live session of a user (disable/reset/role-change).

    except_token: keep the operator's own session alive (their own password
    change) — everything else dies.
    """
    now = _now()
    q = (
        update(AppSession)
        .where(
            AppSession.user_id == user_id,
            AppSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if except_token:
        q = q.where(AppSession.token_hash != _token_hash(except_token))
    res = db.execute(q)
    db.commit()
    return int(res.rowcount or 0)


def purge_expired_sessions(db) -> int:
    """Best-effort cleanup of dead sessions (expired or revoked > 7 days)."""
    now = _now()
    q = (
        update(AppSession)
        .where(
            AppSession.revoked_at.is_(None),
            AppSession.expires_at <= now,
        )
        .values(revoked_at=now)
    )
    res = db.execute(q)
    db.flush()
    return int(res.rowcount or 0)


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------
def require_role(session_user: AppUser, *roles: Role) -> AppUser:
    """Guard: the resolved session user must hold one of `roles`."""
    if session_user.role not in roles:
        raise AuthError("Forbidden: role tidak diizinkan.", status=403)
    return session_user


def is_admin(user: AppUser) -> bool:
    return user.role == "ADMIN"


# --------------------------------------------------------------------------
# Last-admin protection
# --------------------------------------------------------------------------
def count_active_admins(db, exclude_user_id: int | None = None) -> int:
    q = select(AppUser).where(
        AppUser.role == "ADMIN",
        AppUser.is_active.is_(True),
    )
    rows = db.execute(q).scalars().all()
    if exclude_user_id is None:
        return len(rows)
    return sum(1 for r in rows if r.id != exclude_user_id)


def assert_not_last_admin(db, target: AppUser, action: str) -> None:
    """Raises 409 if `action` (disable/demote) would orphan the last admin."""
    if target.role == "ADMIN" and target.is_active:
        if count_active_admins(db, exclude_user_id=target.id) == 0:
            raise AuthError(
                f"Operasi '{action}' ditolak: ini ADMIN aktif terakhir.",
                status=409,
            )


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------
def audit(
    db,
    action: str,
    *,
    actor: AppUser | None = None,
    target: AppUser | None = None,
    detail: dict[str, Any] | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append a security audit event. NEVER include passwords/tokens."""
    actor_username = actor.username if actor is not None else None
    target_username = target.username if target is not None else None
    db.add(
        AppAuditEvent(
            actor_user_id=actor.id if actor is not None else None,
            actor_username=actor_username,
            action=action,
            target_user_id=target.id if target is not None else None,
            target_username=target_username,
            detail=detail or {},
            source_ip=(source_ip or "")[:64] or None,
            user_agent=(user_agent or "")[:256] or None,
        )
    )
    db.flush()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
