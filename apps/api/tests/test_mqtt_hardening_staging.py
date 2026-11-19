"""F-07 hardening regressions found during live staging verification.

These encode the real failure modes observed on the staging broker:
- CRLF line endings in mosquitto.conf made mosquitto 2.x parse values
  literally ("false\\r"), silently leaving anonymous access enabled.
- The ACL used `pattern write hs109rs/#`, but mosquitto pattern rules apply
  to EVERY user, silently granting the read-only dashboard user write access.
- `topic readwrite #` does not match $SYS/# (wildcards never match $-topics),
  so the authenticated healthcheck could subscribe to nothing.
- The backend MQTT listener never called username_pw_set, so it was refused
  ("Not authorized") the moment anonymous access was disabled.
"""

import os
import re

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MQTT_DIR = os.path.join(REPO, "mosquitto")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(MQTT_DIR), reason="mosquitto config not present in this checkout"
)


def _acl() -> str:
    with open(os.path.join(MQTT_DIR, "acl"), encoding="utf-8") as fh:
        return fh.read()


def _listener_source() -> str:
    with open(
        os.path.join(REPO, "apps", "api", "src", "services", "mqtt_listener.py"),
        encoding="utf-8",
    ) as fh:
        return fh.read()


class TestFileFormat:
    def test_mosquitto_conf_has_lf_endings(self):
        with open(os.path.join(MQTT_DIR, "mosquitto.conf"), "rb") as fh:
            raw = fh.read()
        assert b"\r\n" not in raw, (
            "mosquitto.conf must use LF line endings: mosquitto 2.x parses "
            "CRLF values literally, silently disabling directives"
        )

    def test_acl_has_lf_endings(self):
        with open(os.path.join(MQTT_DIR, "acl"), "rb") as fh:
            raw = fh.read()
        assert b"\r\n" not in raw, "acl must use LF line endings (same CRLF hazard)"

    def test_gitattributes_enforces_lf_for_mosquitto(self):
        ga_path = os.path.join(REPO, ".gitattributes")
        assert os.path.isfile(ga_path), ".gitattributes must pin mosquitto LF endings"
        with open(ga_path, encoding="utf-8") as fh:
            ga = fh.read()
        assert "mosquitto" in ga and "eol=lf" in ga


class TestAclLeastPrivilege:
    def test_no_global_pattern_write_rules(self):
        """pattern rules apply to every user: never use them for grants."""
        acl = _acl()
        assert not re.search(r"(?m)^pattern\s+write\s+", acl), (
            "pattern write grants apply to ALL users (including read-only "
            "dashboard); use explicit per-user blocks instead"
        )

    def test_dashboard_is_read_only(self):
        acl = _acl()
        dash_block = acl.split("user ztd-dashboard", 1)[1]
        lines = [
            ln
            for ln in dash_block.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        assert lines, "dashboard ACL block must exist"
        for ln in lines:
            parts = ln.split()
            assert parts[0] == "topic" and parts[1] == "read", (
                f"dashboard rule must be read-only: {ln}"
            )

    def test_sys_topics_granted_for_healthcheck(self):
        assert re.search(r"(?m)^topic\s+read\s+\$SYS/#\s*$", _acl()), (
            "authenticated healthcheck subscribes to $SYS/#; a bare '#' never "
            "matches $-prefixed topics"
        )


class TestListenerAuthentication:
    def test_listener_sets_credentials_when_configured(self):
        src = _listener_source()
        assert "username_pw_set" in src, (
            "listener must authenticate: brokers with allow_anonymous false "
            "refuse the anonymous listener"
        )
        assert "settings.MQTT_USER" in src

    def test_listener_credentials_come_from_config(self):
        with open(
            os.path.join(REPO, "apps", "api", "src", "config.py"), encoding="utf-8"
        ) as fh:
            cfg = fh.read()
        assert re.search(r"MQTT_USER:\s*str", cfg)
        assert re.search(r"MQTT_PASS:\s*str", cfg)

    def test_compose_passes_listener_credentials(self):
        with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as fh:
            compose = fh.read()
        backend_block = compose.split("  ztd-backend:", 1)[1].split("\n  ztd-", 1)[0]
        assert re.search(r"MQTT_USER:\s*\$\{MQTT_USER", backend_block)
        assert re.search(r"MQTT_PASS:\s*\$\{MQTT_PASS", backend_block)
