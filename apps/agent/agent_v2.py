"""
agent_v2.py — ZTD V2 Pi Agent

Authenticated HTTP provisioning client for Raspberry Pi gateways.
Pure-function core (testable without network or filesystem):
  - load_state / save_state
  - backoff_seconds
  - compute_manifest_hash
  - should_fetch_manifest
  - render_hubbrain_env
  - build_registration_payload

Imperative shell (requires network/env):
  - run_agent_loop (entrypoint)

Environment variables consumed at runtime:
  ZTD_DEVICE_ID          — device identity (e.g. raspi-abc123)
  ZTD_DEVICE_PASSWORD    — HTTP Basic password issued at enrollment
  ZTD_PROVISIONING_URL   — Provisioning VPS base URL
  ZTD_AGENT_STATE_FILE   — durable state JSON path (default: /var/lib/ztd/state.json)
  ZTD_MONITORING_HUB_ID  — HubBrain identity (HUB_ID)
  ZTD_MONITORING_URL     — Monitoring VPS base URL
  ZTD_HUBBRAIN_ENV_PATH  — where to write hub/.env (default: /etc/ztd/hubbrain.env)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import stat
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ztd.agent_v2")

# ---------------------------------------------------------------------------
# Default state schema
# ---------------------------------------------------------------------------

DEFAULT_STATE: dict[str, Any] = {
    "device_id": None,
    "revision": 0,
    "approval_status": "PENDING",
    "manifest_hash": None,
    "applied_at": None,
}


# ---------------------------------------------------------------------------
# State file helpers (pure-ish; file I/O only, no network)
# ---------------------------------------------------------------------------


def load_state(path: str) -> dict[str, Any]:
    """Load agent state JSON from *path*. Returns DEFAULT_STATE copy on missing file."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        # Ensure all default keys are present for forward-compat
        return {**DEFAULT_STATE, **data}
    except FileNotFoundError:
        return dict(DEFAULT_STATE)


def save_state(path: str, state: dict[str, Any]) -> None:
    """Write agent state JSON to *path* with restricted permissions (owner-only)."""
    # Write to a temp file, then rename for atomicity
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    # Restrict permissions before moving into place
    if os.name != "nt":
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Retry / backoff (pure)
# ---------------------------------------------------------------------------


def backoff_seconds(
    attempt: int,
    *,
    base: int = 5,
    cap: int = 300,
    jitter: bool = False,
) -> int:
    """Exponential backoff with optional ±50% jitter.

    Returns an integer number of seconds in [base, cap].
    """
    delay = min(base * (2 ** attempt), cap)
    if jitter:
        delay = int(delay * (0.5 + 0.5 * random.random()))
        delay = max(base, delay)
    return delay


# ---------------------------------------------------------------------------
# Manifest helpers (pure)
# ---------------------------------------------------------------------------


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    """SHA-256 hex digest of the JSON-serialised manifest (key-sorted for stability)."""
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def should_fetch_manifest(device_status: dict[str, Any]) -> bool:
    """Return True only when the device is REGISTERED + APPROVED + expiry is in the future."""
    if device_status.get("registration_status") != "REGISTERED":
        return False
    if device_status.get("approval_status") != "APPROVED":
        return False
    expires_raw = device_status.get("approval_expires_at")
    if not expires_raw:
        return False
    try:
        expires = datetime.fromisoformat(expires_raw)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# HubBrain .env rendering (pure)
# ---------------------------------------------------------------------------


def _env_quote(value: str) -> str:
    """Double-quote a value if it contains shell special characters."""
    needs_quoting = any(ch in value for ch in (' ', '\t', '"', "'", '\\', '$', '`', '!', '&', '|', ';'))
    if needs_quoting:
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return value


