# Provisioning V2 Implementation Plan

> Execute inline with executing-plans; independent review after verification. No commits or deployment authorized.

**Goal:** Authenticated registration, external approval gate, deterministic manifests and persistent assignments.
**Architecture:** Extend existing FastAPI/SQLAlchemy service with a separate provisioning registry, isolated from unauthenticated MQTT inventory. Technician pre-enrollment binds an ID to a high-entropy device credential; Pi registers with Basic auth. Monitoring remains sole approval authority through a proposed authenticated, versioned decision feed; disabled until configured and agreed.
**Tech Stack:** Existing Python, FastAPI, Pydantic, PostgreSQL; stdlib credential hashing.
**Spec:** User's Sprint 1 revised architecture; older docs/SYSTEM_CONTRACTS.md approval ownership is superseded.

## Global Constraints
- Production read-only; local clone at infrastructure HEAD 6b2a6dc33bac8c56a66b882c5f0c64a549e542f9.
- Preserve server .gitignore and untracked docs; no production migrations, secrets, records or service operations.
- No Monitoring implementation, new approval UI, arbitrary Git sources, invented versions, hardware attestation or monitoring credentials.
- New API credentials fail closed when absent; Basic device credentials require TLS at deployment.

## Evidence and capability matrix
| Capability | Existing | Gap / blocked |
|---|---|---|
| Registration | services/mqtt_listener.py process_register auto-discovery | No authenticated HTTP registration; models.Device has no credentials |
| Approval | Documents only | Old docs name Provisioning authority; revised requirement names Monitoring; external contract BLOCKED |
| Manifest | None in routes | Agent apps/agent/agent.py only publishes MQTT, no HTTP manifest consumer |
| Assignment | devices.py config publishes retained MQTT | No durable desired-state assignment; modules.py synthesizes 1.0.0 |
| Dashboard API | inventory, metrics, logs, module directory list | New authenticated provisioning contracts needed |

## Design decisions
Use additive provisioning tables rather than extending MQTT-controlled identity records. This avoids treating anonymous discovery as proof of identity and avoids telemetry overwriting approval. Preserve legacy inventory routes, but reject legacy config/delete for enrolled identities to prevent alternate provisioning paths. New approved module catalog is curated by authenticated administrators, pinned to 40-character commits from an environment allowlist. No runtime Git lookup or execution.

Monitoring decisions are an external projection, not local approval: integration-only bearer credential, explicit schema version, monotonic revision, actor/event identity, expiry and transition validation. An unconfigured integration cannot approve devices. Expired approvals fail closed. This proposal requires Monitoring acceptance before deployment.

## Review Focus
- Concurrent enrollment/registration and assignment writes: unique keys and row locks, PostgreSQL concurrency tests.
- Revocation/reordered events: monotonic revisions, replay equality, expiry, audit records.
- Legacy MQTT bypass and inventory deletion: independent registry, legacy management guard.
- Corrupt persisted manifest fields: response validation, generic error, no credentials.
- Proxy strips Authorization: prepare targeted v2 proxy location; deployment requires TLS.

## Tasks
- [x] Read audit, source and old contracts; establish boundaries and local clone. Baseline: 18 tests and 9 subtests pass from apps/api.
- [ ] Write failing API tests for enrollment, registration idempotency/auth, status and pending manifest gate; implement provisioning schemas/models/auth/routes and reversible migration.
- [ ] Write failing tests for external decision authentication, replay/transition/expiry, approved manifest and cross-device restrictions; implement decision projection and audit.
- [ ] Write failing tests for catalog/assignment authorization, source allowlist, commit validation, duplicates/removal, deterministic revision; implement persistent assignments and dashboard detail/list endpoints.
- [ ] Verify legacy protection, schema migration up/down and actual PostgreSQL concurrency in isolated database; run full existing suite, lint, formatting, strict type checks for new modules.
- [ ] Independent security/compatibility review, fix confirmed issues, rerun checks.
- [ ] Document endpoints, Monitoring dependency, Pi changes, deployment/rollback prerequisites and exact verification results.
