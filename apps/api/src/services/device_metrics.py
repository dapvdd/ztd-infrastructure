"""Device metrics contract v1 and validation helpers.

Wire contract (MQTT):
  topic: iot/device/<device_id>/metrics
  qos: 1
  payload:
    {
      "schema_version": 1,
      "kind": "device_metrics",
      "device_id": "raspi-fedae9",
      "measured_at": "2026-10-21T11:40:00+00:00",
      "network": {
        "local_ip": "10.0.0.5" | null,
        "tailscale_ip": "100.64.0.5" | null,
        "public_ip": null,
        "public_ip_status": "not_configured"
      },
      "cpu": {
        "utilization_percent": 12.3 | null,
        "utilization_window_seconds": 60 | null,
        "load_average_1m": 0.42 | null,
        "load_average_5m": 0.31 | null,
        "load_average_15m": 0.28 | null
      },
      "uptime_seconds": 123456 | null,
      "cpu_temperature": {"value": 43.82 | null, "unit": "C" | "F" | null, "source": "thermal_zone0"},
      "unavailable": {"network.public_ip": "not_configured"}
    }

The backend stores the normalized payload in the existing ``telemetry.payload``
JSONB column. No schema migration is required. Metrics rows are marked with
``kind=device_metrics`` and are excluded from the temperature chart endpoint.

This module is deliberately dependency-free so it can be unit-tested without a
database or MQTT broker.
"""

from __future__ import annotations

import ipaddress
import math
from datetime import datetime, timezone
from typing import Any, Optional

METRICS_SCHEMA_VERSION = 1
METRICS_KIND = "device_metrics"
DEFAULT_STALE_AFTER_SECONDS = 180
VALID_TEMPERATURE_UNITS = {"C", "F"}

_NETWORK_FIELDS = (
    "network.local_ip",
    "network.tailscale_ip",
    "network.public_ip",
)
_CPU_FIELDS = (
    "cpu.utilization_percent",
    "cpu.load_average_1m",
    "cpu.load_average_5m",
    "cpu.load_average_15m",
)
_KNOWN_REASONS = set(_NETWORK_FIELDS) | set(_CPU_FIELDS) | {
    "uptime_seconds",
    "cpu_temperature.value",
    "cpu_temperature.unit",
}


