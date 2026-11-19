"""Static nginx configuration assertions (F-06: TLS + auth forwarding).

These tests parse the nginx conf files as text and assert the security-
relevant structure. They are intentionally static: the container integration
(nginx -t against a real cert) is documented as not-run on this Windows host.
"""

import os
import re

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
NGINX = os.path.join(REPO, "nginx")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(NGINX), reason="nginx config not present in this checkout"
)


def _read(name: str) -> str:
    with open(os.path.join(NGINX, name), encoding="utf-8") as fh:
        return fh.read()


def _read_compose() -> str:
    with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as fh:
        return fh.read()


class TestTlsServerBlock:
    def test_tls_listener_on_443(self):
        conf = _read("default.conf")
        assert re.search(r"listen\s+443\s+ssl", conf), "no TLS listener on 443"

    def test_http_redirects_to_https(self):
        conf = _read("default.conf")
        assert re.search(r"return\s+301\s+https://", conf), "port 80 must 301 to https"

    def test_certificate_paths_configured(self):
        conf = _read("default.conf")
        assert "ssl_certificate" in conf
        assert "ssl_certificate_key" in conf

    def test_modern_tls_versions_only(self):
        conf = _read("default.conf")
        assert "ssl_protocols" in conf
        protocols = re.search(r"ssl_protocols\s+([^;]+);", conf).group(1)
        assert "TLSv1.2" in protocols
        assert "TLSv1.3" in protocols
        assert "SSLv3" not in protocols
        assert "TLSv1 " not in protocols and "TLSv1;" not in protocols


class TestAuthForwarding:
    def test_provisioning_v2_forwards_authorization(self):
        conf = _read("provisioning-v2.location.conf")
        # F-06 core: the v2 location must forward the client Authorization
        # header (device Basic auth / admin bearer), never blank it.
        assert re.search(r"proxy_set_header\s+Authorization\s+\$http_authorization", conf)

    def test_dashboard_bff_location_blanks_authorization(self):
        conf = _read("default.conf")
        # The BFF location must NOT forward a client-supplied admin bearer.
        block = conf.split("location ^~ /api/dashboard/")[1].split("}")[0]
        assert 'proxy_set_header Authorization     ""' in block

    def test_dashboard_bff_location_exists(self):
        conf = _read("default.conf")
        assert "location ^~ /api/dashboard/" in conf

    def test_v2_snippet_included_inside_tls_server_block(self):
        """The location snippet must be include()d from the 443 server block,
        never mounted into conf.d/ where nginx would parse it at http level."""
        conf = _read("default.conf")
        assert "include /etc/nginx/snippets/provisioning-v2.location.conf;" in conf
        # include must sit after the 443 listener (i.e. inside that server block)
        assert conf.index("listen       443 ssl") < conf.index(
            "include /etc/nginx/snippets/provisioning-v2.location.conf;"
        )

    def test_compose_mounts_snippet_outside_conf_d(self):
        compose = _read_compose()
        assert "/etc/nginx/snippets/provisioning-v2.location.conf" in compose
        assert "/etc/nginx/conf.d/provisioning-v2.location.conf" not in compose


class TestComposeMounts:
    def test_compose_publishes_443(self):
        compose = _read_compose()
        assert re.search(r"-\s*['\"]?\d{0,5}:443", compose), "nginx must publish 443 (any host port)"

    def test_compose_mounts_v2_location_snippet(self):
        with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as fh:
            compose = fh.read()
        assert "provisioning-v2.location.conf" in compose

    def test_compose_mounts_cert_directory(self):
        with open(os.path.join(REPO, "docker-compose.yml"), encoding="utf-8") as fh:
            compose = fh.read()
        assert re.search(r"nginx-certs|/etc/nginx/certs", compose), (
            "TLS cert directory must be mounted for the nginx container"
        )
