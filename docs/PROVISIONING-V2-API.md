# Provisioning v2 integration contract (Sprint 1)

Status: local implementation; **Monitoring integration BLOCKED pending agreement**. This document supersedes the old documents' Provisioning-owned approval proposal for v2. No local approval UI or admin approval endpoint exists.

## Identity and workflow

1. Authenticated technician/server creates an enrollment for an agreed `raspi-[a-z0-9-]{3,20}` ID. Response returns a server-generated 256-bit password once. Database stores SHA-256 of that random credential, not plaintext. Duplicate enrollment is 409 and does not rotate credentials.
2. Technician securely transfers username/password to the Pi (mode 0600). Basic auth proves possession of this credential, **not hardware identity**. MAC/hostname claims alone never authenticate.
3. Pi registers with Basic auth and its matching hostname. Retry is idempotent and preserves first registration timestamp. Status is REGISTERED/PENDING.
4. Monitoring makes the approval decision. Its service sends the proposed versioned event below. Neither Pi nor Provisioning administrator credentials authorize it.
5. Pi retrieves manifest only while registered and holding unexpired APPROVED state. Pending/rejected/revoked/expired states receive 403. Empty assignments return an explicit EMPTY manifest.

## Authentication and configuration

- Device: HTTP Basic (`device_id`, returned password), over HTTPS.
- Admin: bearer from `ZTD_PROVISIONING_ADMIN_TOKEN`, at least 32 characters.
- Monitoring adapter: separate bearer from `ZTD_MONITORING_TOKEN`, at least 32 characters. Leave unset until the external contract is agreed. Missing configuration is 503; missing/wrong credentials are 401.
- Catalog: exact comma-separated HTTPS Git repository allowlist in `ZTD_MODULE_REPOSITORIES`; empty means deny all.
- Use distinct random secrets. Admin bearer belongs in a trusted dashboard backend/session service, **never a shipped Vue/Vite bundle**. Per-user admin RBAC and audit identity are Sprint 2 work.
- Existing Nginx strips Authorization. Candidate `nginx/provisioning-v2.location.conf` must be reviewed and included in the HTTPS virtual host before deployment. No proxy change has been deployed.

## Endpoints

Base `/api/v2/provisioning`. JSON bodies, standard FastAPI `{"detail": ...}` errors for compatibility; validation detail is an array.

| Method/path | Caller | Body/result |
|---|---|---|
| POST `/devices` | admin | `{"device_id":"raspi-plant-01"}` → 201 status + one-time `password`, no-store |
| POST `/register` | device | `{"hostname":"raspi-plant-01"}` → 200 persisted status |
| GET `/status` | device | own registration/approval/configuration revisions and timestamps |
| GET `/devices` | admin | provisioning inventory (separate from MQTT inventory) |
| GET `/devices/{id}` | admin | registration details/status, no credential hash/password |
| GET `/manifest?device_id={optional-own-id}` | device | authorized own manifest; different ID → 403 |
| GET `/modules` | admin | approved, currently allowlisted catalog entries |
| PUT `/modules/{name}` | admin | `{"repo_url":"https://github.com/NICEganteng/modulraspipmld.git","commit":"<40 lowercase hex>","approved":true}` |
| GET `/devices/{id}/assignments` | admin | validated pinned assignment information |
| PUT `/devices/{id}/assignments/{name}` | admin | `{}` or `{"configuration":{"sample_interval_seconds":30}}`; create/update idempotently |
| DELETE `/devices/{id}/assignments/{name}` | admin | 204, idempotent |
| PUT `/integrations/monitoring/devices/{id}/approval` | Monitoring only | versioned decision projection, below |

Unknown fields are rejected. Module config currently supports only integer `sample_interval_seconds` (1..86400); arbitrary secret/config fields are rejected. Empty config means no override. This is deliberately narrow and requires module-team schema agreement.

Manifest example (values illustrative):
```json
{
  "schema_version": "2",
  "device_id": "raspi-plant-01",
  "configuration_revision": 1,
  "updated_at": "2026-11-05T08:00:00Z",
  "assignment_status": "ASSIGNED",
  "modules": [{
    "name": "temperature",
    "repo_url": "https://github.com/NICEganteng/modulraspipmld.git",
    "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "configuration": {"sample_interval_seconds": 30}
  }]
}
```

Commit references are supplied by trusted catalog curation, validated syntactically, not verified as existing in Git. No fabricated semantic versions, artifact checksums, monitoring API keys or URLs. Assignments pin snapshots; ordinary catalog upgrades do not move them. Withdrawal permanently marks existing snapshots ineligible until explicit reassignment. A reapproved replacement cannot silently reactivate a withdrawn snapshot. Catalog withdrawal blocks the complete manifest (409), rather than silently omitting requested modules.

## Proposed Monitoring decision contract v1 — NOT an established external API

```json
{
  "schema_version": "1",
  "event_id": "monitoring-event-unique-id",
  "revision": 1,
  "status": "APPROVED",
  "actor": "monitoring:technician-7",
  "expires_at": "2026-11-05T09:00:00Z"
}
```

- Authority: Monitoring's decision store, whose location/API is not yet available in inspected evidence. Provisioning stores an auditable projection and event body, not a second independent authority.
- Monotonic per-device revisions; globally unique event IDs. Same current revision/body is an idempotent retry. Old/conflicting revisions return 409. Revision gaps are allowed for latest-state delivery.
- PENDING → APPROVED/REJECTED/REVOKED; APPROVED → APPROVED (renewal)/REVOKED; REJECTED → REJECTED/REVOKED; REVOKED → REVOKED. Re-enablement intentionally unsupported pending explicit contract.
- APPROVED requires future expiry. Negative decisions are applied even after expiry, so delayed revocation cannot leave an older grant active.
- Expired approvals block manifests without a scheduler. Monitoring must renew before expiry. Revocation latency is bounded by delivery/expiry, not instantaneous if the external service is unavailable.
- Agree registration discovery, credential distribution, revision allocation, renewal duration, revocation delivery/retry, terminal-state recovery, event retention, clock synchronization and service identity before deployment.

## Errors and client behavior

401: authenticate again; 403: device cannot provision / cross-device access; 404: absent enrollment/module; 409: duplicate enrollment, invalid transition/revision, withdrawn/invalid assignment; 422: malformed or disallowed input; 503: required service authentication unconfigured. Retry network failures with backoff. Never retry 409 by replacing the device ID or assuming a new credential was issued.

## Compatibility and readiness

Existing v1 dashboard reads retain their paths and shapes. Config/delete for enrolled identities now return 409 and direct callers to v2. Migration must precede code activation because those guards query the new registry. Legacy MQTT retained config, direct MQTT publishes and old agents remain outside v2's authentication boundary; an enrolled Pi must stop consuming that legacy provisioning channel and clear old retained config during an approved rollout.

The inspected `apps/agent/agent.py` is MQTT-only and cannot consume this manifest. Pi work: secure credential storage, POST register, poll status/backoff, GET manifest, honor 403/409, validate schema 2, fetch only allowed repository/commit, verify checkout commit, apply per-module config, handle empty desired state and removal. Real Pi verification has not occurred.

The old documented `/api/v1/provision/manifest` never existed in inspected code; no compatibility alias is claimed. No provisioning completion/ACK is fabricated: status currently covers enrollment/registration/approval and desired configuration revision, not observed installation success.
