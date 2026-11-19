"""Sprint 5 — Centralized authentication SQLAlchemy models.

Separate DeclarativeBase (matches src/provisioning/models.py pattern so these
tables can be created in tests without touching the legacy metadata).

Tables (see postgres/migrations/004_central_auth.up.sql):
    app_users         — dashboard principals (ADMIN | VIEWER)
    app_sessions      — opaque revocable sessions (sha256 token hashes)
    app_audit_events  — security audit trail
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _pk_int() -> BigInteger:
    """BIGSERIAL on PostgreSQL; plain INTEGER (rowid alias) on SQLite tests."""
    return BigInteger().with_variant(Integer(), "sqlite")


class AuthBase(DeclarativeBase):
    """Dedicated metadata for the central-auth tables."""


class AppUser(AuthBase):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(_pk_int(), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # PHC-format Argon2id hash; never serialized by any API response.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="VIEWER", server_default="VIEWER"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'VIEWER')", name="ck_app_users_role"),
    )

    def public_dict(self) -> dict:
        """Safe projection — never includes the password hash."""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


class AppSession(AuthBase):
    __tablename__ = "app_sessions"

    id: Mapped[int] = mapped_column(_pk_int(), primary_key=True, autoincrement=True)
    # sha256 hex of the opaque bearer token; the raw token lives only in the
    # user's HttpOnly cookie.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_from: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (
        Index(
            "ix_app_sessions_active",
            "token_hash",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class AppAuditEvent(AuthBase):
    __tablename__ = "app_audit_events"

    id: Mapped[int] = mapped_column(_pk_int(), primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_username: Mapped[str | None] = mapped_column(String(64))
    # JSON detail (generic JSON type works on PostgreSQL AND SQLite — the
    # provisioning models already rely on this for their payload columns).
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


# Integer import removed — BigInteger covers all id columns.