def _clean_reason(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = " ".join(value.strip().split())[:120]
    return token or None


def _input_reasons(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("unavailable")
    if not isinstance(raw, dict):
        return {}
    reasons: dict[str, str] = {}
    for key, value in raw.items():
        if key not in _KNOWN_REASONS:
            continue
        reason = _clean_reason(value)
        if reason:
            reasons[key] = reason
    return reasons


def _reason(reasons: dict[str, str], key: str, default: str = "not_reported") -> str:
    return reasons.get(key) or default


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _nonnegative_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value) if value >= 0 else None
    return None


def _positive_int(value: Any) -> Optional[int]:
    number = _nonnegative_int(value)
    return number if number and number > 0 else None


def _ip(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _text(value: Any, max_length: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = " ".join(value.strip().split())
    return token[:max_length] if token else None


def normalize_temperature_unit(value: Any) -> Optional[str]:
    """Return ``C``/``F`` only when the payload explicitly names the unit."""
    if not isinstance(value, str):
        return None
    token = value.strip().upper().replace("°", "").replace("DEGREES", "").replace("DEGREE", "").strip()
    return {"C": "C", "CELSIUS": "C", "F": "F", "FAHRENHEIT": "F"}.get(token)


def parse_measured_at(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp that must include a timezone."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _normalize_network(payload: dict[str, Any], reasons: dict[str, str]) -> dict[str, Any]:
    raw = payload.get("network")
    if not isinstance(raw, dict):
        raw = {}
        reasons.setdefault("network.local_ip", "invalid_network")
        reasons.setdefault("network.tailscale_ip", "invalid_network")
        reasons.setdefault("network.public_ip", "invalid_network")

    network: dict[str, Any] = {}
    for key, source_key in (
        ("local_ip", "network.local_ip"),
        ("tailscale_ip", "network.tailscale_ip"),
        ("public_ip", "network.public_ip"),
    ):
        source = raw.get(key)
        if source is None:
            network[key] = None
            reasons[source_key] = _reason(reasons, source_key)
            continue
        parsed = _ip(source)
        if parsed is None:
            network[key] = None
            reasons[source_key] = "invalid_ip"
        else:
            network[key] = parsed

    status = _text(raw.get("public_ip_status"), 40)
    network["public_ip_status"] = status
    if network["public_ip"] is None:
        current_reason = reasons.get("network.public_ip")
        if (current_reason in (None, "not_reported")
                and status
                and status != "reported"):
            reasons["network.public_ip"] = status
        else:
            reasons["network.public_ip"] = _reason(reasons, "network.public_ip")
    return network


def _normalize_cpu(payload: dict[str, Any], reasons: dict[str, str]) -> dict[str, Any]:
    raw = payload.get("cpu")
    if not isinstance(raw, dict):
        raw = {}
        reasons.setdefault("cpu.utilization_percent", "invalid_cpu")
        reasons.setdefault("cpu.load_average_1m", "invalid_cpu")
        reasons.setdefault("cpu.load_average_5m", "invalid_cpu")
        reasons.setdefault("cpu.load_average_15m", "invalid_cpu")

    utilization = _number(raw.get("utilization_percent"))
    if utilization is None:
        reasons["cpu.utilization_percent"] = (
            "out_of_range" if raw.get("utilization_percent") is not None else _reason(reasons, "cpu.utilization_percent")
        )
    elif not 0 <= utilization <= 100:
        reasons["cpu.utilization_percent"] = "out_of_range"
        utilization = None

    cpu: dict[str, Any] = {
        "utilization_percent": utilization,
        "utilization_window_seconds": _positive_int(raw.get("utilization_window_seconds")),
    }

    for key, source_key in (
        ("load_average_1m", "cpu.load_average_1m"),
        ("load_average_5m", "cpu.load_average_5m"),
        ("load_average_15m", "cpu.load_average_15m"),
    ):
        load = _number(raw.get(key))
        if load is None:
            cpu[key] = None
            reasons[source_key] = (
                "out_of_range" if raw.get(key) is not None else _reason(reasons, source_key)
            )
        elif load < 0:
            cpu[key] = None
            reasons[source_key] = "out_of_range"
        else:
            cpu[key] = load
    return cpu


def _normalize_temperature(payload: dict[str, Any], reasons: dict[str, str]) -> dict[str, Any]:
    raw = payload.get("cpu_temperature")
    if not isinstance(raw, dict):
        raw = {}
        reasons.setdefault("cpu_temperature.value", "invalid_temperature")
        reasons.setdefault("cpu_temperature.unit", "invalid_temperature")

    unit = normalize_temperature_unit(raw.get("unit"))
    value = _number(raw.get("value"))

    if value is None:
        reasons["cpu_temperature.value"] = (
            "out_of_range" if raw.get("value") is not None else _reason(reasons, "cpu_temperature.value")
        )
    elif not -100 <= value <= 200:
        value = None
        reasons["cpu_temperature.value"] = "out_of_range"

    if unit is None:
        reasons["cpu_temperature.unit"] = (
            "unsupported_unit" if raw.get("unit") is not None else _reason(reasons, "cpu_temperature.unit", "missing_unit")
        )
        if value is not None:
            # A number without a unit must never be presented as degrees.
            value = None
            reasons["cpu_temperature.value"] = "missing_unit"
    else:
        reasons.pop("cpu_temperature.unit", None)

    return {
        "value": value,
        "unit": unit,
        "source": _text(raw.get("source"), 64),
    }


def normalize_metrics_payload(
    payload: Any,
    expected_device_id: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], list[str]]:
    """Validate and normalize one v1 metrics payload.

    Returns ``(normalized, errors)``. A non-empty error list means the message
    must not be stored: it has the wrong contract version, device, or timestamp.
    Optional metric fields may be missing/null and are retained with a reason.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return None, ["payload_not_object"]

    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != METRICS_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if payload.get("kind") not in (None, METRICS_KIND):
        errors.append("invalid_kind")

    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        errors.append("missing_device_id")
    elif expected_device_id is not None and device_id.strip() != expected_device_id:
        errors.append("device_id_mismatch")

    measured = parse_measured_at(payload.get("measured_at"))
    if measured is None:
        errors.append("invalid_measured_at")

    if errors:
        return None, errors

    reasons = _input_reasons(payload)
    network = _normalize_network(payload, reasons)
    cpu = _normalize_cpu(payload, reasons)
    uptime = _nonnegative_int(payload.get("uptime_seconds"))
    if uptime is None:
        reasons["uptime_seconds"] = (
            "invalid_uptime" if payload.get("uptime_seconds") is not None else _reason(reasons, "uptime_seconds")
        )
    temperature = _normalize_temperature(payload, reasons)

    normalized = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "kind": METRICS_KIND,
        "device_id": device_id.strip(),
        "measured_at": measured.isoformat(),
        "network": network,
        "cpu": cpu,
        "uptime_seconds": uptime,
        "cpu_temperature": temperature,
        "unavailable": reasons,
    }
    return normalized, []


def temperature_metadata(payload: Any) -> dict[str, Any]:
    """Extract additive metadata from a legacy or v2 temperature payload."""
    raw = payload if isinstance(payload, dict) else {}
    unit = normalize_temperature_unit(raw.get("temperature_unit"))
    schema_version = raw.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        schema_version = None
    return {
        "unit": unit,
        "unit_source": "reported" if unit else "legacy_unlabeled",
        "schema_version": schema_version,
        "room_id": _text(raw.get("room_id"), 50),
        "error": _text(raw.get("error"), 160),
    }


def _empty_response(device_id: str, stale_after_seconds: int, reason: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "available": False,
        "schema_version": None,
        "measured_at": None,
        "recorded_at": None,
        "age_seconds": None,
        "stale_after_seconds": stale_after_seconds,
        "stale": True,
        "stale_reason": reason,
        "network": {
            "local_ip": None,
            "tailscale_ip": None,
            "public_ip": None,
            "public_ip_status": None,
        },
        "cpu": {
            "utilization_percent": None,
            "utilization_window_seconds": None,
            "load_average_1m": None,
            "load_average_5m": None,
            "load_average_15m": None,
        },
        "uptime_seconds": None,
        "cpu_temperature": {"value": None, "unit": None, "source": None},
        "unavailable": {"metrics": reason},
    }


def build_metrics_response(
    row: Any,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    """Build the API representation from the latest stored metrics row."""
    device_id = getattr(row, "device_id", "") if row is not None else ""
    try:
        stale_after = int(stale_after_seconds)
    except (TypeError, ValueError):
        stale_after = DEFAULT_STALE_AFTER_SECONDS
    if stale_after <= 0:
        stale_after = DEFAULT_STALE_AFTER_SECONDS

    if row is None:
        return _empty_response(device_id, stale_after, "never_reported")

    normalized, errors = normalize_metrics_payload(
        getattr(row, "payload", None),
        expected_device_id=device_id or None,
    )
    if normalized is None:
        response = _empty_response(device_id, stale_after, "invalid_payload")
        response["errors"] = errors
        return response

    measured = parse_measured_at(normalized["measured_at"])
    if measured is None:
        response = _empty_response(device_id, stale_after, "invalid_payload")
        response["errors"] = ["invalid_measured_at"]
        return response

    age = (now - measured).total_seconds()
    future_skew = age < -60
    age = max(0.0, age)
    stale = future_skew or age > stale_after
    stale_reason = "future_timestamp" if future_skew else (
        "age_exceeds_threshold" if stale else None
    )

    recorded_at = getattr(row, "recorded_at", None)
    response = {
        "device_id": normalized["device_id"],
        "available": True,
        "schema_version": normalized["schema_version"],
        "measured_at": normalized["measured_at"],
        "recorded_at": recorded_at.isoformat() if recorded_at is not None else None,
        "age_seconds": round(age, 1),
        "stale_after_seconds": stale_after,
        "stale": stale,
        "stale_reason": stale_reason,
        "network": normalized["network"],
        "cpu": normalized["cpu"],
        "uptime_seconds": normalized["uptime_seconds"],
        "cpu_temperature": normalized["cpu_temperature"],
        "unavailable": normalized["unavailable"],
    }
    return response
