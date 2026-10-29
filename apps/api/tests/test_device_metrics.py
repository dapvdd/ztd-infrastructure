import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.services.device_metrics import (
    DEFAULT_STALE_AFTER_SECONDS,
    build_metrics_response,
    normalize_metrics_payload,
    parse_measured_at,
    temperature_metadata,
)


def base_payload(**overrides):
    payload = {
        "schema_version": 1,
        "kind": "device_metrics",
        "device_id": "raspi-test",
        "measured_at": "2026-10-21T12:00:00+00:00",
        "network": {
            "local_ip": "10.0.0.5",
            "tailscale_ip": "100.64.0.5",
            "public_ip": None,
            "public_ip_status": "not_configured",
        },
        "cpu": {
            "utilization_percent": 12.5,
            "utilization_window_seconds": 60,
            "load_average_1m": 0.42,
            "load_average_5m": 0.31,
            "load_average_15m": 0.28,
        },
        "uptime_seconds": 123456,
        "cpu_temperature": {"value": 43.82, "unit": "C", "source": "thermal_zone0"},
        "unavailable": {},
    }
    payload.update(overrides)
    return payload


class NormalizeMetricsTests(unittest.TestCase):
    def test_valid_payload_keeps_all_values(self):
        normalized, errors = normalize_metrics_payload(base_payload(), "raspi-test")
        self.assertEqual(errors, [])
        self.assertEqual(normalized["network"]["local_ip"], "10.0.0.5")
        self.assertEqual(normalized["cpu"]["utilization_percent"], 12.5)
        self.assertEqual(normalized["cpu"]["load_average_1m"], 0.42)
        self.assertEqual(normalized["uptime_seconds"], 123456)
        self.assertEqual(normalized["cpu_temperature"]["unit"], "C")
        self.assertEqual(normalized["cpu_temperature"]["value"], 43.82)
        self.assertEqual(normalized["unavailable"]["network.public_ip"], "not_configured")

    def test_missing_and_null_optional_fields_become_null_with_reasons(self):
        payload = base_payload(
            network={"local_ip": None, "tailscale_ip": None, "public_ip": None},
            cpu={},
            uptime_seconds=None,
            cpu_temperature={"value": None, "unit": None},
            unavailable={"network.public_ip": "not_configured"},
        )
        normalized, errors = normalize_metrics_payload(payload, "raspi-test")
        self.assertEqual(errors, [])
        self.assertIsNone(normalized["network"]["local_ip"])
        self.assertIsNone(normalized["cpu"]["utilization_percent"])
        self.assertIsNone(normalized["uptime_seconds"])
        self.assertIsNone(normalized["cpu_temperature"]["value"])
        self.assertEqual(
            normalized["unavailable"]["network.public_ip"], "not_configured"
        )
        self.assertEqual(normalized["unavailable"]["cpu.utilization_percent"], "not_reported")

    def test_invalid_cpu_and_negative_load_are_not_clamped(self):
        payload = base_payload(cpu={
            "utilization_percent": 140,
            "utilization_window_seconds": 60,
            "load_average_1m": -1,
            "load_average_5m": 0.2,
            "load_average_15m": 0.1,
        })
        normalized, errors = normalize_metrics_payload(payload, "raspi-test")
        self.assertEqual(errors, [])
        self.assertIsNone(normalized["cpu"]["utilization_percent"])
        self.assertEqual(normalized["unavailable"]["cpu.utilization_percent"], "out_of_range")
        self.assertIsNone(normalized["cpu"]["load_average_1m"])
        self.assertEqual(normalized["unavailable"]["cpu.load_average_1m"], "out_of_range")
        self.assertEqual(normalized["cpu"]["load_average_5m"], 0.2)

    def test_temperature_without_unit_is_never_presented_as_degrees(self):
        payload = base_payload(cpu_temperature={"value": 43.8, "unit": None})
        normalized, errors = normalize_metrics_payload(payload, "raspi-test")
        self.assertEqual(errors, [])
        self.assertIsNone(normalized["cpu_temperature"]["value"])
        self.assertEqual(normalized["unavailable"]["cpu_temperature.value"], "missing_unit")

    def test_invalid_temperature_unit_is_rejected(self):
        payload = base_payload(cpu_temperature={"value": 43.8, "unit": "kelvin"})
        normalized, errors = normalize_metrics_payload(payload, "raspi-test")
        self.assertEqual(errors, [])
        self.assertIsNone(normalized["cpu_temperature"]["value"])
        self.assertEqual(normalized["unavailable"]["cpu_temperature.unit"], "unsupported_unit")

    def test_out_of_range_temperature_is_rejected(self):
        payload = base_payload(cpu_temperature={"value": 250, "unit": "C"})
        normalized, errors = normalize_metrics_payload(payload, "raspi-test")
        self.assertEqual(errors, [])
        self.assertIsNone(normalized["cpu_temperature"]["value"])
        self.assertEqual(normalized["unavailable"]["cpu_temperature.value"], "out_of_range")

    def test_invalid_ip_is_rejected(self):
        payload = base_payload(network={"local_ip": "not-an-ip", "tailscale_ip": None})
        normalized, errors = normalize_metrics_payload(payload, "raspi-test")
        self.assertEqual(errors, [])
        self.assertIsNone(normalized["network"]["local_ip"])
        self.assertEqual(normalized["unavailable"]["network.local_ip"], "invalid_ip")

    def test_invalid_uptime_types_are_rejected(self):
        for value in (-1, True, "123", 1.5):
            with self.subTest(value=value):
                payload = base_payload(uptime_seconds=value)
                normalized, errors = normalize_metrics_payload(payload, "raspi-test")
                self.assertEqual(errors, [])
                self.assertIsNone(normalized["uptime_seconds"])

    def test_required_contract_fields_are_enforced(self):
        cases = [
            (base_payload(schema_version=2), "unsupported_schema_version"),
            (base_payload(kind="other"), "invalid_kind"),
            (base_payload(device_id="other"), "device_id_mismatch"),
            (base_payload(measured_at=None), "invalid_measured_at"),
            (base_payload(measured_at="2026-10-21T12:00:00"), "invalid_measured_at"),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                normalized, errors = normalize_metrics_payload(payload, "raspi-test")
                self.assertIsNone(normalized)
                self.assertIn(expected, errors)

    def test_parse_measured_at_requires_timezone(self):
        self.assertIsNotNone(parse_measured_at("2026-10-21T12:00:00Z"))
        self.assertIsNone(parse_measured_at("2026-10-21T12:00:00"))
        self.assertIsNone(parse_measured_at("not-a-date"))


class MetricsResponseTests(unittest.TestCase):
    def row(self, payload=None, recorded_at=None):
        return SimpleNamespace(
            device_id="raspi-test",
            payload=payload or base_payload(),
            recorded_at=recorded_at or datetime(2026, 10, 21, 12, 0, 1, tzinfo=timezone.utc),
        )

    def test_fresh_response_contains_freshness_and_values(self):
        now = datetime(2026, 10, 21, 12, 0, 10, tzinfo=timezone.utc)
        response = build_metrics_response(self.row(), now)
        self.assertTrue(response["available"])
        self.assertFalse(response["stale"])
        self.assertEqual(response["age_seconds"], 10.0)
        self.assertEqual(response["cpu_temperature"]["unit"], "C")

    def test_stale_response_is_explicit(self):
        now = datetime(2026, 10, 21, 12, 5, 1, tzinfo=timezone.utc)
        response = build_metrics_response(self.row(), now)
        self.assertTrue(response["stale"])
        self.assertEqual(response["stale_reason"], "age_exceeds_threshold")
        self.assertGreater(response["age_seconds"], DEFAULT_STALE_AFTER_SECONDS)

    def test_future_timestamp_is_not_treated_as_fresh(self):
        payload = base_payload(measured_at="2026-10-21T12:10:00+00:00")
        now = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
        response = build_metrics_response(self.row(payload), now)
        self.assertTrue(response["stale"])
        self.assertEqual(response["stale_reason"], "future_timestamp")

    def test_missing_row_is_unavailable_with_reason(self):
        response = build_metrics_response(None, datetime.now(timezone.utc))
        self.assertFalse(response["available"])
        self.assertTrue(response["stale"])
        self.assertEqual(response["stale_reason"], "never_reported")
        self.assertEqual(response["unavailable"]["metrics"], "never_reported")

    def test_invalid_stored_payload_is_not_rendered(self):
        payload = base_payload(measured_at=None)
        response = build_metrics_response(self.row(payload), datetime.now(timezone.utc))
        self.assertFalse(response["available"])
        self.assertEqual(response["stale_reason"], "invalid_payload")


class TemperatureMetadataTests(unittest.TestCase):
    def test_legacy_payload_has_no_unit(self):
        metadata = temperature_metadata({"temperature": 110.0})
        self.assertIsNone(metadata["unit"])
        self.assertEqual(metadata["unit_source"], "legacy_unlabeled")
        self.assertIsNone(metadata["schema_version"])

    def test_v2_payload_preserves_reported_unit(self):
        metadata = temperature_metadata({
            "schema_version": 2,
            "temperature": 43.8,
            "temperature_unit": "C",
            "room_id": "lab-01",
        })
        self.assertEqual(metadata["unit"], "C")
        self.assertEqual(metadata["unit_source"], "reported")
        self.assertEqual(metadata["schema_version"], 2)
        self.assertEqual(metadata["room_id"], "lab-01")

    def test_fahrenheit_is_labeled_fahrenheit_not_celsius(self):
        metadata = temperature_metadata({"temperature_unit": "F"})
        self.assertEqual(metadata["unit"], "F")


if __name__ == "__main__":
    unittest.main()
