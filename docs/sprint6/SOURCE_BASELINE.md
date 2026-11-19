# PR00 — Source, Test and Release Provenance Baseline

**Status: EVIDENCE BASELINE — 2026-11-19. DOCUMENTATION ONLY.**
**Integration verdict (unchanged): `SOURCE_ALIGNED_CONTRACT_BLOCKED`.**
**No commit, push, merge, deployment, production/VPS/Pi access, credential operation, database migration or Monitoring modification was performed.**

This document executes only PR00 as defined in `SPRINT6_PR_BREAKDOWN.md` §PR00 (lines 11–19), updated by `SPRINT6_REVISED_IMPLEMENTATION_ORDER.md` §7 line 95 and `SPRINT6_IMPLEMENTATION_MASTER_PLAN.md` §§9–10. It records provenance; it does not implement commissioning, does not correct production, and does not claim that a served bundle was built from any commit.

## 1. Source-of-truth hierarchy applied

1. Pinned Monitoring GitHub source at `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6` (runtime code over docs/examples).
2. Monitoring repository tests and documentation (classified `S`/`T`/`D`/`E`/`O`; see the source audit).
3. ZTD source and contracts in the clean authoritative worktrees.
4. The twelve `C:\Users\user\SPRINT6_*.md` planning documents and their reconciliation addenda.
5. Clearly labelled proposals. A README/.env.example value is **never** production configuration.

## 2. Authoritative repository and worktree identities

| Role | Path / repository | Revision | State at PR00 |
|---|---|---|---|
| Parent ZTD infrastructure repository (git common dir) | `C:\Users\user\Development\ztd-preserved-20261111\infrastructure\.git` | main checkout `8ec49007b310eac71fce01fb63a74f76907d624a` (branch `sprint1/provisioning-v2`) | Not modified |
| Authoritative backend/agent base (prior audit L01) | `C:\Users\user\.local\share\opencode\worktree\4fdc7b\bootstrap-v2-integration` | `e01d1ed1e4a91cbb4ad2ea1429cf918304d77b04`, branch `sprint5/auth-central-rbac` | Clean; not modified |
| **PR00 isolated worktree (this baseline)** | `C:\Users\user\.local\share\opencode\worktree\sprint6-pr00-provenance` | `e01d1ed1e4a91cbb4ad2ea1429cf918304d77b04`, new branch `sprint6/pr00-provenance` | Created clean; contains only this PR00 documentation |
| Parent ZTD dashboard/dashboard repository (git common dir) | `C:\Users\user\Development\ztd-preserved-20261111\dashboard\.git` | main checkout `6b6977cda8f803df930e0b9746442ff460e382f9` | Not modified |
| Active Sprint 5.2 frontend worktree | `C:\Users\user\Development\ztd-ui-ux-sprint5` | `702a6066d7c131655c0cc4fca773922c480d5862` | **Dirty and concurrently owned; not touched, not built, not tested** |
| Monitoring dependency clone (read-only) | `C:\Users\user\Development\proyek-monitoring-dtedi` | `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`, branch `main` | Clean; read-only dependency; origin `https://github.com/mochmizan/proyek-monitoring-dtedi` |

Source ownership was **not** ambiguous: `e01d1ed1…` is the infrastructure/backend base (master plan L01); the three frontend commits live in the separate dashboard repository; Monitoring is a distinct upstream repository. Preflight therefore did not trigger the "stop on ambiguity" condition.

## 3. Recoverable commits and ancestry

All four commits cited by PR00 are recoverable locally. Important refinement: `942514f…`, `2b2aca9a…` and `702a6066…` are **not** objects in the infrastructure repository; they belong to the dashboard repository. This is recorded rather than silently assumed.

