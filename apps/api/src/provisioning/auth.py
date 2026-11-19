"""Independent admin, Monitoring service and per-device authentication."""

import hashlib
import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from src.database import get_db
from src.provisioning.models import RegisteredDevice

basic = HTTPBasic(auto_error=False)
bearer = HTTPBearer(auto_error=False)


def token_guard(value: HTTPAuthorizationCredentials | None, variable: str) -> None:
    """Fail closed if no service credential is configured."""
    if value is None:
        raise HTTPException(401, "Authentication required")
    expected = os.environ.get(variable, "")
    if len(expected) < MIN_CREDENTIAL_ENTROPY_BITS // 4:
        raise HTTPException(503, "Authentication service not configured")
    if not secrets.compare_digest(value.credentials.encode(), expected.encode()):
        raise HTTPException(401, "Invalid credentials")


# Minimum accepted entropy for server-issued and operator-supplied credentials,
# expressed in bits. 128 bits = 32 hex/base64ish chars (4 bits per char in the
# common hex issuance format). This is a documented floor, not a strength
# meter: it bounds the shortest secret token_guard will accept.
#
# Credential hashing assumption (F-14) — reviewed, no behavior change:
# credential_hash() is plain SHA-256 over a server-GENERATED 256-bit password
# (secrets.token_urlsafe(32)). Because the input is high-entropy random and
# never a human-chosen password, unsalted fast SHA-256 is acceptable here:
# dictionary/parallel attacks gain nothing against 256 bits of randomness, and
# a slow KDF (bcrypt/argon2) would add cost without added assurance. If this
# function is ever extended to hash HUMAN passwords, it MUST switch to a
# memory-hard KDF with per-credential salt. The plain digest also enables the
# constant-time comparison in device_identity().
MIN_CREDENTIAL_ENTROPY_BITS = 128


def admin(value: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    token_guard(value, "ZTD_PROVISIONING_ADMIN_TOKEN")


def monitoring(value: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    token_guard(value, "ZTD_MONITORING_TOKEN")


def credential_hash(password: str) -> str:
    """Hash server-generated 256-bit credentials, never human passwords."""
    return hashlib.sha256(password.encode()).hexdigest()


def device_identity(
    credentials: HTTPBasicCredentials | None = Depends(basic),
    db: Session = Depends(get_db),
) -> RegisteredDevice:
    if credentials is None:
        raise HTTPException(
            401, "Device authentication required", headers={"WWW-Authenticate": "Basic"}
        )
    device = db.get(RegisteredDevice, credentials.username)
    digest = credential_hash(credentials.password)
    if device is None or not secrets.compare_digest(device.credential_hash, digest):
        raise HTTPException(
            401, "Invalid device credentials", headers={"WWW-Authenticate": "Basic"}
        )
    return device
