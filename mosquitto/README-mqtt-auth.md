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

## 2. Restart the broker

```bash
docker compose up -d ztd-mqtt
```

## 3. Where each component gets its credentials

| Component            | Credential source                                                     |
|----------------------|-----------------------------------------------------------------------|
| `ztd-backend`        | `.env` (host): `MQTT_USER`, `MQTT_PASS` — never in git                |
| Gateway agent (Pi)   | `/etc/ztd/hubbrain.env` written by agent_v2 (`mqtt_user`, `mqtt_pass`)|
| Dashboard (browser)  | MQTT over WebSocket is **not authenticated at the broker** today; the nginx `/mqtt` location is the only path and sits behind the BFF session story (F-04). Do not publish the 9001 port. |
| ESP nodes            | unchanged — they publish to the **gateway's local Mosquitto on the Pi** (secrets.h at flash time), never to this broker |

## 4. ESP compatibility (preserved)

ESP firmware keeps its flash-time `secrets.h` credentials against the
**gateway-side** Mosquitto on the Pi. That broker is a separate deployment
concern; this compose file only governs the VPS broker. No firmware change is
required by this remediation.

## 5. Verification (documented, not run on the dev host)

```bash
# Anonymous must fail:
mosquitto_sub -h <vps> -p 1883 -t '#' -v        # expect Connection error / not authorised
# Authenticated read as backend:
mosquitto_sub -h <vps> -p 1883 -u ztd-backend -P '...' -t 'hs109rs/#' -C 1 -v
# Dashboard user must NOT be able to publish:
mosquitto_pub -h <vps> -p 1883 -u ztd-dashboard -P '...' -t 'hs109rs/ts/data' -m '{"x":1}'
# expect: Not authorized / ACL denial
```

These commands were not executed here (no Docker on the remediation host);
container-level verification is listed as a remaining external dependency in
the remediation report.
