# SDD ledger — plan: C:\Users\user\docs\superpowers\plans\2026-11-19-sprint6-pr01-ztd-contracts.md

Executor: inline (executing-plans). Mode: LOCAL IMPLEMENTATION — PR01 ONLY.
Worktree: C:\Users\user\.local\share\opencode\worktree\sprint6-pr01-contracts
Branch: sprint6/pr01-contracts
Base commit: 7eaf59b042ec4ddc4be16436d406de1f35f5c4bd (PR00 provenance commit)
Monitoring pin: 3afa0a954fac1b92cf9df7a29ed13bc82b5352e6 (read-only, no access)
Authorization: local ZTD-owned contracts/schemas/fixtures/tests only. NO commit/push/merge/deploy.

## Setup / pre-flight

- Verified PR00 commit 7eaf59b is HEAD of sprint6-pr00-provenance and is a valid commit object.
- Created isolated worktree from 7eaf59b with branch sprint6/pr01-contracts; status clean at creation.
- Confirmed GITDIR (.../.git/worktrees/sprint6-pr01-contracts) != COMMONDIR (.../infrastructure/.git): isolated linked worktree, not submodule.
- Read PR00 SOURCE_BASELINE.md and OWNERSHIP.md before implementation.
- Read full PR01 plan and all named specs (PR_BREAKDOWN §PR01, MANIFEST_SCHEMA_PROPOSAL, COMMISSIONING_STATE_MACHINE via plan, MONITORING_CONTRACT_PROPOSAL §§4-5, MONITORING_API_CONTRACT_EVIDENCE, SOURCE_BASELINE §7).
- Toolchain: Python 3.13.7, pytest 8.4.2, pydantic 2.12.5, PyYAML 6.0.3. jsonschema absent (plan uses test-only Pydantic v2 models).
- No dependency installed. No production file under apps/api/src/ or apps/agent/ touched. No frontend/Monitoring/VPS/Pi/DB/credential access.

## Rulings (pre-flight)

Ruling: Base the PR01 worktree on PR00 commit 7eaf59b, not the plan's e01d1ed1 — the explicit authorization names the committed PR00 baseline as the base; 7eaf59b is a docs-only commit on top of e01d1ed1, so all source contracts are identical and the PR00 docs are included. — Cost if wrong: PR01 ancestry includes two documentation files; harmless and matches the stated baseline.

Ruling: Do NOT commit any task. The plan says "commit only if separately authorized" and the authorization explicitly forbids commit/push/merge/deploy. Ledger completion lines record test commands/results and file state instead of commit SHAs. — Cost if wrong: changes stay uncommitted in the isolated worktree for the human partner to review; no shared state affected.

Ruling: Task 2 plan assertion `Decision.model_fields["schema_version"].default == "1"` is factually wrong at the pinned source —实测 default is PydanticUndefined (Literal["1"] has no default). Replace with `get_args(Decision.model_fields["schema_version"].annotation) == ("1",)` to test the same v2-pinning intent without editing production code (which is forbidden). — Cost if wrong: none; source unchanged and the literal value is still pinned by the test.

## Pre-flight shared-interface scan

Pre-flight: Interfaces are shared only through the test module's module-level helpers/models (FIXTURES, load_fixture, load_schema, LocalPlanModel, local_plan_schema, OperationalManifestModel, ExecutionEventModel, ApprovalEventModel, DIGEST_VECTORS, SIGNATURE_VECTOR) and the source-fact fixture. Task 1 produces facts consumed by Tasks 2/4; Task 3 produces LocalPlanModel consumed by Task 4; Task 5 produces digest/signature vectors consumed by Tasks 6/7; Tasks 3-6 produce four schemas consumed by Task 7; all tasks consumed by Task 8. Rulings above cover the only conflicts (base, commits, v2 assertion). Fixture names are pinned identically in every task per plan Self-Review.

## Tasks

