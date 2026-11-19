# PR01 evidence record — Sprint 6 ZTD-owned contracts (local, not for commit)

## Scope and base

- Plan: `C:\Users\user\docs\superpowers\plans\2026-11-19-sprint6-pr01-ztd-contracts.md`
- Worktree: `C:\Users\user\.local\share\opencode\worktree\sprint6-pr01-contracts`
- Branch: `sprint6/pr01-contracts`
- HEAD / base commit: `7eaf59b042ec4ddc4be16436d406de1f35f5c4bd` (PR00 provenance commit; docs-only on top of `e01d1ed1…`, so source contracts are identical)
- Monitoring source pin (read-only, never contacted): `mochmizan/proyek-monitoring-dtedi@3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`
- Authorization: local ZTD-owned contracts/schemas/fixtures/tests only. NO commit / push / merge / deploy.

## Environment (measured)

- python=3.13.7
- pytest=8.4.2
- pydantic=2.12.5
- pyyaml=6.0.3
- node=v24.15.0 (present; Redocly linter intentionally not run — see Limits)
- jsonschema: not installed (executable validation uses test-only Pydantic v2 models per plan)

## Task test evidence (exact commands, counts, results)

All commands run with `$env:PYTHONPATH='apps/api'` from the PR01 worktree root.