| Short | Full SHA | Repository | Subject / date (author date) | Recovery command |
|---|---|---|---|---|
| `e01d1ed1…` | `e01d1ed1e4a91cbb4ad2ea1429cf918304d77b04` | infrastructure | `docs(sprint5): staging rehearsal evidence — 20-check matrix, migration round-trip, CSRF host-port finding, teardown` / 2026-11-16T17:33:56+07:00 | `git -C <infra> rev-parse e01d1ed1…` |
| `942514f…` | `942514fda79f8ecea082c8e48c33080ca7a43e87` | dashboard | `sprint5(auth): centralized login, RBAC-aware UI, user management` | `git -C <dashboard> rev-parse 942514f…` |
| `2b2aca9a…` | `2b2aca9a956065411f0290c1c56462860833ff51` | dashboard | `feat(ui): dedicated auth shell, role-aware layout and Sprint 5.1 design system` | `git -C <dashboard> rev-parse 2b2aca9a…` |
| `702a6066…` | `702a6066d7c131655c0cc4fca773922c480d5862` | dashboard | `docs: record implementation commit SHA in final report` / 2026-11-19T08:50:43+07:00 | `git -C <dashboard> rev-parse 702a6066…` |

Verified parent chain (`git rev-list --parents -n 1 <sha>`):

```
942514fda79f8ecea082c8e48c33080ca7a43e87 <- c584f058c34ea3b1e2b08abf2091eefc975244ba
2b2aca9a956065411f0290c1c56462860833ff51 <- 942514fda79f8ecea082c8e48c33080ca7a43e87
702a6066d7c131655c0cc4fca773922c480d5862 <- 2b2aca9a956065411f0290c1c56462860833ff51
```

This confirms the documented Sprint 5.1 ancestry `942514f… → 2b2aca9a… → 702a6066…`.

## 4. Immutable source manifests (read-only)

Commands (PowerShell, 2026-11-19) and exact results:

```
$r='C:/Users/user/Development/ztd-preserved-20261111/infrastructure'
$c='e01d1ed1e4a91cbb4ad2ea1429cf918304d77b04'
git -C $r rev-parse "$c^{tree}"                       -> dfbff57ea346393db4dbf1232eee02b350971fba
(git -C $r ls-tree -r --name-only $c).Count           -> 134
git -C $r ls-tree -r $c | git -C $r hash-object --stdin -> 763a5faf8a75699322557892ea73a9097784668f
test-*.py files in that tree                          -> 20

$r='C:/Users/user/Development/ztd-preserved-20261111/dashboard'
$c='702a6066d7c131655c0cc4fca773922c480d5862'
git -C $r rev-parse "$c^{tree}"                       -> 56309b81bc1aa8eb72ff963245b47561eaee50e3
(git -C $r ls-tree -r --name-only $c).Count           -> 116
git -C $r ls-tree -r $c | git -C $r hash-object --stdin -> e5a69a961ac63622b54cd691d1cf6628003e8031
*.test.mjs files in that tree                         -> 24
```

The `hash-object --stdin` value is a Git object ID of the pinned recursive tree listing; it is a compact, reproducible inventory fingerprint for these exact commands. It is not a substitute for an artifact/build digest and does not prove any deployed bundle's origin.

## 5. Reproducible test baseline

### 5.1 Historical evidence — two different baselines, not one contradiction

| Evidence | Value | Source |
|---|---|---|
| Local audit suite on a server-checkout copy | **205 passed, 0 failed, 0 skipped**, exit 0 (`node --test "tests/**/*.test.mjs"`) | `ZTD_CONFORMANCE_AUDIT.md` line 88; also `PHASE8-READINESS-SPRINT5.md` lines 70/167 (22 files) |
| Sprint 5.1 implementation report | **220 passed, 0 failed**, 5 suites | `C:\Users\user\Development\ztd-ui-ux-sprint5\SPRINT5_UI_UX_REPORT.md` line 52 |
| Static declaration delta | 183 → 198 top-level `test(` declarations; test files 22 → 24; **net +15** | `SPRINT6_IMPLEMENTATION_MASTER_PLAN.md` L09 (line 47) |
| PR00 independent re-measurement | **183 → 198**, net **+15**, files **22 → 24** — matches L09 exactly | read-only `git show <sha>:<testfile>` + `^\s*test\s*\(` line count over each pinned tree |

