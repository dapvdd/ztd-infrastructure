# PR00 — Ownership Boundaries, Handoff Record and PR01 Readiness

**Status: EVIDENCE BASELINE — 2026-11-19. DOCUMENTATION ONLY.**
Companion to `docs/sprint6/SOURCE_BASELINE.md`. Integration verdict unchanged: `SOURCE_ALIGNED_CONTRACT_BLOCKED`. No commit, push, merge, deployment or external-system change was performed.

## 1. Ownership map

| Component / surface | Owner | Authoritative evidence at PR00 | Mutation authority in this session |
|---|---|---|---|
| ZTD infrastructure repo (backend, API, agent, provisioning) | ZTD release/backend owner | `C:\Users\user\Development\ztd-preserved-20261111\infrastructure`, clean base `e01d1ed1e4a91cbb4ad2ea1429cf918304d77b04` | Read-only except new PR00 docs in the isolated worktree |
| Sprint 5.2 frontend worktree | Frontend owner (concurrent work) | `C:\Users\user\Development\ztd-ui-ux-sprint5`, HEAD `702a6066…`, dirty | **None.** No read-modify, build, test, reset, merge or cleanup |
| Dashboard source lineage (recovered commits) | Frontend owner | `C:\Users\user\Development\ztd-preserved-20261111\dashboard`, commits `942514f… → 2b2aca9a… → 702a6066…` | Read-only `git show/log/rev-parse` |
| Monitoring repository (`mochmizan/proyek-monitoring-dtedi`) | Monitoring team | Pinned `3afa0a954fac1b92cf9df7a29ed13bc82b5352e6`, clean read-only clone | **None.** No source, issue, PR, VPS or Pi change |
| Production VPS, nginx config, served dist | Production release owner | Audit R01/R02/R04/R10 (see `SOURCE_BASELINE.md` §9) | **None.** No access attempted |
| Raspberry Pi / hardware acceptance | Separately authorized hardware owner | `SPRINT6_HARDWARE_ACCEPTANCE_PLAN.md` H01–H12, R01–R10 | **None.** NOT RUN / NOT AUTHORIZED |
| Credentials, DB migrations, issuance/escrow | Named owner per M02/M09; not ZTD agent-side | `SPRINT6_MONITORING_TEAM_DECISIONS.md` | **None.** No credential operation or migration |
| PR00 documentation deliverables | Release integrity / PR00 executor | Isolated worktree `sprint6-pr00-provenance` at `e01d1ed1…` | Created two documents; no other source touched |

Policy applied: code/config/credential ownership follows the owning team, not the directory name or a passing mock. Source compatibility is never treated as approval.

## 2. Concurrent Sprint 5.2 preservation

Before and after PR00 work, the active frontend worktree reported the same state. This is a later point-in-time snapshot than the master plan §1 conflict map, which recorded four tracked edits at its inspection (plus a subsequently noted untracked report); the additional modified/untracked paths below are newly visible concurrent owner work and were not created by PR00. Worktree status must be rechecked before any future handoff:

- Modified (6): `ztd-dashboard/src/utils/monitoringStatus.mjs`, `ztd-dashboard/src/utils/provisioningState.mjs`, `ztd-dashboard/src/views/DeploymentsView.vue`, `ztd-dashboard/tests/DeploymentsView.test.mjs`, `ztd-dashboard/tests/monitoringStatus.test.mjs`, `ztd-dashboard/tests/provisioningState.test.mjs`.
- Untracked (5): `SPRINT5_2_UI_UX_REPORT.md`, `docs/`, `screenshots/sprint5-2/`, `ztd-dashboard/tests/operational-workspace.browser.py`, `ztd-dashboard/tests/remediation.browser.py`.

No file in that list was opened for writing, cleaned, built, tested, staged, reset or merged. The PR00 worktree was created from the infrastructure parent repository only, so it cannot overlap that tree. The dirty production nginx file cited in R01 remains historical user work; PR00 neither inspected it remotely again nor authorized reconciliation.

## 3. Frontend handoff record

Handoff is **not granted by PR00**. Required before any future PR10 UI change:

1. Frontend owner confirms the intended clean base commit (candidate: `702a6066…`) and opens a separate clean documentation/implementation branch.
2. The Sprint 5.2 dirty edits are explicitly accepted, stashed by their owner, or scoped out — never cherry-picked or reset by another owner.
3. `npm test` is re-run on the agreed clean baseline and the exact count recorded instead of assuming 220 forever (`SPRINT6_PR_BREAKDOWN.md` PR10 line 117).
4. DTOs from PR06/09 are stable and evidence labels distinguish source facts from owner claims.

Until then, PR10 remains blocked and the 205/220 figures stay historical (see `SOURCE_BASELINE.md` §5.1).

## 4. Decision authority — M01–M13