- [x] Task 1: Source-fact and drift fixtures — RED: 2 failed (FileNotFoundError, missing fixtures); GREEN: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k "source_fact or drift_names"` → 2 passed, exit 0; `git diff --check` exit 0. No commit (ruling above).
  - Ruling: wrote the module preamble together with the RED tests (plan Step 1) instead of at Step 3, so RED failed for the intended reason (missing fixture files) rather than NameError. No outcome change; fixtures created in Step 3 as planned.
- [x] Task 2: v2 preservation guard — RED: 1 failed (`AssertionError: PydanticUndefined == '1'`, the plan's buggy Decision-default assertion, matching the pre-flight ruling); GREEN: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k v2_contract_unchanged` → 1 passed, 2 deselected, exit 0 (7 pre-existing Pydantic deprecation warnings from src/schemas.py, unrelated to PR01). `git status --short -- apps/api/src apps/agent` empty. No commit.
  - Ruling: route snapshot pins 12 (method, path) pairs actually registered at e01d1ed1 (verified via `app.routes`) and rejects any `/api/v3/` path; no dependency_overrides/env monkeypatch fixture added because the guard only reads `app.routes` and issues no request — no production route was added, patched or monkey-patched.
- [x] Task 3: LOCAL_INSTALL commissioning-plan schema — RED: 3 failed (missing fixtures + NameError LocalPlanModel); GREEN: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k "local_plan or missing_mqtt_user or unknown_schema"` → 4 passed, 3 deselected, exit 0. v2 guard re-run: 1 passed, exit 0. No commit.
  - Ruling: plan Step 4 says "PASS (5 tests)" but Step 1 names only 3 tests and Step 3 requires one schema/model equality assertion; implemented 4 tests and recorded the exact count rather than inventing a fifth. No functional deviation.
  - Note: committed `docs/sprint6/schemas/commissioning-plan.json` is generated from `LocalPlanModel.model_json_schema()` plus `$schema`/`$id`; the equality test strips only those two transport keys. `x-evidence: ztd_proposal` and `additionalProperties: false` are asserted directly. No real endpoint/key/secret in fixtures (`.invalid` broker host, opaque IDs).
- [x] Task 4: OPERATIONAL manifest schema (proposed, authority-gated) — RED: 4 failed (undefined model/missing fixtures/missing authority_notes/missing schema); GREEN targeted: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k "operational_requires or approval_not_connectivity or 202_is_not or generated_hub_key"` → 4 passed, exit 0. Full targeted: 11 passed, exit 0. Full regression: `python -m pytest apps/api/tests/ -q` → **302 passed, 2 skipped, 8 warnings in 26.98s** (PR00 baseline 291 passed + 11 new PR01 tests), exit 0. Warnings are pre-existing (starlette anyio alias + src/schemas.py Pydantic deprecations), not PR01 defects. No commit.
  - Note: `authority_notes` added to the Task 1 source-fact fixture exactly as planned; `not_approval` holds the three exact strings and `authority_loss` holds `401 from Monitoring`. Valid fixture uses source-verified endpoint paths (`/api/iot`, `/api/devices`, `/api/hub/commands`, `/api/iot/unapproved`) on `.invalid` hosts and an opaque `hub_credential` secret-role handle; no `hub_key` literal appears in schema or fixture.