Declarations are not runtime case totals; the +15 delta explains how the reported 220 can exceed the observed 205 across different source baselines. Both numbers remain **prior evidence**, not a rerun of the served release.

### 5.2 Baseline executed in this PR00 worktree (fresh, this session)

Environment: Windows (PowerShell), Python `3.13.7`, pytest `8.4.2`, Node `v24.15.0`. Source: PR00 worktree at `e01d1ed1…`. No dirty UI tree, no build, no network, no shared-system mutation.

| # | Exact command | Result | Exit |
|---|---|---|---|
| 1 | `$env:PYTHONPATH='apps/api'; python -m unittest discover apps/api/tests/ -v` | `Ran 18 tests in 0.001s` — **OK** (unittest-discoverable cases only) | 0 |
| 2 | `python -m pytest apps/api/tests/ -q` (without `PYTHONPATH`) | Collection errors in `test_auth_central.py` / `test_auth_rbac.py`: `ModuleNotFoundError: No module named 'src'` — harness environment missing the repo's documented `PYTHONPATH`; **not** a source defect | 2 |
| 3 | `$env:PYTHONPATH='apps/api'; python -m pytest apps/api/tests/ -q` | **291 passed, 2 skipped, 8 warnings in 25.48s** | 0 |

Full command output retained at `.superpowers/sdd/SPRINT6_PR00/baseline-unittest.log`, `baseline-pytest.log` and `baseline-pytest-with-path.log` in the PR00 worktree.

Limitations, stated explicitly: the dashboard/frontend suite was **not run** (the only local frontend checkout is dirty and concurrently owned; PR00 forbids running tests/build there). No `npm test`, vite build, API server, database migration, hardware, Pi, Monitoring or production test was executed. The 291/2 backend result is a new baseline for the clean infrastructure tree; it does not retroactively prove the 205/220 figures or any deployed artifact.

## 6. Component and dependency inventory

Source evidence only. No dependency installation, lockfile generation, wheel download or version substitution was performed.

| Component | Pinned source | Declared dependencies / runtime (evidence) |
|---|---|---|
| ZTD API | `e01d1ed1…` `apps/api/requirements.txt` | `fastapi>=0.110.0`, `uvicorn[standard]>=0.28.0`, `pydantic-settings>=2.2.0`, `psycopg2-binary>=2.9.9`, `sqlalchemy>=2.0.28`, `paramiko>=3.4.0`, `paho-mqtt>=2.0.0`, `itsdangerous>=2.1.0`, `argon2-cffi==23.1.0`, `argon2-cffi-bindings==21.2.0` (offline wheel-staging comments present in file) |
| ZTD API test tooling | `apps/api/requirements-test.txt` | `sqlalchemy>=2.0.28,<2.1`, `fastapi>=0.110,<0.120`, `starlette<0.49`, `itsdangerous>=2.0`, the two argon2 pins, `pytest>=8,<10`, `httpx>=0.27,<0.29`, `pytest-cov>=5,<8`, `ruff`, `black`, `mypy` |
| ZTD agent | `apps/agent/requirements.txt` | `httpx>=0.27,<0.29`, `paho-mqtt>=2.0.0` |
| ZTD dashboard (pinned `702a6066…`) | `ztd-dashboard/package.json` | `vue ^3.5.42`, `vue-router ^5.3.1`; dev `vite ^8.3.6`, `@vitejs/plugin-vue ^6.0.8`, `vite-plugin-vue-devtools ^8.2.1`; engines `node ^22.18.0 || >=24.12.0`; test script `node --test "tests/**/*.test.mjs"` |
| HubBrain (Monitoring, read-only) | pinned source `hub/requirements.txt` | `paho-mqtt==2.2.1`, `requests==2.32.3`, `python-dotenv==1.0.1`, `urllib3==2.2.3`; CI/Docker Python 3.12, `requires-python >=3.12` |

