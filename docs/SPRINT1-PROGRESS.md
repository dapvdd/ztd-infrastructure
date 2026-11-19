# Sprint 1 execution ledger

Plan: docs/superpowers/plans/2026-11-05-provisioning-v2.md

- Baseline: isolated local clone, branch sprint1/provisioning-v2, HEAD 6b2a6dc. Production only read with SSH; audit read in full. Parent repository HEAD deada298; modified/untracked server files preserved.
- Existing tests: 18 passed, 9 subtests.
- Registration/auth red: two endpoint tests returned 404 rather than required 401. Added strict schemas, separate registry, auth and routes. Broader behavioral suite currently 32 passed, 9 subtests.
- TDD deviation: broader tests were added before implementation but only the initial two were individually observed failing before implementation. Do not claim full per-behavior red-green evidence.
- Ruling: use local clone rather than production worktree — no server filesystem mutation; untracked architecture docs copied read-only. Cost: deployment must separately reconcile user changes.
- Ruling: use dedicated provisioning registry — anonymous MQTT inventory is not identity authority. Cost: dashboard must consume separate provisioning inventory.
- Ruling: proposed Monitoring push projection with expiry, disabled without service credential — no deployed external authority discovered. Cost: external team must accept or revise contract before integration.
- Ruling: bound dependencies in test requirements after latest SQLAlchemy defaulted to uninstalled psycopg driver; existing source expects psycopg2. Cost: application runtime dependency bounds also need review before deployment.
- Local PostgreSQL binaries unavailable (EDB link delivered pgAdmin installer, not bare server); SQLite tests validate logic/locking/migrations. PostgreSQL concurrency and race tests marked skipped pending local or CI PostgreSQL. Review findings all addressed; full suite passes.
- Independent reviewer findings: (1) delayed revocation fail-open fixed with retrospective negative decisions; (2) assignment commit-before-validation fixed by validating before commit; (3) withdrawn snapshot reactivation fixed with explicit `withdrawn` flag and reassignment requirement. All three regressions have failing tests then fixes.
- Legacy guards implemented: v1 config/delete for enrolled devices return 409. Nginx Authorization header forwarding candidate written; production requires TLS and proxy review.
- Documentation: PROVISIONING-V2-API.md supersedes old docs' Provisioning approval proposal for v2. Monitoring integration contract proposed, BLOCKED pending agreement. No local approval UI or admin approval endpoint implemented.
