# Sprint 3 edge integration implementation plan

**Goal:** implement an independently managed, fail-closed V2 edge reconciler and secure bootstrap, with local integration evidence and a minimal Vue handoff.

**Architecture:** Provisioning owns desired module snapshots, Monitoring owns approval and hub/device identities, and the Pi owns protected credentials plus observed apply state. The existing MQTT prototype remains compatible. A separate Python agent validates schema 2, stages pinned repositories through locally approved launch profiles, atomically journals revisions, and verifies systemd services before marking an apply successful. HubBrain receives its actual environment through a local credential adapter; firmware onboarding is an offline proposal rather than an invented network API.

**Tech stack:** Python 3.11+, Pydantic 2, HTTPX, pytest, systemd, Git, existing Vue/Vite.

**Spec:** user Sprint3 instruction and `docs/PROVISIONING-V2-API.md`; source contracts take precedence over older documentation.

## Constraints and design decisions
- Work only in the two supplied isolated worktrees; Monitoring reference is read-only. No production, push, merge, or deployment.
- Basic credentials are supplied from existing enrollment, never issued by the edge. Hub/MQTT keys are separately supplied by operators.
- Keep ModuleConfiguration's sample interval contract; HubBrain does not consume it, so reject overrides for that profile rather than silently invent support.
- No arbitrary repository install hooks or shell commands from manifests. Local profiles pin repo, entrypoint and preinstalled Python environment.
- Approval/status failure stops managed services; restart requires a fresh approved response. Durable high-water revisions survive rollback and reboot.
- Browser never receives provisioning admin or hub secrets. BFF remains a separately owned prerequisite.

## Tasks (executed inline, no approval pauses)
- [ ] Bootstrap: failing tests for optional edge config, identity/HTTPS validation and protected atomic persistence; extend generator without changing network body.
- [ ] Agent: failing tests for strict manifests, authenticated registration/status gating, monotonic state, transactional apply/rollback/recovery, outages and revocation; implement in `apps/edge_v2/`.
- [ ] Adapters: test and implement protected HubBrain environment and offline ESP identity proposal; add systemd launcher and installation guidance.
- [ ] Integration: use real API with isolated SQLite and local HTTP fixtures; simulate service/hardware boundaries explicitly; exercise duplicate nodes, bad credentials, outages and interrupted apply.
- [ ] Dashboard: minimal bootstrap/handoff status guidance preserving existing layout; run Node tests and build.
- [ ] Verification/report: backend suite, edge suite, formatting/static checks, shell parsing, available browser checks; write `docs/SPRINT3-REPORT.md` with gaps and rollback readiness.

## Review focus
Same revision with changed content; crash between service activation and state commit; stale approval after reboot; symlink/credential permissions; MAC collisions across different gateways. Each belongs in edge/adapters regression tests.

## Initial evidence
- API register requires `hostname == authenticated device_id`; manifest schema is string `"2"`, with exact allowlisted HTTPS repos and 40-hex commits.
- API configuration currently accepts only `sample_interval_seconds`; no arbitrary secret fields.
- HubBrain source defaults telemetry to `/api/iot`, devices to `/api/devices`, with `X-Hub-ID`/`X-Hub-Key`; docs contain a conflicting telemetry suffix, so source wins.
- Firmware TS uses full MAC `DEV_ID`, boot-derived `TS-last4` display name and compile-time broker credentials. No dynamic enrollment API has been established.
- Windows host has Python/Node/Git, no Docker or Bash on PATH; Linux/systemd and physical hardware checks require explicit gap reporting.
