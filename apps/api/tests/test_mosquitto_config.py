"""Static mosquitto configuration assertions (F-07: MQTT authentication).

Parse mosquitto.conf / acl / docker-compose.yml as text and assert:
- anonymous access disabled
- password_file + acl_file wired
- broker ports are NOT published to all host interfaces by default
- healthcheck authenticates instead of relying on anonymous $SYS reads

Container integration (real broker + authenticated publish) is documented as
not-run on this host; see the remediation report.
"""

import os
import re

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MQTT_DIR = os.path.join(REPO, "mosquitto")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(MQTT_DIR), reason="mosquitto config not present in this checkout"
)


def _conf() -> str:
    with open(os.path.join(MQTT_DIR, "mosquitto.conf"), encoding="utf-8") as fh:
        return fh.read()


def _compose() -> str:
    with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as fh:
        return fh.read()


class TestBrokerAuthentication:
    def test_anonymous_access_disabled(self):
        conf = _conf()
        assert re.search(r"(?m)^allow_anonymous\s+false\s*$", conf), (
            "allow_anonymous must be false"
        )

    def test_password_file_configured(self):
        assert re.search(r"(?m)^password_file\s+", _conf())

    def test_acl_file_configured(self):
        assert re.search(r"(?m)^acl_file\s+", _conf())

    def test_acl_file_exists_with_topic_rules(self):
        acl_path = os.path.join(MQTT_DIR, "acl")
        assert os.path.isfile(acl_path), "mosquitto/acl must exist"
        with open(acl_path, encoding="utf-8") as fh:
            acl = fh.read()
        # Backend: full control. Devices: write-only sensor data.
        # Dashboard: read-only telemetry.
        assert re.search(r"(?m)^user\s+[\w-]*backend[\w-]*\s*$", acl, re.IGNORECASE)
        assert "hs109rs/" in acl
        assert re.search(r"(?m)^pattern\s+write\s+", acl) or re.search(
            r"(?m)^user\s+", acl
        )

    def test_persistence_and_listeners_unchanged(self):
        conf = _conf()
        assert re.search(r"(?m)^listener\s+1883\s*$", conf)
        assert re.search(r"(?m)^listener\s+9001\s*$", conf)
        assert re.search(r"(?m)^persistence\s+true\s*$", conf)


class TestNetworkExposure:
    def test_mqtt_ports_not_published_to_all_interfaces(self):
        compose = _compose()
        mqtt_block = compose.split("ztd-mqtt:")[1].split("volumes:")[0]
        # Neither 1883 nor 9001 may be published to 0.0.0.0 (bare "port:port"
        # or "${VAR:-port}:port"). Loopback bind or removal are acceptable.
        for port in ("1883", "9001"):
            assert not re.search(
                rf"(?m)^\s*-\s*[\"']?(\$\{{[^}}]*\}}:)?{port}:{port}[\"']?\s*$",
                mqtt_block,
            ), f"port {port} must not bind 0.0.0.0 on the host"

    def test_websocket_reachable_via_nginx_only(self):
        # Dashboard consumes MQTT WS through the nginx /mqtt location on the
        # internal network; the broker port itself stays container-internal.
        with open(
            os.path.join(REPO, "nginx", "default.conf"), encoding="utf-8"
        ) as fh:
            conf = fh.read()
        assert re.search(r"location\s+/mqtt\s*\{", conf)
        assert "ztd-mqtt:9001" in conf

    def test_healthcheck_authenticates(self):
        compose = _compose()
        # Second occurrence: the first is the depends_on reference.
        mqtt_block = compose.split("  ztd-mqtt:")[2].split("\nvolumes:")[0]
        health = mqtt_block[mqtt_block.index("healthcheck:"):]
        assert "-u" in health and "-P" in health, (
            "mosquitto healthcheck must pass credentials (anonymous disabled)"
        )
        assert "|| exit 0" not in health, (
            "healthcheck must not swallow auth failures"
        )


class TestCredentialProvisioningPath:
    def test_compose_mounts_password_file(self):
        compose = _compose()
        assert re.search(r"mosquitto/passwd:/mosquitto/config/passwd", compose)

    def test_compose_mounts_acl(self):
        compose = _compose()
        assert re.search(r"mosquitto/acl:/mosquitto/config/acl", compose)

    def test_operator_docs_exist(self):
        assert os.path.isfile(
            os.path.join(MQTT_DIR, "README-mqtt-auth.md")
        ), "operator credential-generation doc required"