Not established and not asserted: ARM64/Debian 13/Python 3.13 support, a paho 2.2.0 rationale, hash-locked wheel set, signed release, or any artifact digest linking source to production. See `SPRINT6_MONITORING_GITHUB_SOURCE_AUDIT.md` §2/§3 and `SPRINT6_MONITORING_TEAM_DECISIONS.md` M03/M11.

## 7. Pinned Monitoring source reference (read-only dependency)

| Item | Value |
|---|---|
| Repository | `mochmizan/proyek-monitoring-dtedi` — public, default branch `main` |
| Pinned commit | `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6` |
| Subject / author date | `feat(telemetry): update ATS and ACC payload schemas and databases` / 2026-10-13T07:19:42Z |
| Commit link | `https://github.com/mochmizan/proyek-monitoring-dtedi/commit/3afa0a954fac1b92cf9df7a29ed13bc82b5352e6` |
| Source link pattern | `https://github.com/mochmizan/proyek-monitoring-dtedi/blob/3afa0a954fac1b92cf9df7a29ed13bc82b5352e6/<path>#L<n>` |
| Local verification | Clean clone at that SHA, 348 blob paths enumerated from the pinned tree; read-only |
| Runtime names that override docs/examples | `SERVER_UNAPPROVED_URL`, `HUB_ID`, `POST /api/iot`, headers `X-Hub-ID` / `X-Hub-Key` |
| Absent contracts | No key issuer/escrow, binding/generation/approval event, callback sender, hub heartbeat or telemetry receipt API, watchdog/health/stop contract, or signed release artifact |

### 7.1 Documentation/example drift — locations only, no values

Recorded per reconciliation addendum; **no credential value is reproduced**.

| Runtime source | Doc/example claim | Locations (no values) |
|---|---|---|
| `SERVER_UNAPPROVED_URL` | `SERVER_ALERT_URL` | `hub/.env.example:18`, `hub/README.txt:68`, `docs/PRODUCTION_DEPLOYMENT_GUIDE.md:194`, `tools/deploy_pi_edge.py:105`, `tools/verify_prod_env.py:451` |
| `HUB_ID` | `HUB_NAME` | `hub/README.txt:62`, `tools/deploy_pi_edge.py:98` |
| `POST /api/iot` | `/api/iot/telemetry` | `hub/AGENTS.md` (doc-only path) |
| Python 3.12 CI/Docker, `>=3.12` | "3.10+" / "3.14" | `docs/LOCAL_TESTING_GUIDE.md:40`, `server/AGENTS.md` |
| Canonical `deploy/hubbrain.service` | two differing variants | `tools/install_pi_service.py:13-37`, `hub/README.txt:129-142` |
| Credential literal locations (weak/example values) | — | root/hub/tools `AGENTS.md`, `.env.example`, `README.txt`, test fixtures — **locations only**; report to Monitoring owner, never copy into ZTD config |

Full evidence: `SPRINT6_MONITORING_GITHUB_SOURCE_AUDIT.md` §§1–3, `SPRINT6_MONITORING_API_CONTRACT_EVIDENCE.md`, `SPRINT6_HUBBRAIN_V5_COMPATIBILITY_MATRIX.md`.

## 8. Git and release provenance / reconstruction procedure

**Prior R10 evidence (cited, not re-fetched in PR00):** live HTTPS `/` SHA-256 `9c12ded81ec00c2f576d914dabdf496e9fc05257fd0bddb5801834d07f05bcff`; `/assets/index-C2b51f_B.js` SHA-256 `9f4ec0f2b27cdbe53ac164da0e9f8be2016dc83f1ba18c96f5ad7f5ff6f25a98`. Both matched `D/dist` and the corresponding `dist-release-702a6066` files; all 10 release files matched, while the live dist contained six additional old assets, so the directories were **not** byte-identical as sets. Canonical citation: `ZTD_CONFORMANCE_AUDIT.md` line 45 (R10).

These hashes prove only that a served entry point matched a named local release directory at audit time. A directory name is **not** proof of a commit, and PR00 makes **no** claim that a served bundle was built from `702a6066…`.

