# Dashboard Bootstrap V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download a complete secret-free Agent V2 installer through the authenticated dashboard.
**Architecture:** Backend owns generation. Embed authoritative local agent and adapter sources with SHA-256 verification; no invented artifact URL. Browser submits only allowlisted non-secret configuration. Runtime credentials stay on the Pi.
**Tech Stack:** FastAPI, Pydantic, Python, Bash, NetworkManager, systemd, Vue, Node test runner.
**Spec:** User mission and autonomous execution authorization in this session.

## Global Constraints
- Preserve original dirty checkouts and remediation branch history; isolated branches, local integration only.
- No push, deployment, production changes, automatic Monitoring credential issuance, or legacy fallback.
- No Wi-Fi, Monitoring, MQTT, Tailscale or private-key secret in request or download.
- Preserve device/hub identity separation, deployment history, and network choices.

## Review Focus
- Tampered payload must fail before installation or service activation.
- Interrupted/rerun installation must preserve last usable configuration.
- Enterprise TLS requires trusted CA and server-name validation.
- Unknown request fields, including secrets, must be rejected without echoing values.
- Failed/unauthenticated generation must never trigger browser download.

### Task 1: Complete backend installer
Files: `apps/api/src/routes/bootstrap.py`, new installer resources under `apps/agent/`, `apps/api/tests/test_bootstrap_download.py`.
Consumes non-secret BootstrapRequest; produces deterministic complete shell download.
- [x] Inspect baseline generator, agent, BFF, frontend and NetworkManager documentation.
- [x] Run baseline backend and frontend suites (201 passed/3 skipped; 168 passed).
- [ ] Add failing schema, identity, payload integrity, installation, atomicity and prompt tests; capture red run.
- [ ] Implement strict schema and embedded verified executable/dependency installation, runtime secret prompts, atomic writes and cleanup.
- [ ] Verify backend acceptance tests before dashboard wiring.
- [ ] Commit backend installer.

### Task 2: Authenticated generation boundary
Files: `apps/api/src/routes/dashboard_bff.py`, `apps/api/tests/test_bootstrap_download.py`.
Produces POST `/api/dashboard/bootstrap/raspberry`, session-authorized, CSRF-checked, bounded, rate-limited, no-store shell response.
- [ ] Add and run failing authentication, authorization, CSRF, size-limit, invalid-input and response-header tests.
- [ ] Implement BFF generation and protect direct backend route.
- [ ] Run passing boundary tests and commit.

### Task 3: Dashboard integration
Files: `ztd-dashboard/src/api/bootstrapApi.js`, `src/views/DeploymentsView.vue`, `tests/bootstrapApi.test.mjs`, `tests/DeploymentsView.test.mjs`.
Consumes BFF shell response; produces download only after successful validation.
- [ ] Add and run failing endpoint, secret allowlist, failure/no-download and active-path tests.
- [ ] Implement request client, dual-server inputs and async download; preserve history and layout.
- [ ] Run frontend tests/build and commit.

### Task 4: Acceptance and integration
- [ ] Run full backend/frontend suites and build.
- [ ] Run actual isolated backend and dashboard; automate browser login and download where available.
- [ ] Inspect downloaded payload and record security, hardware and Monitoring coverage limits.
- [ ] Review diffs; commit evidence; fast-forward clean remediation worktrees and record final SHAs.