- Task 1 source-fact/drift — RED: 2 failed (missing fixtures). GREEN: `-k "source_fact or drift_names"` → **2 passed**.
- Task 2 v2 guard — RED: 1 failed (plan's buggy Decision-default assertion). GREEN: `-k v2_contract_unchanged` → **1 passed** (7 pre-existing `src/schemas.py` Pydantic deprecation warnings).
- Task 3 LOCAL_INSTALL — RED: 3 failed. GREEN: `-k "local_plan or missing_mqtt_user or unknown_schema"` → **4 passed**. v2 guard re-run: 1 passed.
- Task 4 OPERATIONAL — RED: 4 failed. GREEN targeted: `-k "operational_requires or approval_not_connectivity or 202_is_not or generated_hub_key"` → **4 passed**.
- Task 5 execution event / vectors — RED: 3 failed. GREEN: `-k "canonical_digest or signature_input or execution_event"` → **3 passed**.
- Task 6 approval event — RED: 2 failed. GREEN: `-k "absent_sender or proposed_approval_event_fields or approval_expiry_uses"` → **3 passed**.
- Task 7 OpenAPI — RED: 2 failed (`FileNotFoundError: docs/sprint6/openapi-v3.yaml`). GREEN: `-k "openapi_references or approval_gates"` → **2 passed, 17 deselected**.

### Final verification runs

- Full targeted (fresh, post-remediation): `python -m pytest apps/api/tests/test_sprint6_contracts.py -q` → **30 passed, 7 warnings in 0.94s**, exit 0. (Warnings are pre-existing `src/schemas.py` Pydantic deprecations, not PR01 defects.)
- Full backend regression (fresh, post-remediation): `python -m pytest apps/api/tests/ -q` → **321 passed, 2 skipped, 8 warnings in 25.68s**, exit 0. PR00 baseline was 291 passed; 19 original PR01 tests + 11 new regression tests = 321. No baseline test regressed.
- Focused remediation selectors: `-k "external_refs or matches_committed_document or structural or semantic or source_facts_and_drift or openapi or signature"` → **10 passed, 20 deselected in 0.28s**, exit 0.
- Mutation sensitivity (fresh, post-remediation):
  - `python C:\Users\user\AppData\Local\Temp\opencode\mutation_check_equality_gates.py` → all four committed schemas report `gate detects drift` (commissioning-plan, operational-manifest, execution-event, approval-event).
  - `python C:\Users\user\AppData\Local\Temp\opencode\mutation_check_source_facts.py` → `clean fixtures: gate passes`; drifted fixture fails with `URL path outside pinned source surface`.
- Bare `python -m pytest apps/api/tests/ -q` without PYTHONPATH is expected to fail collection with `ModuleNotFoundError: No module named 'src'` — harness environment fact, not a regression (not re-run here; recorded per plan).

## Schema validation outcomes

- Four JSON Schema 2020-12 documents generated from test-only Pydantic v2 models and checked in under `docs/sprint6/schemas/`: `commissioning-plan.json`, `operational-manifest.json`, `execution-event.json`, `approval-event.json`.
- Equality gates: `test_local_plan_schema_matches_committed_document` asserts `strip_schema_transport(doc) == LocalPlanModel.model_json_schema()`; `$schema`/`$id` are the only stripped keys. Other three schemas follow the same generation pattern (their models are the executable oracle).
- `x-evidence: ztd_proposal` present on every schema; `additionalProperties: false` on the LOCAL_INSTALL schema; approval-event carries `x-monitoring-sender: DOES_NOT_EXIST_AT_PINNED_SOURCE`, `x-approval-gate: M04/M10`, `x-no-connectivity-inference: true`.
- No real secret representable: `hub_key` absent from operational-manifest schema and fixture; `envelope_id` is the opaque handle. `approval-event.absent-sender.json` now passes body validation; sender authentication is explicitly unverified and UNKNOWN is only a proposed expectation, not an executed policy decision. Missing `actor` never proved authentication rejection. `derived-hub-id.json` now contains **no** extra top-level `hub_id`; it fails only because `binding.hub_id == device_id`, enforced by `OperationalManifestModel.binding_is_not_derived_from_device_id`. This is a test-only invariant and does **not** establish Monitoring-authorized binding (`x-binding-authority: NOT_MONITORING_AUTHORIZED`); no Monitoring binding API is assumed to exist.
- Canonical digest vectors pin literal bytes: base D0, changed-value D1 ≠ D0, reordered-key D2 == D0. Signature input vector is receiver input only with synthetic `test-only-key-1`.

## v2 compatibility

- `test_v2_contract_unchanged` passes: `Manifest.schema_version == "2"`, `Decision` Literal annotation `("1",)`, strict `HubConfig` with exactly `{hub_id, server_url, mqtt_host, mqtt_port}`, `extra=forbid`, no `mqtt_user`.
- Route snapshot pins all 12 `(method, path)` pairs under `/api/v2/provisioning` and asserts no `/api/v3/` route is registered. No production route added, patched or monkey-patched.

## Git / scope checks

- `git diff --check` → exit 0 (zero whitespace errors, re-run post-remediation). Trailing-whitespace scan of all new text files → none.
- `git status --short` → only 5 untracked PR01-owned paths; no tracked file modified. `git status --short --untracked-files=all` → 21 untracked files.
- No entry under `apps/api/src/`, `apps/agent/`, `docs/sprint6/SOURCE_BASELINE.md`, `docs/sprint6/OWNERSHIP.md`, or the Sprint 5.2 tree. No commit made.

## Files created (20, all untracked; relative to worktree)

- `apps/api/tests/test_sprint6_contracts.py` (all 30 tests after remediation, test-only models/helpers)
- `docs/sprint6/openapi-v3.yaml` (OpenAPI 3.1 proposed v3 surface)
- `docs/sprint6/schemas/`: `commissioning-plan.json`, `operational-manifest.json`, `execution-event.json`, `approval-event.json`
- `apps/api/tests/fixtures/sprint6/` (13): `monitoring-source-facts.json`, `monitoring-source-drift-negatives.json`, `commissioning-plan.local.valid.json`, `commissioning-plan.local.invalid-upstream.json`, `commissioning-plan.local.invalid-no-mqtt-user.json`, `operational-manifest.proposed.valid.json`, `operational-manifest.no-approval.json`, `operational-manifest.derived-hub-id.json`, `execution-event.valid.json`, `canonical-digest-vectors.json`, `signature-input-vector.json`, `approval-event.proposed.json`, `approval-event.absent-sender.json`
- `.superpowers/sdd/SPRINT6_PR01/progress.md`, `.superpowers/sdd/SPRINT6_PR01/evidence.md` (local evidence). Final `git status --short --untracked-files=all` reports **21 untracked files** (the earlier 20-file status snapshot predated evidence.md).

## Rulings / deviations from plan text (no functional impact)

1. Base commit `7eaf59b…` used instead of plan's `e01d1ed1…` (authorization names the committed PR00 baseline; source contracts identical).
2. No task committed (authorization forbids commit/push/merge/deploy).
3. `Decision` v2 assertion corrected from `.default == "1"` (factually `PydanticUndefined`) to `get_args(annotation) == ("1",)`.
4. Task 3 count recorded as 4 (plan said 5 but named 3 tests + 1 equality assertion).
5. `json.dumps(event.model_dump())` → `model_dump(mode="json")` in Tasks 5/6 (datetime not JSON-serializable otherwise).
6. Task 6 added `validate_approval_event(payload, receipt_time)` + a third test so APPROVED expiry is checked against an explicit receiver time, never wall-clock. Recorded as 3 tests.

## Monitoring blockers (unchanged)

- M01–M13 remain `UNANSWERED / NOT APPROVED`; source compatibility is not owner approval.
- No Monitoring callback sender, key issuer/escrow, binding API, approval event sender, telemetry receipt or hub heartbeat exists at the pinned source.
- 202 `pending_approval` is not approval; approval is not connectivity; `/api/devices` and `/delivered` are not operational evidence.
- PR04/PR05/PR09/PR11 and operational portions of PR03/06/07/08 remain contract-blocked; PR10 remains frontend-handoff-blocked.
- Full-stack verdict stays `SOURCE_ALIGNED_CONTRACT_BLOCKED`.

## Limits / not performed

- `npx @redocly/cli lint docs/sprint6/openapi-v3.yaml` NOT run — separate tooling approval required by plan; no dependency/tooling installed.
- No new dependency installed or declared. No HTTP/API call, migration, credential issuance/retrieval, Monitoring/VPS/Pi/DB/hardware access, real secret, frontend edit, commit, push, merge or deployment occurred.

## Post-review remediation (targeted, no scope expansion)

Independent review verdict `NEEDS_FIXES` (4 IMPORTANT, 4 MINOR, no CRITICAL). All eight findings remediated locally with RED→GREEN cycles; no runtime/Monitoring/frontend change, no new dependency, no commit.

1. **OpenAPI refs (P1):** four external `$ref`s changed from repo-root-relative `docs/sprint6/schemas/*.json` to document-relative `schemas/*.json`; new test resolves every external ref from `OPENAPI.parent`, asserts the file exists, parses and carries `$schema` 2020-12 + `x-evidence`. Literal-substring assertion removed.
2. **Approval expiry (P1):** `ApprovalEventModel` rejects `APPROVED` with null `expires_at` via a model validator; committed schema carries an expressible `allOf`/`if`/`then` requiring a non-null date-time string for `APPROVED`. `validate_approval_event(payload, receipt_time)` rejects stale expiry against the explicit receiver time; no wall-clock authority.
3. **HUB_ID binding (P1):** top-level `hub_id` removed from `operational-manifest.derived-hub-id.json`; new `binding_is_not_derived_from_device_id` validator rejects `binding.hub_id == device_id`; schema annotated `x-runtime-invariants` + `x-binding-authority: NOT_MONITORING_AUTHORIZED`. Explicitly not Monitoring-authorized binding.
4. **Schema semantic parity (P1):** a documented minimal structural checker (stdlib only, NOT a conforming validator) validates all four valid fixtures and catches expressible negatives. Temporal/cross-field rules are declared in `x-runtime-invariants` + `x-schema-conformance` and proven to require the Pydantic validators. No claim of full independent schema conformance; `jsonschema` is not installed.
5. **Equality gates (P2):** all four committed schemas now equality-gated against their test models; mutation check confirms each gate detects drift.
6. **Signature vector (P2):** `field_order` → `proposed_field_order`; `x-wire-format-status: NOT_FROZEN_PENDING_M04_M10`; note no longer claims a specified encoding. HMAC wire format not frozen (M04/M10).
7. **Meaningful tests (P2):** source facts and drift negatives now gate real fixture monitoring URLs (pinned paths + `.invalid` hosts), and no `202` response / no `PENDING` approval status is permitted. Mutation check confirms a drifted URL is caught.
8. **OpenAPI operations (P2):** unique `operationId` and explicit `x-auth-status` on all ten operations; `info.x-auth-model` states no issuer/escrow/Monitoring sender is assumed or invented.

Remediation verification: each finding had a RED failure (or documented gap) before its smallest correction and a GREEN focused run afterward; full targeted suite went 19 → 30 passed, full backend regression 310 → 321 passed with 2 skipped. Mutation checks confirm the new equality and source-fact gates detect deliberate drift. No finding required runtime API v2, Monitoring-source, dependency, frontend, or operational changes.

## Final verdict

`READY_FOR_REVIEW` for independent re-review of the eight remediated findings only. No commit/push/merge/deploy is authorized. Integration activation remains contract-blocked by the unresolved Monitoring decisions above; no operational claim is made.

## Finding 7 final micro-remediation — 2026-11-19

This section supersedes the earlier F7 completeness claim and earlier final-run counts. Independent re-review marked F7 PARTIALLY_FIXED; findings 1–6 and 8 were not reopened.

- [x] Reproduce: in-memory ingest/devices role swap incorrectly passed the original shared-set gate.
- [x] RED: focused selector `source_gate or absent_sender or source_facts_and_drift` → **7 failed, 5 passed, 28 deselected**, exit 1. All six role-pair swaps failed with DID NOT RAISE; absent-sender evidence lacked its explicit unverified marker. The four invented-path negatives and clean gate already passed.
- [x] Correct: enforce `ingest_url → /api/iot`, `devices_url → /api/devices`, `commands_url → /api/hub/commands`, `unapproved_url → /api/iot/unapproved`, grounded in pinned `hub/main.py:61–72` at `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`. These are source-compatible proposal roles, not Monitoring owner approval. Retain illustrative-host and forbidden-drift checks; URL fields cannot silently bypass checks with a non-HTTPS value.
- [x] Absent-sender option B: fixture now includes illustrative `actor` and `authentication_verification: UNVERIFIED_NOT_TESTED`. Renamed test explicitly demonstrates that a body containing status APPROVED passes model validation without authenticating a sender. UNKNOWN remains a proposed fixture expectation only. No sender, verifier, receipt policy or authentication protocol was added.
- [x] GREEN focused: **12 passed, 28 deselected**, exit 0. All six role swaps rejected; invented `/api/iot/telemetry` rejected for each of four roles; unchanged source-derived fixtures accepted.
- [x] Complete PR01 suite: **40 passed, 7 pre-existing Pydantic deprecation warnings**, exit 0. Includes unchanged v2 route/model guard.
- [x] Full backend safety assessment: NOT RUN in this session. Existing backend tests create/access SQLite databases (e.g. `test_auth_rbac.py:50–54`, `test_dual_server_acceptance_16.py:152`); the task forbids database access. Earlier **321 passed / 2 skipped** is historical evidence, not a fresh result for this micro-remediation.

Both pytest commands used `PYTHONPATH=apps/api`, `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and `python -B -m pytest apps/api/tests/test_sprint6_contracts.py -q -p no:cacheprovider --assert=plain`; focused run additionally used `-k 'source_gate or absent_sender or source_facts_and_drift'`. Mutation tests intercept fixture reads in memory and invoke the actual artifact gate; no fixture mutation is persisted.

Changed files only: test module, absent-sender fixture, this evidence record and progress ledger. No schema/OpenAPI/runtime/dependency change. All 21 candidate PR01 files remain the same scoped inventory. Final scope/hash verification is recorded in the session report. Verdict: `READY_FOR_REVIEW` for Finding 7 only; authentication unverified and integration `SOURCE_ALIGNED_CONTRACT_BLOCKED` remain explicit limitations.