- [x] Task 5: Execution event and canonical digest/signature vectors — RED: 3 failed (missing vector fixtures + undefined ExecutionEventModel); GREEN: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k "canonical_digest or signature_input or execution_event"` → 3 passed, exit 0. No commit.
  - Ruling: plan test used `json.dumps(event.model_dump())`, which raises `TypeError: Object of type datetime is not JSON serializable` because `device_timestamp` is an AwareDatetime (confirmed empirically). Changed to `json.dumps(event.model_dump(mode="json"))`; same secret-leak intent, no production change. — Cost if wrong: none; the serialized event is the correct leak-check surface.
  - Note: three digest cases pin literal canonical bytes — base D0, changed-value D1 ≠ D0, reordered-keys canonical bytes identical to base so D2 == D0 (asserted explicitly). No JCS encoder implemented. Signature vector is receiver input only with synthetic `test-only-key-1` and no sender. `ExecutionEventModel` enforces the immutable issued snapshot tuple.
- [x] Task 6: Proposed approval-event schema and absent-sender negative — RED: 2 failed (missing schema + undefined model); GREEN: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k "absent_sender or proposed_approval_event_fields or approval_expiry_uses"` → 3 passed, exit 0. No commit.
  - Ruling: same `json.dumps(event.model_dump())` datetime defect as Task 5 (confirmed there) → used `model_dump(mode="json")`. Same secret-leak intent, no production change.
  - Ruling: plan Step 3 requires "APPROVED requires future expires_at relative to a supplied receipt time in the test, never wall-clock" but names no test for it. Added `validate_approval_event(payload, receipt_time)` plus `test_approval_expiry_uses_supplied_receipt_time` (explicit UTC receipt, stale-expiry rejection). Plan's "PASS (2 tests)" therefore recorded as 3. — Cost if wrong: none; no wall-clock dependency introduced.
  - Note: `approval-event.json` carries `x-evidence: ztd_proposal`, `x-monitoring-sender: DOES_NOT_EXIST_AT_PINNED_SOURCE`, `x-approval-gate: M04/M10`, `x-no-connectivity-inference: true`. Historical missing-actor rejection was body validation only, not sender authentication. Final F7 micro-remediation below replaces that misleading negative with a valid body and explicit unverified-authentication evidence.