def render_hubbrain_env(hub_config: dict[str, Any]) -> str:
    """Render a HubBrain-compatible .env file from *hub_config*.

    Required keys: hub_id, hub_key, server_url, mqtt_host, mqtt_port, mqtt_user, mqtt_pass
    """
    lines = [
        "# ZTD-generated HubBrain configuration — do not edit manually",
        f"HUB_ID={_env_quote(str(hub_config['hub_id']))}",
        f"HUB_KEY={_env_quote(str(hub_config['hub_key']))}",
        f"SERVER_URL={_env_quote(str(hub_config['server_url']))}",
        f"MQTT_HOST={_env_quote(str(hub_config['mqtt_host']))}",
        f"MQTT_PORT={hub_config['mqtt_port']}",
        f"MQTT_USER={_env_quote(str(hub_config['mqtt_user']))}",
        f"MQTT_PASS={_env_quote(str(hub_config['mqtt_pass']))}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Registration payload (pure)
# ---------------------------------------------------------------------------


def build_registration_payload(device_id: str) -> dict[str, str]:
    """Build the JSON payload for POST /api/v2/provisioning/register."""
    return {"hostname": device_id}


# ---------------------------------------------------------------------------
# Imperative shell — HTTP provisioning loop
# ---------------------------------------------------------------------------


def _provisioning_base_url() -> str:
    url = os.environ.get("ZTD_PROVISIONING_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("ZTD_PROVISIONING_URL is not set")
    return url


def _device_credentials() -> tuple[str, str]:
    device_id = os.environ.get("ZTD_DEVICE_ID", "")
    password = os.environ.get("ZTD_DEVICE_PASSWORD", "")
    if not device_id or not password:
        raise RuntimeError("ZTD_DEVICE_ID and ZTD_DEVICE_PASSWORD must be set")
    return device_id, password


def run_agent_loop(
    state_path: str | None = None,
    poll_interval: int = 60,
    max_attempts: int = 0,
) -> None:  # pragma: no cover — requires real HTTP + env
    """Main agent loop: register → poll status → fetch manifest → handoff."""
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required for the agent loop; install it") from exc

    state_path = state_path or os.environ.get("ZTD_AGENT_STATE_FILE", "/var/lib/ztd/state.json")
    device_id, password = _device_credentials()
    base_url = _provisioning_base_url()
    auth = (device_id, password)

    # F-12: TLS trust for private VPS addresses. The provisioning/monitoring
    # endpoints commonly use internal CAs or IPs, so the operator points
    # ZTD_TLS_CA_BUNDLE at a CA bundle that includes the issuing CA. The cert
    # presented by the server MUST carry a SAN matching the URL host (an IP
    # SAN for literal IPs). Disabling verification is not supported by design;
    # verification stays ON even without the env var (system trust store).
    ca_bundle = os.environ.get("ZTD_TLS_CA_BUNDLE", "").strip()
    verify: str | bool
    if ca_bundle:
        verify = ca_bundle
        if not os.path.isfile(ca_bundle):
            raise RuntimeError(
                f"ZTD_TLS_CA_BUNDLE points to a missing file: {ca_bundle!r}"
            )
    else:
        verify = True
    # Shared timeout for all calls in the loop.
    timeout = httpx.Timeout(15.0)

    state = load_state(state_path)
    state["device_id"] = device_id
    save_state(state_path, state)

    attempt = 0
    while max_attempts == 0 or attempt < max_attempts:
        try:
            # 1. Register (idempotent — server ignores re-registration)
            resp = httpx.post(
                f"{base_url}/api/v2/provisioning/register",
                json=build_registration_payload(device_id),
                auth=auth,
                timeout=timeout,
                verify=verify,
            )
            if resp.status_code not in (200, 422):  # 422 = already registered
                logger.warning("Register returned %s; will retry", resp.status_code)
                time.sleep(backoff_seconds(attempt, jitter=True))
                attempt += 1
                continue

            # 2. Poll status
            status_resp = httpx.get(
                f"{base_url}/api/v2/provisioning/status",
                auth=auth,
                timeout=timeout,
                verify=verify,
            )
            status_resp.raise_for_status()
            device_status = status_resp.json()
            state["approval_status"] = device_status.get("approval_status", "PENDING")
            save_state(state_path, state)

            # 3. Fetch manifest when approved
            if should_fetch_manifest(device_status):
                manifest_resp = httpx.get(
                    f"{base_url}/api/v2/provisioning/manifest",
                    auth=auth,
                    timeout=timeout,
                    verify=verify,
                )
                if manifest_resp.status_code == 200:
                    manifest = manifest_resp.json()
                    new_hash = compute_manifest_hash(manifest)
                    if new_hash != state.get("manifest_hash"):
                        logger.info("New manifest received (rev %s)", manifest.get("configuration_revision"))
                        # Apply first; persist hash only after a successful apply
                        # so a failed write leaves the previous known-good state.
                        _apply_hubbrain_config(manifest)
                        state["manifest_hash"] = new_hash
                        state["revision"] = manifest.get("configuration_revision", 0)
                        state["applied_at"] = datetime.now(timezone.utc).isoformat()
                        save_state(state_path, state)
                elif manifest_resp.status_code == 403:
                    logger.info("Manifest denied (403); approval may have expired")

            attempt = 0  # reset backoff on success
        except Exception as exc:
            logger.error("Agent loop error: %s", exc)
            attempt += 1

        time.sleep(poll_interval)


def _apply_hubbrain_config(manifest: dict[str, Any]) -> None:  # pragma: no cover
    """Write HubBrain .env from manifest hub_config block, if present.

    Secrets (HUB_KEY, MQTT_PASS) never come from the manifest: they are merged
    from the agent's own environment. The manifest supplies non-secret
    addressing only. The merged configuration is validated before any write.
    """
    import hubbrain_adapter

    hub_config = manifest.get("hub_config")
    if not hub_config:
        return
    merged = dict(hub_config)
    merged["hub_key"] = os.environ.get("ZTD_HUB_KEY", "")
    merged["mqtt_pass"] = os.environ.get("ZTD_MQTT_PASS", "")
    # Fail before writing anything invalid (F-09).
    hubbrain_adapter.validate_hub_config(merged)
    env_path = os.environ.get("ZTD_HUBBRAIN_ENV_PATH", "/etc/ztd/hubbrain.env")
    env_content = render_hubbrain_env(merged)
    tmp = env_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(env_content)
    if os.name != "nt":
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, env_path)
    logger.info("HubBrain .env written to %s", env_path)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    run_agent_loop()