Documented reconstruction procedure (future, **not executed**, requires separate authorization):

1. Start from the pinned clean source commits above in a fresh isolated worktree; do not use the dirty Sprint 5.2 tree.
2. Record exact tool versions and package-lock/node versions (Node engine range above; lockfile to be inspected when approved), OS/architecture and interpreter.
3. Build with the documented `vite build` / `node --test "tests/**/*.test.mjs"` scripts in the clean tree.
4. Compare emitted chunk/manifest names and SHA-256 digests against the R10 values and the release directory.
5. Record any diff as unresolved evidence; do not infer source identity from a matching directory name.
6. Keep all outputs in the isolated workspace; no production/localhost fetch or deployment.

## 9. Known production-versus-source discrepancies (unresolved evidence, not deployment failure)

| ID | Observed discrepancy | Classification | Evidence |
|---|---|---|---|
| R01 | Production infrastructure tracked-dirty `nginx/default.conf` | Historical user work; not reconciled by PR00 | `ZTD_CONFORMANCE_AUDIT.md:36`; master plan line 57 |
| R02 | Production dashboard HEAD `942514f…`; `git rev-parse 702a6066` failed there; release/backup dirs untracked | Locally recovered commit now available; production lineage still unproven | `ZTD_CONFORMANCE_AUDIT.md:37`; master plan L08/L10 |
| R04 | `ztd-nginx` config mounted read-only; loaded worker configuration history not reconstructed | Unverified config history | `ZTD_CONFORMANCE_AUDIT.md:39` |
| R10 | Served entry points match `D/dist` and `dist-release-702a6066`; six extra old assets in live dist; sets not byte-identical | Unresolved evidence, **not** a deployment failure claim | `ZTD_CONFORMANCE_AUDIT.md:45` |
| F02 | Release/artifact/config lineage not reproducibly attributable | PARTIAL / P2; stays open until build evidence | `SPRINT6_17_FINDINGS_TRACEABILITY.md` row 2 |

## 10. Evidence-based readiness gates for PR01

| Gate | Requirement | Status after PR00 |
|---|---|---|
| G0 source/ownership | Recover commits, distinguish test baselines, record frontend handoff, immutable release metadata | **Evidence recorded here**; frontend handoff still unsigned (see `OWNERSHIP.md`); no build reproduction performed |
| G1 contract freeze | ZTD v3 contracts + Monitoring M01–M08 acceptance | **BLOCKED** — decisions unanswered |
| PR01 scope | ZTD-owned fixtures/tests with proposals clearly marked; exact Monitoring runtime names | Technically independent and available after separate approval; Monitoring-specific fixtures remain proposals |

PR00 does **not** authorize PR01 implementation. Full-stack integration remains `SOURCE_ALIGNED_CONTRACT_BLOCKED`; F17 remains UNVERIFIED; no release, deployment, migration, hardware, credential or Monitoring-side change is authorized.

## 11. Non-goals observed

No dirty-tree reconciliation; no nginx or production correction; no redeploy; no source inference from a directory name; no closure of F02 without build evidence; no commit/push/merge; no Monitoring VPS or Pi access; no credentials, database migration or frontend edits.

## 12. References

`SPRINT6_PR_BREAKDOWN.md` §PR00; `SPRINT6_IMPLEMENTATION_MASTER_PLAN.md` §§3/9/10; `SPRINT6_REVISED_IMPLEMENTATION_ORDER.md` §7; `SPRINT6_MONITORING_GITHUB_SOURCE_AUDIT.md`; `SPRINT6_MONITORING_API_CONTRACT_EVIDENCE.md`; `SPRINT6_HUBBRAIN_V5_COMPATIBILITY_MATRIX.md`; `SPRINT6_MONITORING_TEAM_DECISIONS.md`; `SPRINT6_17_FINDINGS_TRACEABILITY.md`; `ZTD_CONFORMANCE_AUDIT.md`; `PHASE8-READINESS-SPRINT5.md`; `SPRINT5_UI_UX_REPORT.md`.
