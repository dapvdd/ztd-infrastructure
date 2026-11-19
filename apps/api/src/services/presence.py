"""Single source of truth for device presence.

The API and the MQTT listener both use this module. A device is ONLINE when its
last contact (heartbeat/telemetry/register) is at most ``DEVICE_ONLINE_WINDOW_SECONDS``
old; otherwise it is OFFLINE. The value read from the wire is never trusted for
status, and the database ``devices.status`` column is only a compatibility hint.
"""
from datetime import datetime, timedelta, timezone

from src.config import settings

ONLINE_WINDOW_SECONDS = settings.DEVICE_ONLINE_WINDOW_SECONDS

# Do not rewrite the same device row more than once per this window. QoS 1
# duplicates and near-simultaneous heartbeat/telemetry messages are coalesced.
TOUCH_MIN_INTERVAL_SECONDS = 4


def ensure_aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def device_status(last_seen, now=None, window_seconds=None):
    """Return ONLINE / OFFLINE / UNKNOWN from ``last_seen`` only."""
    last_seen = ensure_aware(last_seen)
    if last_seen is None:
        return "UNKNOWN"
    current = now or datetime.now(timezone.utc)
    window = ONLINE_WINDOW_SECONDS if window_seconds is None else window_seconds
    return "ONLINE" if (current - last_seen) <= timedelta(seconds=window) else "OFFLINE"


def touch_device(device, now=None, min_interval_seconds=TOUCH_MIN_INTERVAL_SECONDS):
    """Refresh last_seen/status at most once per ``min_interval_seconds``.

    Returns True when the row was touched, False when the update was coalesced.
    The caller decides when to commit.
    """
    current = now or datetime.now(timezone.utc)
    last = ensure_aware(device.last_seen)
    if last is not None and (current - last) < timedelta(seconds=min_interval_seconds):
        return False
    device.status = "ONLINE"
    device.last_seen = current
    return True