All decisions in `SPRINT6_MONITORING_TEAM_DECISIONS.md` remain **UNANSWERED / NOT APPROVED**. No agreement, issue, PR or commit in the pinned Monitoring tree grants them. PR00 records this; it does not resolve any item.

| Area | Decision IDs | Effect on later PRs |
|---|---|---|
| Identity/binding, issuer/secret lifecycle | M01, M02, M09 | PR02 final constraints; PR03 handoff; PR04, PR09, PR11 blocked |
| Release/artifact/runtime, OS/Python/architecture | M03, M11 | PR07 shipping, PR08/09 activation and PR11 blocked; Debian 13/ARM64/3.13 stays UNKNOWN |
| Callback sender, decision authenticity | M04, M10 | PR05, PR09 and PR11 blocked |
| Endpoints/trust/auth, env names | M05, M12 | PR01 fixtures, PR04, PR07/09 runtime config and PR11 blocked; ZTD uses runtime source names and records drift |
| Receipt evidence, hardware window | M06, M07 | PR09 verification, PR10 labels and PR11 blocked; no simulated success |
| Revocation/offline behavior, unit/stop/health | M08, M13 | PR05 policy, PR07 unit, PR08/09 activation and PR11 blocked |

A README example, a deployed configuration, a matching directory name, source compatibility or a passing mock is **not** approval. No global fleet `HUB_ID`, no automatic Device ID = HUB_ID, and no ZTD-generated Monitoring authority/HUB_KEY is assumed.

## 5. PR ownership and independent executability

From `SPRINT6_REVISED_IMPLEMENTATION_ORDER.md` §7, carried forward without granting execution authority:

| PR | Independent of Monitoring agreement? | Owner / condition |
|---|---|---|
| PR00 | Yes (this execution, documentation only) | Release integrity; isolated docs worktree |
| PR01 | ZTD-only fixtures yes; Monitoring-specific fixtures no | Backend/contract owner; separate approval; proposals clearly marked |
| PR02 | Structurally yes; final binding constraints need M01 | Backend owner |
| PR03 | ZTD-side yes; HUB_KEY handoff no | Backend owner with synthetic keys only |
| PR04 | **No** — blocked by M01/M02/M05/M09 | Monitoring agreement required |
| PR05 | **No** — blocked by M04/M10 | Monitoring agreement required |
| PR06 | Local yes; operational stage no | Backend owner; v2 gate preserved |
| PR07 | Generic primitives yes; shipping no (M03/M11) | Installer owner; inert fixture only |
| PR08 | Local yes; operational activation no | Orchestrator owner |
| PR09 | **No** — blocked by M05/M06/M08 | Monitoring agreement + evidence |
| PR10 | Only after frontend handoff and PR06/09 DTO stability | Frontend owner |
| PR11 | **No** — M01–M13 + authorized hardware | Joint, separately authorized |

Shared files (`provisioning/routes.py`, `schemas.py`, `models.py`, `agent_v2.py`, BFF) land serially under one owner at a time; no competing parallel edits.

## 6. Authority exercised and withheld in this session

Exercised: local read-only git inspection (`rev-parse`, `log`, `show`, `ls-tree`, `rev-list`, `status`, `worktree`), an isolated worktree creation from the clean authoritative SHA, documentation authoring, and execution of the repository's existing backend tests in that isolated tree.

Withheld: commits (explicitly forbidden), push/merge, any Monitoring or VPS access, any production/Pi/DB/credential operation, any frontend edit/build/test, dependency installation, code changes beyond the two PR00 documents, and any commissioning functionality.

## 7. PR01 readiness assessment

- **G0 evidence:** satisfied for source/test provenance and ownership boundaries by `SOURCE_BASELINE.md` §§2–9 and this document §§1–4.
- **G0 residual:** frontend owner handoff is unsigned; no isolated build/digest reproduction was performed; F02 and the R01/R02/R04/R10 discrepancies remain unresolved evidence.
- **G1:** not satisfied — M01–M08 unanswered, so contract freeze cannot be claimed.
- **Conclusion:** PR01's ZTD-only fixture work is technically separable and may be commissioned **only by a separate approval**. PR01 must use the actual runtime names (`SERVER_UNAPPROVED_URL`, `HUB_ID`, `/api/iot`), keep Monitoring-specific fixtures clearly proposed, preserve current v2 behavior, and include negative vectors for `SERVER_ALERT_URL`, `HUB_NAME`, doc-only ingest paths and the absent callback sender. This PR00 does not authorize or begin that work.

## 8. References

`SPRINT6_PR_BREAKDOWN.md` §§PR00/PR10; `SPRINT6_IMPLEMENTATION_MASTER_PLAN.md` §§3/7/9/10; `SPRINT6_REVISED_IMPLEMENTATION_ORDER.md` §7–8; `SPRINT6_MONITORING_TEAM_DECISIONS.md`; `docs/sprint6/SOURCE_BASELINE.md` (this worktree).
