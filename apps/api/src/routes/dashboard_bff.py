"""Dashboard BFF session boundary (F-04, F-05).

The provisioning admin token must never reach browser JavaScript. This router
provides a session-based boundary:

- POST /api/dashboard/session     — login against an nginx htpasswd file
- DELETE /api/dashboard/session   — logout (clears cookie)
- GET  /api/dashboard/session     — session introspection
- ANY  /api/dashboard/v2/provisioning/{path} — authenticated proxy into the
  provisioning v2 API with the admin bearer injected server-side.

Fail-closed design:
- No/short ZTD_DASHBOARD_SESSION_SECRET  -> 503 on all endpoints.
- Missing/unreadable ZTD_DASHBOARD_HTPASSWD -> 503 on login.
- No valid session cookie -> 401 on all proxied endpoints.

Cookies are HMAC-signed (itsdangerous), HttpOnly, SameSite=Strict, and Secure
when ZTD_COOKIE_SECURE=1. There is deliberately no persistent server-side
session store: the signed cookie is the session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets as _secrets
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.routes.bootstrap import BootstrapRequest, build_script

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard BFF"])

COOKIE_NAME = "ztd_session"
SESSION_TTL_SECONDS = 8 * 3600
MIN_SECRET_LEN = 32

_rate_limit_history: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX_REQUESTS = 10


def _check_rate_limit(key: str) -> None:
    now = time.time()
    history = _rate_limit_history.setdefault(key, [])
    # Prune old entries
    cutoff = now - RATE_LIMIT_WINDOW
    _rate_limit_history[key] = [t for t in history if t > cutoff]
    if len(_rate_limit_history[key]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(429, "Too many requests; please wait before retrying")
    _rate_limit_history[key].append(now)


def _check_csrf(request: Request) -> None:
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site and sec_fetch_site.strip().lower() == "cross-site":
        raise HTTPException(403, "Cross-site request forbidden")
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host:
        from urllib.parse import urlsplit
        parsed_origin = urlsplit(origin)
        origin_host = parsed_origin.netloc or parsed_origin.path
        # Normalize by removing default port if matches
        if origin_host.lower() != host.lower():
            raise HTTPException(403, "Cross-origin request forbidden")


def _check_payload_size(request: Request, max_bytes: int = 16384) -> None:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(413, "Request payload too large")
        except ValueError:
            raise HTTPException(400, "Invalid Content-Length header")


class LoginInput(BaseModel):
    username: str
    password: str


# ---------------------------------------------------------------------------
# Environment access (fail-closed)
# ---------------------------------------------------------------------------


def _secret() -> str:
    secret = os.environ.get("ZTD_DASHBOARD_SESSION_SECRET", "")
    if len(secret) < MIN_SECRET_LEN:
        raise HTTPException(503, "Dashboard session service not configured")
    return secret


def _htpasswd_path() -> str:
    path = os.environ.get("ZTD_DASHBOARD_HTPASSWD", "")
    if not path or not os.path.isfile(path):
        raise HTTPException(503, "Dashboard authentication service not configured")
    return path


def _admin_token() -> str:
    token = os.environ.get("ZTD_PROVISIONING_ADMIN_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Provisioning admin service not configured")
    return token


# ---------------------------------------------------------------------------
# htpasswd verification (apr1 / MD5-crypt and salted SHA1 supported)
# ---------------------------------------------------------------------------


def _apr1_verify(password: str, hash_part: str) -> bool:
    """Pure-Python apr1 (Apache MD5-crypt) verification.

    Faithful transliteration of the canonical apr_md5 algorithm (verified
    byte-for-byte against `openssl passwd -apr1`), including the byte-level
    quirks of the original C implementation.
    """
    magic = "$apr1$"
    if not hash_part.startswith(magic):
        return False
    rest = hash_part[len(magic):]
    salt, _, expected = rest.partition("$")
    if not salt or not expected:
        return False

    to64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

    def t64(value: int, n: int) -> str:
        out = ""
        for _ in range(n):
            out += to64[value & 0x3F]
            value >>= 6
        return out

    pw = password.encode()
    salt_b = salt.encode()[:8]
    magic_b = magic.encode()

    # Digest B
    final = hashlib.md5(pw + salt_b + pw).digest()

    # Context: pw + magic + salt, then digest B chopped to pw length,
    # then the 'weird' single-byte transform.
    ctx = bytearray(pw + magic_b + salt_b)
    for pl in range(len(pw), 0, -16):
        ctx += final[:16] if pl > 16 else final[:pl]
    i = len(pw)
    while i:
        ctx += b"\x00" if i & 1 else pw[:1]
        i >>= 1
    final = hashlib.md5(bytes(ctx)).digest()

    # 1000 rounds of alternating concatenation.
    for i in range(1000):
        c = bytearray()
        c += pw if i & 1 else final
        if i % 3:
            c += salt_b
        if i % 7:
            c += pw
        c += final if i & 1 else pw
        final = hashlib.md5(bytes(c)).digest()

    encoded = (
        t64((final[0] << 16) | (final[6] << 8) | final[12], 4)
        + t64((final[1] << 16) | (final[7] << 8) | final[13], 4)
        + t64((final[2] << 16) | (final[8] << 8) | final[14], 4)
        + t64((final[3] << 16) | (final[9] << 8) | final[15], 4)
        + t64((final[4] << 16) | (final[10] << 8) | final[5], 4)
        + t64(final[11], 2)
    )
    return hmac.compare_digest(encoded, expected)


def _verify_htpasswd(password: str, entry: str) -> bool:
    entry = entry.strip()
    if entry.startswith("$apr1$"):
        return _apr1_verify(password, entry)
    if entry.startswith("{SHA}"):
        digest = base64.b64encode(
            hashlib.sha1(password.encode()).digest()
        ).decode()
        return hmac.compare_digest(entry[5:], digest)
    # Unknown format (e.g. bcrypt from htpasswd -B): fail closed rather than
    # attempt a partial implementation.
    return False


def _check_credentials(username: str, password: str) -> bool:
    path = _htpasswd_path()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            user, _, hash_part = line.partition(":")
            if hmac.compare_digest(user, username):
                return _verify_htpasswd(password, hash_part)
    return False


# ---------------------------------------------------------------------------
# Session cookie (itsdangerous-signed, no server-side store)
# ---------------------------------------------------------------------------


def _signer():
    from itsdangerous import URLSafeTimedSerializer

    return URLSafeTimedSerializer(_secret(), salt="ztd-dashboard-session")


def _issue_cookie(response: Response, username: str) -> None:
    token = _signer().dumps({"u": username, "n": _secrets.token_hex(8)})
    secure = os.environ.get("ZTD_COOKIE_SECURE", "") == "1"
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


def _current_user(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Dashboard session required")
    try:
        data = _signer().loads(token, max_age=SESSION_TTL_SECONDS)
    except Exception:
        raise HTTPException(401, "Dashboard session invalid or expired")
    user = data.get("u")
    if not user:
        raise HTTPException(401, "Dashboard session invalid")
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/session")
def login(payload: LoginInput, response: Response) -> dict:
    _secret()  # fail closed
    if not _check_credentials(payload.username, payload.password):
        raise HTTPException(401, "Invalid dashboard credentials")
    _issue_cookie(response, payload.username)
    return {"authenticated": True, "username": payload.username}


@router.get("/session")
def me(request: Request) -> dict:
    return {"authenticated": True, "username": _current_user(request)}


@router.delete("/session", status_code=204)
def logout(response: Response) -> None:
    # Mutate the injected response; returning a new Response here would
    # discard the delete_cookie header.
    response.delete_cookie(COOKIE_NAME, path="/")
    return None


# ---------------------------------------------------------------------------
# Authenticated proxy into provisioning v2
# ---------------------------------------------------------------------------


def _provisioning_request(
    path: str, headers: dict[str, str], method: str = "GET", body: bytes | None = None
) -> tuple[int, Any]:
    """Forward a request to the provisioning API with the admin bearer injected.

    Primary path (tests): in-process ASGI via starlette TestClient -- no
    network, no dependency on a running server.
    Runtime fallback (deployed container): stdlib urllib against the
    container-loopback API, because starlette refuses to import testclient
    without the test-only httpx dependency (staging P4 caught the 500).
    The admin bearer is injected by this function in both paths and never
    echoed to the client. The caller forwards the original request body
    (POST /devices enrollment, PUT assignments) and Content-Type.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    forward_headers = dict(headers)
    if body:
        # Content-Type must travel with the body or FastAPI returns 422.
        forward_headers.setdefault("Content-Type", "application/json")

    # 1) In-process path (test environment): starlette TestClient against this
    #    same app under the real /api/v2/provisioning prefix. No network.
    try:
        from fastapi.testclient import TestClient

        from src.main import app as _app
    except (ImportError, RuntimeError):
        # The runtime image's fastapi/testclient shim raises ImportError at
        # import time; test installs without httpx raise RuntimeError. Both
        # mean "no in-process path" -> fall through to loopback HTTP.
        pass
    else:
        with TestClient(_app, raise_server_exceptions=False) as client:
            resp = client.request(
                method,
                f"/api/v2/provisioning/{path}",
                headers=forward_headers,
                content=body if body else None,
            )
        try:
            resp_body = resp.json()
        except ValueError:
            resp_body = {"detail": resp.text}
        return resp.status_code, resp_body

    # 2) Runtime path: stdlib urllib against the container-loopback API.
    base = os.environ.get("ZTD_INTERNAL_API_URL", "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/api/v2/provisioning/{path}"
    req = Request(url, data=body if body else None, headers=forward_headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read()
    except HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except URLError as exc:
        # Loopback unreachable: surface a clean 502, never a bare 500.
        return 502, {"detail": f"Provisioning upstream unreachable: {exc.reason}"}
    try:
        import json as _json

        body_json = _json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        body_json = {"detail": raw.decode("utf-8", "replace")[:500]}
    return status, body_json


@router.api_route(
    "/v2/provisioning/{path:path}", methods=["GET", "POST", "PUT", "DELETE"]
)
async def proxy(path: str, request: Request) -> Response:
    _current_user(request)  # 401 without valid session
    raw_body = await request.body()
    forward_headers = {"Authorization": f"Bearer {_admin_token()}"}
    content_type = request.headers.get("content-type")
    if content_type:
        forward_headers["Content-Type"] = content_type
    # _provisioning_request blocks (urllib); run_in_threadpool keeps the event
    # loop free -- calling it inline deadlocked the loopback API, which shares
    # this same process/event loop (staging E2E caught the 500).
    status, body = await run_in_threadpool(
        _provisioning_request,
        path,
        forward_headers,
        request.method,
        raw_body if raw_body else None,
    )
    return JSONResponse(status_code=status, content=body)


# ---------------------------------------------------------------------------
# Authenticated bootstrap generation (F-01, Task 2)
# ---------------------------------------------------------------------------


@router.post("/bootstrap/raspberry", response_class=PlainTextResponse)
async def generate_raspberry_bootstrap(request: Request) -> Response:
    user = _current_user(request)
    _check_csrf(request)
    _check_payload_size(request)
    _check_rate_limit(user)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    from pydantic import ValidationError
    try:
        req = BootstrapRequest.model_validate(data)
    except ValidationError as err:
        # Sanitize error detail: never echo submitted input values (which may contain secrets)
        clean_errors = [
            {"type": e.get("type"), "loc": e.get("loc"), "msg": e.get("msg")}
            for e in err.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": clean_errors})

    script = build_script(req)
    return PlainTextResponse(
        content=script,
        media_type="text/x-shellscript; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="bootstrap-raspberry.sh"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )

