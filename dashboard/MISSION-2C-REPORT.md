# ZTD Mission 2C delivery record

## Preservation
- Durable candidate: `C:\Users\user\Development\ztd-vnext-20261029`.
- Original candidate remains untouched. `candidate-original-manifest.csv` records SHA-256 and sizes for all 46 source/configuration/test files copied. Original checksum recheck: zero mismatches.
- Generated dependencies and build directories were excluded from the copy and regenerated locally. No existing destination was overwritten.
- Ignore rules cover dependencies, builds, environment secrets, key files, and browser artifacts. Limited source/test scan for private-key headers, GitHub tokens, and AWS access IDs found no matches; this is not a comprehensive secret audit.

## Implementation
- Dedicated Device 360 route uses GET detail by exact ID, with explicit 404 and response-identity validation, stale-request protection, metadata, backend presence, heartbeat, CPU/temperature freshness, telemetry table, reported module states, deployment history, and device-targeted configuration navigation.
- Partial section failures retain the device identity and offer refresh. Missing metrics are not converted to zero; units are never guessed.
- Deployment history retains search/status filters, status text and failure output; adds pending filtering and validates history arrays instead of silently presenting malformed responses as empty. Device identification comes from the requested device.
- Catalog failure/manual folder-name fallback preserved; malformed catalog responses now show errors. Module route honors explicit device query without selecting a substitute. Request acknowledgment remains distinct from agent-confirmed deployment.
- RBAC remains inactive: no credentials/accounts/sessions simulated. Integration text explicitly requires backend authorization and HTTPS. PermissionAction defaults denied and is presentation only.
- Local Vite development server binds loopback.

## Dependency security
- Original installed package: direct dev dependency `vite@8.3.1` (manifest previously permitted `^8.2.2`). Shared peer consumers include plugin-vue, vue-devtools/inspect/inspector, vue-router/unplugin.
- High advisory: GHSA-587h-7wmj-h5pm, launch-editor Windows existence-check bypass/command execution. Audit also listed GHSA-698v-4r3x-3vcv, GHSA-r825-w8mm-5pxw, GHSA-9jrq-w75r-8gcw, GHSA-rq7h-c2jc-7f22 and GHSA-vfpm-58rq-9qcg.
- Audit affected range: 8.3.0–8.3.2. Updated manifest/lock to compatible same-major Vite 8.3.3 (`^8.3.3`). No force update or backend dependency changes.
- Vite is build/dev/preview tooling, not the shipped static application's browser runtime. Risk centers on tooling behavior and plugin compatibility; verified build and local Chromium preview with Node 24.15.0.
- Final npm audit: zero vulnerabilities.

## Verification and independent review
- Existing Node tests: 60 passed, zero failed after dependency update.
- Production build: passed with Vite 8.3.3; rebuilt after review fix.
- Chromium isolated fixture test: passed, rerun after review fix. Covers navigation, device 404, empty/error states, module target, catalog outage, responsive overflow at 390/1280 pixels, keyboard focus, and uncaught JavaScript errors. Includes delayed-device-list regression asserting exactly one history refresh.
- Fixtures are explicitly synthetic and intercepted locally; no simulated data is represented as production telemetry. No production write requests were performed.
- Read-only production API checks returned HTTP 200 for device detail, metrics, telemetry (12 rows), and logs (44 rows); field shapes match implementation. Production source routes/schemas were also inspected read-only.
- Independent reviewer identified P2 duplicate module refresh race that could overwrite edits. Fixed refresh orchestration to load history once after list validation and disabled editing/deployment while busy. Regression browser check passed.
- Browser checks are targeted, not a full accessibility audit; expected HTTP failure scenarios may emit network-console errors. No uncaught page errors occurred. Live mutation/agent installation was not exercised.

## Repository ownership and delivery decision
- `/home/firza/.git` is the enclosing repository, so Git resolves `/home/firza` as root. Reflog records an initial infrastructure/orchestrator commit followed by master-to-main rename and nginx fix. Why the team chose the home directory cannot be established from history.
- Local main: `ba2bc2f`; initial source commit `6fed070`, both authored by `luqman`. Tracked root contains `.gitignore`, `ztd-infrastructure`, `ztd-orchestrator`; dashboard is untracked because it has not been added to that index/history.
- Configured origin: `https://github.com/FirzaSulaiman/ztd.git`. Advertised remote heads: only main at `e9d0ccd5ca95ea882208e618bf37e29835d82764`; corresponding available remote tree contains README.md only. No other advertised branch supplies production source.
- Production has modified infrastructure files and many untracked paths. Filesystem owner `firza` does not establish authorship; local commits by `luqman` reinforce the need for team attribution. None were staged, reset, or modified.
- History suggests local infrastructure/orchestrator grouping, but does not prove intended dashboard monorepo membership. The README-only remote and local source histories do not establish an approved delivery destination.
- **Git delivery BLOCKED.** Team must confirm repository URL/owner, monorepo versus dashboard repository, target base branch/path, and ownership of server-local changes. No branch, commit, push, merge, or remote SHA delivery was performed. No repository was initialized in production or the candidate.
- Recommended delivery after confirmation: obtain a clean local checkout of the approved base, create a feature branch, copy reviewed dashboard files into the approved path, review staged diff and scan secrets, rerun checks, commit/push only that branch, then verify its remote SHA. Preserve server work separately with its owners rather than adding the home-directory tree wholesale.

## Readiness
Ready for team review and destination decision, not production deployment. Authentication requires backend support and HTTPS. Installed-module data is inferred by the backend from latest successful events, not live inventory. Telemetry is the latest 12 samples, and history has no server pagination contract. Production mutation/end-to-end installation verification remains outstanding. Deployment was neither authorized nor performed.
