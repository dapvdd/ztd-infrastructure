"""
hubbrain_adapter.py — HubBrain V5 secure configuration adapter

Responsibilities:
- Validate hub configuration dictionary
- Write a chmod-600 .env file for HubBrain process
- Render a systemd drop-in that loads the .env
- Explicitly block automated HubGate credential issuance (not supported by the
  Monitoring team's /api/hubs/pair endpoint, which only registers a hub and
  returns 202 Pending — it does NOT issue HUB_ID/HUB_KEY to ZTD)

HUB_ID and HUB_KEY must be manually provisioned by a Monitoring VPS admin and
injected into the deployment environment. This module enforces that constraint.
"""

from __future__ import annotations

import os
import stat
from typing import Any


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

REQUIRED_KEYS = frozenset(
    {"hub_id", "hub_key", "server_url", "mqtt_host", "mqtt_port", "mqtt_user", "mqtt_pass"}
)


def validate_hub_config(config: dict[str, Any]) -> None:
    """Validate hub configuration dict. Raises ValueError on invalid fields.

    Rules:
    - All required keys present and non-empty (except mqtt_port which is int)
    - hub_id and hub_key must be non-empty strings
    - server_url must start with https://
    - mqtt_port must be 1–65535
    """
    missing = REQUIRED_KEYS - config.keys()
    if missing:
        raise ValueError(f"Missing required hub config keys: {missing}")

    if not str(config.get("hub_id", "")).strip():
        raise ValueError("hub_id must not be empty")

    if not str(config.get("hub_key", "")).strip():
        raise ValueError("hub_key must not be empty")

    server_url = str(config.get("server_url", ""))
    if not server_url.startswith("https://"):
        raise ValueError(f"server_url must start with https://; got: {server_url!r}")

    mqtt_port = config.get("mqtt_port")
    if not isinstance(mqtt_port, int) or not (1 <= mqtt_port <= 65535):
        raise ValueError(f"mqtt_port must be an integer 1–65535; got: {mqtt_port!r}")


# ---------------------------------------------------------------------------
# .env rendering helper
# ---------------------------------------------------------------------------


def _env_quote(value: str) -> str:
    """Double-quote env value if it contains shell special characters."""
    needs_quoting = any(ch in value for ch in (' ', '\t', '"', "'", '\\', '$', '`', '!', '&', '|', ';'))
    if needs_quoting:
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return value


# ---------------------------------------------------------------------------
# .env file writer
# ---------------------------------------------------------------------------


def write_hubbrain_env(config: dict[str, Any], path: str) -> None:
    """Write a HubBrain-compatible .env to *path* with 0600 permissions.

    Raises ValueError if config is invalid.
    Raises KeyError if a required key is missing.
    """
    validate_hub_config(config)

    lines = [
        "# ZTD-generated HubBrain .env — do not edit manually",
        f"HUB_ID={_env_quote(str(config['hub_id']))}",
        f"HUB_KEY={_env_quote(str(config['hub_key']))}",
        f"SERVER_URL={_env_quote(str(config['server_url']))}",
        f"MQTT_HOST={_env_quote(str(config['mqtt_host']))}",
        f"MQTT_PORT={config['mqtt_port']}",
        f"MQTT_USER={_env_quote(str(config['mqtt_user']))}",
        f"MQTT_PASS={_env_quote(str(config['mqtt_pass']))}",
    ]
    content = "\n".join(lines) + "\n"

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    if os.name != "nt":
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# systemd drop-in renderer
# ---------------------------------------------------------------------------


def render_systemd_dropin(env_path: str) -> str:
    """Render a systemd .conf drop-in that loads HubBrain .env.

    Usage: write to /etc/systemd/system/hubbrain.service.d/ztd.conf
    """
    return (
        "# ZTD-generated systemd drop-in — do not edit manually\n"
        "[Service]\n"
        f"EnvironmentFile={env_path}\n"
    )


# ---------------------------------------------------------------------------
# Auto-issuance blocker
# ---------------------------------------------------------------------------


def issue_hubgate_credentials(provisioning_url: str, device_id: str) -> None:
    """Automated HubGate credential issuance is NOT supported.

    The Monitoring team's POST /api/hubs/pair endpoint registers a hub with
    a bootstrap key and returns 202 Pending. It does NOT issue HUB_ID/HUB_KEY
    to the ZTD system. Manual provisioning is required.

    A Monitoring VPS admin must:
    1. Register the hub via the Monitoring admin panel
    2. Retrieve HUB_ID and HUB_KEY
    3. Inject them into the Pi's environment (e.g. via /etc/ztd/agent.env)

    This function exists as a documented dead-end to prevent future callers
    from accidentally invoking a non-existent automatic flow.
    """
    raise NotImplementedError(
        "HubGate credential issuance is not supported by the ZTD system. "
        "HUB_ID and HUB_KEY must be manually provisioned by a Monitoring VPS admin. "
        "See docs/ESP_NODE_PROVISIONING.md and docs/SPRINT3-REPORT.md for details."
    )
