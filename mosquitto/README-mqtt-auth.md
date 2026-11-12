# MQTT authentication runbook (F-07)

The broker no longer accepts anonymous connections. Credentials live in two
operator-managed files, mounted read-only into the `ztd-mqtt` container:

- `mosquitto/passwd` — password file (never committed; generate per environment)
- `mosquitto/acl`    — topic ACL (committed; reviewed like code)

## 1. Generate the password file

```bash
# First user (-c creates the file):
docker run --rm -it -v "$(pwd)/mosquitto:/mosquitto/etc" eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/etc/passwd ztd-backend
# Add more users (no -c, or you wipe the file):
docker run --rm -it -v "$(pwd)/mosquitto:/mosquitto/etc" eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/etc/passwd gw-raspi-lab-01 'STRONG-PASSWORD'
docker run --rm -it -v "$(pwd)/mosquitto:/mosquitto/etc" eclipse-mosquitto:2 \
  mosquitto_passwd /mosquitto/etc/passwd ztd-dashboard
```

Users required by the committed ACL:

| User              | Purpose                                     | ACL                              |
|-------------------|---------------------------------------------|----------------------------------|
| `ztd-backend`     | FastAPI MQTT listener + config publisher    | readwrite `#`                    |
| `gw-<gateway-id>` | one per Raspberry Pi gateway agent          | write own status + sensor topics |
| `ztd-dashboard`   | browser WebSocket (via nginx `/mqtt`)       | read-only telemetry/status       |

## 2. File permissions (mosquitto 2.x requirement)

The broker refuses to load (or silently fails auth on) a passwd file that is
world-readable or not owned by its service user. Inside the container the
broker runs as UID 1883 (`mosquitto`), so on the host:

```bash
chown 1883:1883 mosquitto/passwd   # or the host user mapped into the container
chmod 600 mosquitto/passwd
```

Also: `mosquitto.conf` and `acl` MUST have LF line endings. mosquitto 2.x
parses CRLF values literally (`allow_anonymous false\r` is not recognized),
which silently leaves the broker misconfigured. `.gitattributes` enforces LF.

## 3. Restart the broker

```bash
docker compose up -d ztd-mqtt
```

## 4. Where each component gets its credentials

| Component            | Credential source                                                     |
|----------------------|-----------------------------------------------------------------------|
| `ztd-backend`        | `.env` (host): `MQTT_USER`, `MQTT_PASS` — never in git                |
| Gateway agent (Pi)   | `/etc/ztd/hubbrain.env` written by agent_v2 (`mqtt_user`, `mqtt_pass`)|
| Dashboard (browser)  | MQTT over WebSocket is **not authenticated at the broker** today; the nginx `/mqtt` location is the only path and sits behind the BFF session story (F-04). Do not publish the 9001 port. |
| ESP nodes            | unchanged — they publish to the **gateway's local Mosquitto on the Pi** (secrets.h at flash time), never to this broker |

## 5. ESP compatibility (preserved)

ESP firmware keeps its flash-time `secrets.h` credentials against the
**gateway-side** Mosquitto on the Pi. That broker is a separate deployment
concern; this compose file only governs the VPS broker. No firmware change is
required by this remediation.

## 6. Verification (documented, not run on the dev host)

```bash
# Anonymous must fail:
mosquitto_sub -h <vps> -p 1883 -t '#' -v        # expect Connection error / not authorised
# Authenticated read as backend:
mosquitto_sub -h <vps> -p 1883 -u ztd-backend -P '...' -t 'hs109rs/#' -C 1 -v
# Dashboard user must NOT be able to publish:
mosquitto_pub -h <vps> -p 1883 -u ztd-dashboard -P '...' -t 'hs109rs/ts/data' -m '{"x":1}'
# expect: Not authorized / ACL denial
```

Denial visibility: a QoS 0 denied publish is dropped silently and
`mosquitto_pub` still exits 0. Use QoS 1 (broker replies PUBACK reason code
"Not authorized", `mosquitto_pub` prints an error and exits non-zero) or MQTT
v5 (reason codes surfaced directly) when verifying ACL denials.

Gateway ACL blocks: `pattern` rules in mosquitto apply to EVERY user, so
gateway grants must be explicit `user gw-<id>` blocks in `acl` (see the
template in that file). Never add `pattern write <broad-topic>` — it would
silently grant the read-only dashboard user write access.

These commands were not executed here (no Docker on the remediation host);
container-level verification is listed as a remaining external dependency in
the remediation report.