- [x] Task 7: OpenAPI 3.1 document and cross-artifact consistency — RED: 2 failed (`FileNotFoundError: docs/sprint6/openapi-v3.yaml`, matching plan); GREEN targeted: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q -k "openapi_references or approval_gates"` → 2 passed, 17 deselected, exit 0. Full targeted: 19 passed, 7 (pre-existing) warnings, exit 0. No commit.
  - Note: `docs/sprint6/openapi-v3.yaml` declares all 10 proposed v3 resources from MONITORING_CONTRACT_PROPOSAL §5, each with a non-empty `x-approval-gate` (operational_manifest=M01/M02/M04/M05/M06/M08, approval_events={event_id}=M04/M10, commissioning_plan=NONE_ZTD_LOCAL_ONLY). Four document-relative `$ref`s point to the committed JSON Schemas (changed from repo-root-relative during post-review remediation); `application/problem+json` appears in every path item (YAML alias to a shared Problem content); `components.securitySchemes.MonitoringSender.x-status: PROPOSED_NO_SENDER`; `info.x-evidence: ztd_proposal`. Forbidden drift strings absent and asserted by test. No Monitoring source endpoint registered as a ZTD resource. Redocly linter NOT run (tooling not approved).
- [x] Task 8: Full verification and evidence record — Full targeted: `python -m pytest apps/api/tests/test_sprint6_contracts.py -q` → 19 passed, 7 (pre-existing) warnings, exit 0. Full regression: `python -m pytest apps/api/tests/ -q` → **310 passed, 2 skipped, 8 warnings in 26.91s**, exit 0 (baseline 291 + 19 PR01 tests). `git diff --check` exit 0; trailing-whitespace scan of all 19 new text files → none; `git status --short` shows only PR01-owned untracked paths, no change under apps/api/src/, apps/agent/, PR00 docs or Sprint 5.2 tree. Environment: python=3.13.7, pytest=8.4.2, pydantic=2.12.5, pyyaml=6.0.3, node=v24.15.0, jsonschema absent. Evidence written to `.superpowers/sdd/SPRINT6_PR01/evidence.md`. Redocly lint NOT run (tooling approval absent). No commit/push/merge/deploy/frontend/Monitoring/hardware/credential action. Final verdict: `READY_FOR_REVIEW`.

## Post-review remediation ledger (independent NEEDS_FIXES → local fixes)

Independent review returned `NEEDS_FIXES` (4 IMPORTANT, 4 MINOR, no CRITICAL). All eight findings were remediated locally in the PR01 worktree only, with RED→GREEN cycles and no scope expansion:

- [x] F1 OpenAPI external `$ref` paths — RED: 2 failed on literal repo-root refs. Fix: document-relative `schemas/*.json` + resolver test. GREEN: 2 passed.
- [x] F2 APPROVED null/stale expiry — RED: 1 failed (null ACCEPTED). Fix: Pydantic model validator + schema `if/then` + `validate_approval_event(payload, receipt_time)`. GREEN: 4 targeted, then 21 all passed.
- [x] F3 derived-hub-id negative — RED: negative failed for the wrong reason. Fix: remove extra top-level `hub_id`, add `binding_is_not_derived_from_device_id`, annotate schema. GREEN: 22 all passed.
- [x] F4 schema semantic parity — RED: 1 failed (missing annotations). Fix: stdlib structural checker + `x-schema-conformance`/`x-runtime-invariants` on all four schemas. GREEN: 2 focused, then 24 all passed.
- [x] F5 equality gates — gap: only 1 of 4 schemas gated. Fix: equality gate for all four; mutation check confirms drift detection. GREEN: 4 passed.
- [x] F6 signature vector — RED: 1 failed (missing status key). Fix: `proposed_field_order`, `x-wire-format-status: NOT_FROZEN_PENDING_M04_M10`, no frozen HMAC encoding. GREEN: 2 passed.
- [x] F7 meaningful tests — gap: fixture-string restatement only. Fix: source-fact/drift URL gates, no `202`, no `PENDING`; mutation check confirms drift detected. GREEN: 2 passed.
- [x] F8 OpenAPI operations — RED: 1 failed (missing operationIds/x-auth). Fix: unique `operationId`, `x-auth-status` on all ten operations, `info.x-auth-model`. GREEN: 3 passed.

Fresh final verification after all remediation: targeted **30 passed, 7 warnings in 0.94s**; full regression **321 passed, 2 skipped, 8 warnings in 25.68s**; focused remediation selectors 10 passed / 20 deselected; mutation checks confirm all four equality gates and the source-fact gate detect drift; `git diff --check` exit 0; `git status --short --untracked-files=all` → 21 untracked PR01-owned files, no tracked file modified. No commit/push/merge/deploy; no runtime v2, Monitoring-source, dependency, frontend or operational change. Verdict: `READY_FOR_REVIEW` for independent re-review only; integration remains `SOURCE_ALIGNED_CONTRACT_BLOCKED`.

## Finding 7 final micro-remediation

Independent re-review found F7 PARTIALLY_FIXED; the prior shared-path membership gate permitted wrong endpoint roles. This section supersedes the earlier F7 completeness claim, not the seven findings already marked FIXED.

- [x] Reproduce old gate accepting ingest/devices swap in memory.
- [x] Add regressions: six role-pair swaps, four invented-path mutations; replace misleading absent-sender test with explicit body/authentication boundary characterization.
- [x] Observe RED: 7 failed / 5 passed / 28 deselected (six DID NOT RAISE swap failures; missing unverified-authentication marker).
- [x] Minimal correction: field-specific pinned endpoint mapping, retaining source-compatibility-not-approval boundary; option B for absent-sender evidence, valid body plus explicit UNVERIFIED_NOT_TESTED status, no authentication implementation.
- [x] GREEN: focused 12 passed / 28 deselected; full PR01 40 passed / 7 pre-existing warnings, including v2 guard. Commands and safety decision recorded in evidence.md.
- [x] Full backend assessed but not run: SQLite database use conflicts with no-database-access restriction. Previous full backend result remains historical only.
- [x] Scope limited to four existing PR01-owned files: tests, absent-sender fixture, evidence and this ledger. No commit/push/merge/deploy, no runtime/frontend/Monitoring change, no new dependency. Final verdict: READY_FOR_REVIEW (Finding 7 only); authentication remains unverified and integration remains contract-blocked.
