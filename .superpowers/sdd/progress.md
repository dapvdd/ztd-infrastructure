# SDD ledger — plan: docs/superpowers/plans/2026-11-11-sprint3-edge-integration.md

## Baselines
- Infrastructure worktree: sprint3/edge-integration branch from 8ec4900
- Dashboard worktree: sprint3/edge-dashboard branch from 6b6977c  
- Monitoring reference: read-only clone at C:/Users/user/AppData/Local/Temp/opencode/sprint3-monitoring-reference
- Sprint 1 baseline tests: 36 passed, 2 skipped (pre-Sprint 3)

## Pre-flight scan

| Task pair | Shared interface | Finding |
|---|---|---|
| T1→T2 | bootstrap extended fields → agent reads PROVISIONING_URL/MONITORING_URL from env/state | CLEAN — T1 produces shlex-quoted env vars in script; T2 reads from .env file at runtime; no naming conflict |
| T2→T3 | agent produces manifest JSON → adapter consumes it | CLEAN — adapter function signature takes manifest dict; no field name conflict |
| T2→T6 | agent state functions → integration tests call them directly | CLEAN — pure functions, no process or file side effects in tests |
| T3→T6 | hubbrain adapter → integration tests call with fixture credentials | CLEAN — test-only fixture uses ALLOW_INSECURE_DEV_KEYS=true |
| T4→T6 | esp adapter → integration tests verify identity mappings | CLEAN |

Pre-flight: clean. No conflicting interfaces found.

## Rulings made
- Ruling: HubGate credential issuance is BLOCKED — the Monitoring team has no provisioning endpoint that issues HUB_KEY automatically; adapter requires manually-provisioned HUB_ID/HUB_KEY supplied via env/secret; test fixture uses deterministic test keys — Why: hubs.py POST /api/hubs/pair only registers a hub with a bootstrap key, it does NOT issue device credentials to the ZTD system; there is no supported ZTD→HubGate issuance contract — Cost if wrong: Pi HubBrain cannot auto-connect to Monitoring VPS without manual credential injection; documented as explicit limitation
- Ruling: Dashboard BFF authentication (admin token) is BLOCKED for browser-held secrets — CORS + no session layer means admin token cannot safely be held in browser; dashboard shows provisioning status read via admin-authenticated BFF pattern; documented as limitation — Cost if wrong: status display works but requires BFF layer to be built separately
- Ruling: ESP firmware zero-touch wireless onboarding NOT claimed — firmware uses hardcoded secrets.h WiFi/MQTT credentials compiled at flash time; "zero-touch" for ESP requires reflashing with new secrets.h; adapter covers identity mapping and gateway-side whitelist only — Cost if wrong: ESP onboarding still requires physical flashing step

## Tasks
