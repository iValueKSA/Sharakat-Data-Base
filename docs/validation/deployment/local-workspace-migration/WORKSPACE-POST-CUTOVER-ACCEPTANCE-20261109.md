# Post-Cutover Workspace Acceptance — 2026-11-09

**Report generated:** 2026-11-09 09:21:47 UTC
**Status:** **PARTIAL**  
**Project root:** `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`

## Decision

The live Docker rebind is complete and the platform is operational from the official root. Database and Redis persistence were preserved, post-cutover DQ has zero failures, and the full isolated regression has zero failures. Migration acceptance remains partial because authentication behavior in the running `local_user` configuration fails the requested unauthorized-access check, XLSX did not finish within the 45-second runtime probe, authenticated UI/exports were not verified, and Stop/Restart batch scripts were not exercised against the healthy live service.

## Live Docker and workspace evidence

- Compose project identity remains `alahsa-local`.
- All six running services (`api`, `frontend`, `worker`, `scheduler`, `db`, `redis`) have `com.docker.compose.project.working_dir` set to the official root above.
- Active source-code bind mounts to the previous root: **0**. API and worker backup binds point to `%LOCALAPPDATA%\Sharakat Data Base\backups`; frontend and scheduler have no host binds. PostgreSQL and Redis use Docker named volumes.
- PostgreSQL uses `alahsa-local_postgres_data` at `/var/lib/postgresql/data`; Redis uses `alahsa-local_redis_data` at `/data`. Both original volume names remained attached after rebind.
- `docker compose ls` still reports the old Compose file paths as well as the new paths because exited one-shot `migrate` / `local-bootstrap` containers retain historical labels. They are not running and do not have active source mounts. The six live services point only to the official root.
- A separate `alahsa-transfer-test-1a3f8332` project remains on its own network, database, Redis, and port. Its scheduler has `PORTABLE_TRANSFER_TEST_MODE=1`, so it does not compete with the single active `alahsa-local` Beat scheduler. Its API container remains unhealthy, but it is isolated from `alahsa-local` and does not compete for its queues. It was not modified.
- No application images were rebuilt. The pre-cutover image comparison showed matching application/frontend content apart from byte-level line endings and a package initializer hash difference; migration configuration changes did not require a code rebuild.

## Data preservation and scheduler

- PostgreSQL is healthy on PostgreSQL 16.15; Alembic head remains `0025_source_geographic_coverage`.
- Current database counts: 6,678 opportunity rows (6,657 current, 21 merged), 9,468 `source_opportunities`, and 54,996 observations. DQ reports 14 configured sources, 13 enabled, and 13 open reviews.
- The pre-cutover custom-format backup is outside OneDrive at `%LOCALAPPDATA%\Sharakat Data Base\backups\workspace-migration-20261109T082421Z.dump`; SHA-256 `4BB2E52513C990A3D5491F50C914FC6A7EA8310591F0D35D4C8A0EC2E6690211`. It restored successfully in an isolated PostgreSQL 16 instance with matching pre-cutover counts and schema head.
- Compared with that backup, observations increased from 54,967 to 54,996 (+29). The scheduled `alahsa-opportunities` job ran 2026-11-09 08:28:07–08:28:48 UTC and completed successfully with zero new Masters. This natural scheduled activity preceded cutover; no manual source synchronization was initiated. Current Master and SourceOpportunity row counts remain unchanged.
- Beat’s saved schedule file was copied to AppData before the rebind and restored to the new scheduler container with matching SHA-256 `F4A50B760AAB1E2817F9D49A9D5EEB1091CF4E4860C8EBEB53E1A46303E5B6C9`. Beat started from the restored `PersistentScheduler` state.
- Latest inspection found no active, reserved, or scheduled worker tasks and zero items in the source, maintenance, exports, notifications, document-processing, and default queues. Redis AOF is enabled and reports `aof_last_write_status=ok`.
- Furas national enumeration remains disabled by its false default; the removals flag is unset. No schedule configuration was changed.
- A natural scheduled job changed observation state before cutover. No business-data edit, identity rewrite, or source sync was performed by the agent. The one-shot bootstrap reported `ALREADY_IMPORTED`; migration remained at the existing head.

## Post-cutover runtime and API checks

- Readiness: `http://localhost:8080/health/ready` returned HTTP 200 with database, Redis, and worker checks `ok`.
- Frontend `/`: HTTP 200.
- Opportunity list, second-page request, and search request: HTTP 200; page requests returned two distinct rows each.
- Dashboard, data dashboard, geography summary, geography catalog, geography filter options, region options, source coverage, and national map data endpoint: HTTP 200. The map-data response was 1,785,827 bytes. Geographic selectors returned 13 regions and 149 governorates; the first region had 12 governorates.
- No API 5xx entries appeared in the inspected recent API log window. Some geography routes took 3–7 seconds; the individually retried routes returned 200.
- Visual browser acceptance was not performed. The prior Computer Use session was blocked because its URL could not be determined, and the current task explicitly says not to retry it.

## Authentication and exports

- Anonymous `/api/auth/me` returned HTTP 401.
- **Authentication blocker:** anonymous `GET /api/admin/users` returned HTTP 200 and a two-user response in the running `ENVIRONMENT=local_user` configuration. `ADMIN_TOKEN` is unset. In this mode, `admin_auth` permits requests when no session and no configured token are present. This does not satisfy the requested unauthorized API restriction. The production-mode role fixture in the isolated regression passed, but it does not override the live local-mode result.
- Anonymous CSV export returned HTTP 200 with a 360,403-byte response. Thus authenticated CSV authorization was not established by this check.
- Anonymous XLSX export did not return within 45 seconds (`curl` status `000`). This is a runtime timeout, not a recorded HTTP error. Full regression export fixtures passed, but those do not establish live authenticated export behavior.
- The full regression includes the production security fixture; it passed viewer/admin authorization checks in its isolated test environment. No live Admin or Viewer UI session was used.

## Startup scripts

- Existing batch wrappers use quoted `%~dp0` paths and `cd /d "%~dp0"`, supporting spaces and the Unicode project path. Local Compose helper resolves the private AppData config and retains `alahsa-local`.
- The already-running startup/readiness branch and `Platform Status.bat` were validated before this post-cutover review; the controlled cutover cold start itself also succeeded.
- Stop/Restart batch scripts were not invoked because they would cause another live interruption. They remain unverified end-to-end. The previous maintenance authorization covered the cutover only.
- During the cutover, Compose `start` also started the exited migration/bootstrap dependencies. Migration was already current and bootstrap returned `ALREADY_IMPORTED`; counts and schema head remained stable. No initialization or import occurred.

## DQ and regression

### Full DQ

- Run ID: `8e99668c8f3741f1ae9021fd6df29b3e`
- Scope: full; read-only transaction; `persist=false`; post-cutover database snapshot recorded 54,996 observations and Alembic head 0025.
- Result: **134 gates; 128 PASS, 6 WARNING, 0 FAIL**.
- Warnings: `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`, `OPEN_REVIEW_BACKLOG`, `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`, `SOURCE_LAST_SUCCESS_TOO_OLD`, `SYNC_RUNTIME_ANOMALY`, `UNKNOWN_AREA_STORED_AS_ZERO`.
- Executed 2026-11-09 after cutover. The ephemeral `--rm` runner returned the run ID and result but did not retain exact wall-clock start/end timestamps.

### Full isolated regression

- Command scope: canonical `tests/`; project mounted read-only; disposable SQLite database; async pytest plugin installed only in the disposable container.
- Result: **703 passed, 1 skipped, 0 failed**, 43 warnings, 86.23 seconds.
- The skipped test requires an isolated PostgreSQL advisory-lock test database (`FURAS_CHECKPOINT_TEST_DATABASE_URL`). Warnings were existing Starlette/httpx and Alembic deprecations.
- Executed after cutover on 2026-11-09. The disposable container did not retain exact start/end wall-clock timestamps.

## Remaining blockers and manual checklist

1. Resolve the live `local_user` unauthenticated admin-user endpoint behavior before claiming authentication/RBAC acceptance. This report does not change that behavior.
2. Verify CSV and XLSX with an authorized session and confirm XLSX completes against the live dataset.
3. Verify Admin and Viewer UI visibility/permissions, dashboard/map, and export downloads manually. The Windows browser tool was unavailable under the task’s no-retry instruction.
4. Stop/Restart `.bat` behavior remains unverified against the live stack; obtain a separate maintenance authorization before any additional interruption.
5. Exact wall-clock start/end times for the two completed tests were not retained by their ephemeral runners; only the DQ run ID and regression duration survived.

Suggested manual checklist:

- Sign in as Admin; confirm the admin controls, national dashboard, opportunity list, map, regional filters, search, pagination, CSV, and XLSX.
- Sign out and sign in as Viewer; confirm read-only views and that admin/user-management actions are denied or hidden.
- Confirm the exported files open and reflect the selected filters.

## Final fields — original 09:21 UTC snapshot

- `PROJECT_ROOT`: verified official root.
- `LIVE_DOCKER_REBOUND`: TRUE.
- `OLD_ACTIVE_SOURCE_BIND_MOUNTS`: 0.
- `DATABASE_PRESERVED`: TRUE.
- `REDIS_PRESERVED`: TRUE.
- `LOCAL_PLATFORM`: OPERATIONAL.
- `ONE_CLICK_STARTUP`: PARTIAL.
- `AUTHENTICATION`: FAIL for the live anonymous admin-user endpoint; `/api/auth/me` alone correctly returns 401.
- `AUTHENTICATED_EXPORTS`: PARTIAL; live authenticated check pending, anonymous CSV returned data, XLSX timed out.
- `ROLE_SPECIFIC_UI`: PENDING_MANUAL_VERIFICATION.
- `CELERY_SCHEDULER`: HEALTHY; one active `alahsa-local` Beat with restored schedule, idle queues. Separate transfer-test Beat is isolated and test mode.
- `DATA_QUALITY`: 128 PASS / 6 WARNING / 0 FAIL.
- `REGRESSION`: 703 passed / 1 skipped / 0 failed.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: NONE by the agent; natural scheduled observation change documented above.
- `WORKSPACE_MIGRATION`: PARTIAL.
- `NEXT_DEVELOPMENT_READY`: FALSE until authentication/export and manual UI acceptance blockers are resolved.

## Follow-up acceptance review — 2026-11-09 09:39 UTC

This addendum preserves the original post-cutover evidence above and records the targeted follow-up. It did not repeat the Docker rebind, restart a service, modify security configuration, access the restricted Windows browser, or write to the live business database.

### Authentication and RBAC

- The live `local_user` probe showed `/api/auth/me` = **401** and anonymous `/api/admin/users` = **200** (305-byte response). This demonstrates the request had no authenticated session while the admin guard treated the absence of identity as sufficient in non-production mode; no implicit local user identity is supplied.
- The accepted authentication ADR requires production admin APIs to use authenticated sessions. The local Windows runbook documents login/session use and says the listener is loopback-only. The persistent `local_user` environment is the operational user installation, so anonymous user-management access is not an intended trust boundary.
- Minimal source correction: `admin_auth` now treats `local_user` as a protected mode alongside `production` and `staging`. Anonymous admin requests fail with 401; authenticated non-admin requests remain 403; an authenticated Admin remains permitted. The development/test shared-token fallback remains available only in the existing unprotected modes.
- The change is in source only. The running API container was not rebuilt or restarted, so the live endpoint remains on the prior code and the correction is **not deployed**. Deployment requires separate maintenance authorization.

### Export policy, integrity, and performance

- The local runbook defines CSV/XLSX as read-only downloads from the opportunity view. The accepted local UI baseline is loopback-only and includes anonymous read views; the ADR requires authenticated sessions for admin APIs, not public opportunity reads. Accordingly, anonymous exports remain allowed in this local loopback mode, and signed-in Admin and Viewer sessions also retain read access. No export authorization policy was changed.
- Added isolated tests exercise anonymous, Admin, and Viewer requests in `local_user` mode. CSV returned 200 with `text/csv` and the UTF-8 BOM; XLSX returned 200 with the spreadsheet MIME type and opened with `openpyxl` with the expected opportunity sheet. The role matrix test took 0.57 seconds across all three roles on an empty SQLite fixture.
- The opportunity search/export fixture also passed against three test Masters and validated the XLSX workbook structure and values plus four CSV rows (header and three opportunities). No live export was repeated.
- XLSX performance is still **not accepted** for the live dataset. The prior live request exceeded 45 seconds. Code inspection found that XLSX selects all matching ORM rows, builds the workbook in memory, then serializes it to a `BytesIO`; CSV instead streams rows. This is a plausible scale-related bottleneck, but the isolated fixture is too small to establish the live cause or a safe optimization. No production export was retried and no performance fix was applied without representative isolated profiling.

### UI and one-click scripts

- Browser acceptance remains **pending**. No restricted browser session was retried. API tests do not establish role-specific UI visibility or Cloudflare external behavior.
- Static review of `Start Platform.bat`, `Open Platform.bat`, `Stop Platform.bat`, and `Restart Platform.bat` found quoted `%~dp0` paths and delegation to the shared PowerShell helpers. The helper pins the local Compose project name `alahsa-local` and uses explicit project config paths. Start performs `up -d --build`, checks migration heads/current, readiness, worker ping, and Beat startup. Stop uses Compose `stop` (which preserves named volumes); Restart invokes Stop then Start.
- Previously recorded cold-start/readiness evidence is reused. Stop and Restart were not run: they would interrupt the live installation, and the earlier authorization covered only the completed cutover. Their live end-to-end behavior remains pending separate maintenance authorization. A future check should first confirm the six services are healthy and queues idle, preserve the existing PostgreSQL/Redis volumes and Beat state, then run the selected script and verify readiness, worker, scheduler, and unchanged schema/data counts. Rollback is to use the official Start script if the clean stop succeeds but restart fails; do not use `down -v`.

### Focused test results and preservation

- A read-only project mount and temporary SQLite database were used in a disposable test container with networking disabled. `tests/test_production_security.py` and `tests/test_opportunities_search_count.py`: **19 passed, 0 failed**, 1 existing Starlette/httpx deprecation warning, 9.32 seconds. This includes anonymous/Admin/Viewer admin-route checks, session login/logout and RBAC, export file integrity, and populated opportunity export reconciliation.
- The post-cutover full DQ (**128 PASS / 6 WARNING / 0 FAIL**) and full isolated regression (**703 passed / 1 skipped / 0 failed**) remain the prior recorded results; they were not rerun because this follow-up was limited to route authorization and focused exports.
- PostgreSQL and Redis volumes, Celery scheduler/jobs/checkpoints, MasterOpportunity and SourceOpportunity identities, observations, provenance, and audit history were not changed by this follow-up. No production business-data mutation or source synchronization was performed by the agent. Natural scheduled observation activity already recorded above remains the only post-backup change.
- Files changed by this follow-up: `app/main.py`, `tests/test_production_security.py`, and this report. Existing unrelated workspace modifications were left untouched.

## Latest acceptance fields — 09:39 UTC

- `LIVE_DOCKER_REBIND`: COMPLETE; no repetition performed.
- `AUTHENTICATION`: **PARTIAL** — local_user admin guard corrected and focused tests pass, but the live API has not been restarted, so the fix is not active there.
- `AUTHENTICATED_EXPORTS`: **PARTIAL** — Admin/Viewer CSV and XLSX access and file integrity pass in isolated tests; live authenticated browser download is pending; anonymous read-only exports remain allowed by the documented loopback opportunity-view policy.
- `ROLE_SPECIFIC_UI`: **PENDING_MANUAL_VERIFICATION** — no authorized browser session used.
- `ONE_CLICK_STARTUP`: **PARTIAL** — prior cold-start evidence and static script review pass; Stop/Restart live checks await separate maintenance authorization.
- `DATA_QUALITY`: **128 PASS / 6 WARNING / 0 FAIL** (reused post-cutover full run).
- `REGRESSION`: **703 passed / 1 skipped / 0 failed** (reused post-cutover full isolated run); focused follow-up **19 passed / 0 failed**.
- `WORKSPACE_MIGRATION`: **PARTIAL**.
- `NEXT_DEVELOPMENT_READY`: **FALSE**.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: **NONE by the agent**.

### Exact remaining blockers and next action

1. Obtain separate authorization for a brief API-only rebuild/recreate from the official root, without running migration/bootstrap, stopping the scheduler, or changing PostgreSQL/Redis. Then verify anonymous `/api/admin/users` returns 401, Admin returns 200, Viewer returns 403, and readiness remains healthy. Until then the running API retains the old fail-open guard.
2. Profile XLSX on a representative isolated copy/fixture large enough to model the live row count; do not repeat the >45-second production export.
3. Complete Admin and Viewer UI checks in an authorized browser session: Dashboard, National Map, opportunity listing, filters, search, pagination, role-specific admin controls, and CSV/XLSX downloads/opening.
4. Obtain separate maintenance authorization before invoking live Stop/Restart scripts; then record successful readiness and preservation checks.

`WORKSPACE_MIGRATION` remains **PARTIAL** and `NEXT_DEVELOPMENT_READY` remains **FALSE** until these gates have adequate evidence.

## Controlled API deployment preflight — 2026-11-09 09:47 UTC

**Deployment authorization:** not granted in this request. No image was rebuilt and no live service was stopped, recreated, or restarted. `DEPLOYMENT_STATUS = AWAITING_AUTHORIZATION`.

### Pre-deployment evidence

- Official root and Compose identity were confirmed from the running API labels: project `alahsa-local`; working directory is the official root; Compose files are `docker-compose.yml` and `docker-compose.local.yml`; service/container are `api` / `alahsa-local-api-1`; configured image is `alahsa-local-api`, current image ID `sha256:5a03e2b7b0696f66a2a35c5d26bd8d1595a95de1c43ed002917dc029085aaf4a`.
- The live API has only the backup-directory bind mount at `/backups`; it has no application-code mount. The workspace file hash for `app/main.py` is `E03EAD16ABCD590998B9D9D87658CE5D2A7E8CC1A62B212E078071A85DBC79B9`, while the running image's `/app/app/main.py` hash is `807c4b9340184da23fa4f1699a2842026c39bc1a3d5770eb3f07802b4df3788c`. Runtime source inspection still has only `production` and `staging` in the protected-mode set. Live anonymous probes reconfirmed `/api/auth/me` = **401** and `/api/admin/users` = **200**. The fix is not deployed.
- All six `alahsa-local` containers are running: API, PostgreSQL, and Redis report healthy; frontend and worker return HTTP/worker checks successfully; scheduler is running. `/health/ready` and frontend `/` returned HTTP 200; Redis returned PONG; Celery worker ping returned pong. Celery `active`, `reserved`, and `scheduled` inspections were empty.
- There is exactly **one Beat scheduler in `alahsa-local`**, with a Beat log marker present. A second scheduler belongs to the separately isolated `alahsa-transfer-test` project and remains in its test mode; it was not touched.
- PostgreSQL and Redis volumes remain `alahsa-local_postgres_data` and `alahsa-local_redis_data`. PostgreSQL reported 6,678 opportunities, 9,468 source opportunities, 55,025 observations, and schema head `0025_source_geographic_coverage`. Both volume names and health were inspected; Redis responded to a read-only PING. No database writes were issued.
- The updated focused suite was rerun in a disposable container with a read-only project mount, temporary SQLite database, and networking disabled: **19 passed, 0 failed**, one existing Starlette/httpx deprecation warning, 10.50 seconds.

### Prepared API-only deployment plan (not executed)

- **Target:** Compose service `api` only. Rebuilding is required because application code is copied into the image and is not mounted into the running container. No supported hot-reload path exists.
- **Inputs:** preserve the existing project root, project name `alahsa-local`, Compose files, private `%LOCALAPPDATA%\Sharakat Data Base\.env.local`, environment variables, and secrets. Do not print or copy secret values.
- **Exact commands, after separate explicit authorization:**

  ```powershell
  $envFile = Join-Path $env:LOCALAPPDATA 'Sharakat Data Base\.env.local'
  docker image tag sha256:5a03e2b7b0696f66a2a35c5d26bd8d1595a95de1c43ed002917dc029085aaf4a alahsa-local-api:pre-auth-20261109
  docker compose --env-file $envFile -f docker-compose.yml -f docker-compose.local.yml -p alahsa-local build api
  docker compose --env-file $envFile -f docker-compose.yml -f docker-compose.local.yml -p alahsa-local up -d --no-deps --no-build --force-recreate api
  ```

- `build api` does not stop the current container. The subsequent `up` targets only `api`; `--no-deps` prevents Compose from starting/recreating the API dependencies (including `migrate`, `local-bootstrap`, PostgreSQL, Redis, worker, scheduler, and frontend), while `--no-build` prevents an implicit second build. No `down` command is used. No DB/cache volume is mounted into the API container apart from its existing backup directory. Expected interruption is one API replacement interval while the container starts and readiness recovers; the frontend may briefly receive an API error during that interval.
- **Rollback if post-deploy acceptance fails:** `docker image tag alahsa-local-api:pre-auth-20261109 alahsa-local-api`, then rerun the same Compose `up -d --no-deps --no-build --force-recreate api` command. This restores the recorded prior image for the API only. Do not remove images or volumes.
- **Acceptance after authorized execution:** confirm only the API container/image changed; `/health/ready` is 200; `/api/auth/me` anonymous is 401; `/api/admin/users` anonymous is 401, Viewer is 403, Admin is 200; repeat with approved live session identities; validate CSV/XLSX content types and file structure; record bounded XLSX duration without repeatedly exporting the full live dataset; confirm all six services, volumes, schema/data counts, Beat, and Celery queues remain healthy/unchanged. If Compose attempts migration/bootstrap or another dependency, stop before accepting that broader action and request new authorization.

### Latest deployment gate status

- `API_SECURITY_FIX`: PASS in source and focused isolated tests.
- `LIVE_API_DEPLOYMENT`: **NOT DEPLOYED — AWAITING_AUTHORIZATION**.
- `AUTHENTICATION`: PARTIAL; live anonymous admin-user access remains 200 until deployment.
- `AUTHENTICATED_EXPORTS`: PARTIAL; live Admin/Viewer sessions not exercised.
- `XLSX_PERFORMANCE`: UNRESOLVED; prior live request exceeded 45 seconds; no full export repeated.
- `ROLE_SPECIFIC_UI`: PENDING authorized browser verification.
- `ONE_CLICK_STARTUP`: PARTIAL; Stop/Restart still require separate maintenance authorization.
- `CELERY_SCHEDULER`: one `alahsa-local` Beat is running with idle inspected task states; a separate isolated test-mode Beat also exists.
- `DATA_QUALITY`: 128 PASS / 6 WARNING / 0 FAIL (reused historical full run).
- `REGRESSION`: 703 passed / 1 skipped / 0 failed (reused historical full run); latest focused run 19 passed / 0 failed.
- `WORKSPACE_MIGRATION`: PARTIAL; `NEXT_DEVELOPMENT_READY`: FALSE.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: NONE by the agent during this preflight.

**Exact next action:** obtain explicit authorization for the listed API-only image build and API-only recreation. No deployment action is authorized by this preflight request itself.

## Post-deployment acceptance — evidence through 2026-11-09 10:19 UTC

The user explicitly authorized the listed API-only build and recreation. Deployment completed using the previously recorded Compose project, root, config files, and private environment file. This section supersedes the preflight's `AWAITING_AUTHORIZATION` status.

### Deployment and runtime confirmation

- Before building, the previous API image was preserved as `alahsa-local-api:pre-auth-20261109`, image ID `sha256:5a03e2b7b0696f66a2a35c5d26bd8d1595a95de1c43ed002917dc029085aaf4a`.
- `docker compose ... build api` completed. `docker compose ... up -d --no-deps --no-build --force-recreate api` reported only `alahsa-local-api-1` as recreated and started. No dependency service, migration, or bootstrap service was started by this operation. No rollback was needed.
- The new API image is `sha256:76a87187dd5b5425344ae504a8d7aef1095116a00ae9d7cb3f90f873a11ed3c5`. Its `/app/app/main.py` SHA-256 is `e03ead16abcd590998b9d9d87658ce5d2a7e8cc1a62b212e078071a85dbc79b9`, matching the authorized workspace correction. Its `admin_auth` protected-mode set includes `local_user`.
- The standard Dockerfile build resolved newer versions within the existing dependency ranges: FastAPI 0.162.0→0.162.2, SQLAlchemy 2.1.6→2.1.8, Pydantic 2.14.1→2.14.3, and Celery 5.6.3→5.7.0. Starlette 1.10.0 and Uvicorn 0.54.0 stayed the same. The candidate image passed the focused suite and the full isolated regression below. No requirements or lock files were changed.
- The Dockerfile copies the official root's complete `app`, `scripts`, and `migrations` trees plus `alembic.ini`; only the API service was recreated, but the image therefore contains the current root source tree, not just the single `admin_auth` line change. This was the standard service build needed because the API has no code bind mount. The focused and full isolated suites passed against that image, and live opportunity/dashboard endpoints returned 200. The frontend service was not recreated; visual browser acceptance remains pending.

### Live authorization checks

- Anonymous `/api/auth/me`: **401**.
- Anonymous `/api/admin/users`: **401** after deployment (before deployment it returned 200).
- The stored local Admin credential did not establish an authenticated session in one attempt. No credential or response body was printed, and no retry was made. A post-attempt read-only check showed the Admin role was not locked and had `failed_login_count=1`; the pre-attempt count was not captured, so the attempt may have recorded a failed-login counter/audit event. No business opportunity data was affected by this authentication attempt.
- The only Viewer account observed in the local user table is disabled. No approved live Viewer session was available. Therefore live Admin-positive and Viewer-negative route/export results remain **pending**. Isolated session/RBAC tests pass, including Viewer denial and Admin permission.

### Bounded live exports and remaining XLSX performance

- One anonymous, one-opportunity filtered export was run because local read-only opportunity exports are available through the loopback-only opportunity view. CSV returned 200 (`text/csv`), 1,445 bytes, two rows including header, and matched the selected opportunity title in **28 ms**. XLSX returned 200 with the expected spreadsheet MIME type, 164,189 bytes, a valid ZIP workbook package and worksheet in **43 ms**. This was a one-row filtered measurement, not a full-dataset performance result.
- A subsequent bounded direct-API XLSX check returned 200 with attachment disposition and filename, the expected MIME type, 164,191 bytes, and both expected worksheet names; `openpyxl` opened it in **204.5 ms**. No full-dataset export was repeated.
- The prior full-dataset XLSX request exceeded 45 seconds. A later full DQ attempt (`persist=false`) invoked the same unfiltered XLSX route internally. After about four minutes, the API container reached roughly 1.4 GiB memory and high CPU while inside `export_xlsx` / per-row `_opportunity_geography` database lookups. The DQ diagnostic subprocess alone was interrupted; the API service was not stopped. This confirms the full export path remains too expensive for the requested acceptance and must not be repeated on the live dataset. No DQ run record was persisted and no business rows were changed.
- Do not claim full XLSX performance acceptance. The next investigation should profile the export on a representative isolated copy and assess batched geography-reference loading / workbook memory use before any production change.

### Health and data preservation

- Post-deploy `/health/ready`: **200**; frontend `/`: **200**; `/api/opportunities?limit=1`: **200**; `/api/dashboard`: **200**. The six `alahsa-local` services remain present and running. API, PostgreSQL, and Redis report healthy; worker ping returns pong; scheduler logs show Beat started.
- `alahsa-local_postgres_data` and `alahsa-local_redis_data` remain attached. PostgreSQL counts remain 6,678 opportunities, 9,468 source opportunities, and 55,025 observations; schema remains `0025_source_geographic_coverage`. Source count remains 14 configured / 13 enabled. Source seeding preserves `polling_frequency_minutes`; the scheduler container was not restarted.
- Celery reports one online worker with 0 active, 0 reserved, and 0 scheduled tasks. There is one Beat in `alahsa-local`; the separate test-mode Beat in `alahsa-transfer-test` remains isolated. No manual source synchronization, migration, Furas activation/removal, or schedule operation was performed.
- No production MasterOpportunity, SourceOpportunity, observation, provenance, or audit-history business data were changed by the agent. One failed login attempt may have affected authentication-only failure/audit state as described above.
- API startup invokes the existing `seed_sources` routine; its current code preserves `polling_frequency_minutes`. The source count/enabled count remain 14/13, the Beat service/container was not restarted, and no sync task ran. Source schedule execution was not changed.

### Post-deployment tests and current decision

- Candidate image focused security/export suite: **19 passed, 0 failed**, one existing Starlette/httpx deprecation warning, 10.69 seconds.
- Full isolated regression against the deployed image and temporary SQLite: **705 passed, 1 skipped, 0 failed**, 43 warnings, 66.01 seconds. The count is two higher than the prior 703 because this workspace adds two focused tests. `pytest-asyncio` was installed only in the disposable runner; the project mount was read-only.
- Fresh fast DQ on live data, `persist=false`, run ID `befdc8cefe044f748f582ef3876cd86c`: **54 gates, 54 PASS, 0 WARNING, 0 FAIL**; snapshot counts and schema are listed above. The refreshed full DQ did **not** complete because its export reconciliation triggered the expensive full XLSX path. Historical full DQ remains **128 PASS / 6 WARNING / 0 FAIL**, but it is not a new post-deployment full result.
- `API_SECURITY_FIX`: PASS; source deployed and anonymous admin denial verified live.
- `LIVE_API_DEPLOYMENT`: PASS; API-only recreation completed; the other five `alahsa-local` services were not recreated.
- `AUTHENTICATION`: PARTIAL; live anonymous checks pass, but live Admin success and Viewer denial await approved active sessions.
- `AUTHENTICATED_EXPORTS`: PARTIAL; isolated Admin/Viewer tests pass and bounded anonymous file checks pass; no live authenticated session was available.
- `XLSX_PERFORMANCE`: UNRESOLVED for the national dataset; one-record export is fast, full export path is not.
- `ROLE_SPECIFIC_UI`: PENDING authorized browser verification; no browser restriction was bypassed.
- `ONE_CLICK_STARTUP`: PARTIAL; Stop/Restart remain untested and need separate maintenance authorization.
- `CELERY_SCHEDULER`: HEALTHY; one active `alahsa-local` Beat, idle worker task states; separate isolated test-mode Beat remains.
- `DATA_QUALITY`: FAST PASS 54/54; full post-deploy DQ incomplete. Historical full DQ remains 128/6/0.
- `REGRESSION`: 705 passed / 1 skipped / 0 failed against the deployed image.
- `WORKSPACE_MIGRATION`: **PARTIAL**; `NEXT_DEVELOPMENT_READY`: **FALSE**.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: **NONE by the agent**; possible authentication-only failed-login audit/counter update from one Admin credential attempt is disclosed above.

### Exact remaining blockers and next action

1. Use a valid approved active Admin session and an approved active Viewer session to verify live user-management permissions and CSV/XLSX downloads. Do not send passwords in chat. The local Viewer account currently observed is disabled.
2. Profile and optimize full XLSX on an isolated representative dataset; do not repeat the full live export or full DQ export reconciliation until that path is bounded.
3. Complete role-specific browser checks when an authorized browser session is available.
4. Obtain separate maintenance authorization before live Stop/Restart script acceptance.

The security fix is deployed, but authentication, authenticated exports, full XLSX performance, UI, and Stop/Restart gates remain incomplete. `WORKSPACE_MIGRATION = PARTIAL`; `NEXT_DEVELOPMENT_READY = FALSE`.

## XLSX performance investigation and bounded correction — 2026-11-09

This addendum records the source-level export correction and isolated validation. It does not supersede the historical live measurements, deploy code, rerun the live full export, or alter any live service or business data.

### Baseline and safety

- Confirmed official project root: `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`.
- Read-only runtime baseline: the six `alahsa-local` services remain running; API readiness, PostgreSQL, and Redis were healthy. The current API image remains `sha256:76a87187dd5b5425344ae504a8d7aef1095116a00ae9d7cb3f90f873a11ed3c5`; the API has no application-code bind mount. Celery worker showed no active/reserved/scheduled work; Beat was not modified. Alembic head remains `0025_source_geographic_coverage`.
- No live export, restart, build, deployment, migration, data-quality export reconciliation, account modification, source sync, schedule change, or production business-data write was performed in this follow-up.
- All new profiling used disposable SQLite fixtures in Docker with networking disabled, read-only project mounts, and a 512 MiB memory cap. The full national export was not attempted.

### Root cause confirmed

- The XLSX and CSV export paths called `_opportunity_geography` once per opportunity. That function used `db.get()` for the opportunity's geography reference unit and its dataset on each iteration. With the SQLAlchemy session's weak identity-map references, the records were repeatedly fetched rather than reliably retained. An isolated 30-row diagnostic reproduced approximately one unit lookup and one dataset lookup per opportunity.
- `source_fact_summary` accessed `SourceOpportunity.opportunity_locations` without eager loading, causing one additional lazy query per source record.
- CSV formatting also accesses asset/facility assignments. The query had not eager-loaded these relationships, creating another per-opportunity lookup discovered by the new regression test.
- Independently, XLSX still materializes the selected opportunity ORM rows, builds a normal styled openpyxl workbook in memory, serializes it to `BytesIO`, and returns `getvalue()` bytes. The export therefore has meaningful workbook/response memory costs even after query batching. No streaming-workbook architecture was introduced in this correction.

### Source correction

- `app/main.py`: export the matching geography-unit IDs in a batch; batch-load those units, their parent units, and their datasets into strong-reference maps; pass those maps into `_opportunity_geography`; and eager-load source records, source locations, and asset/facility type assignments for both export paths. Export columns, filters, ordering, source/provenance content, and CSV/XLSX formats were not intentionally changed.
- `tests/test_opportunities_search_count.py`: added a populated 25-opportunity test asserting bounded SQL query counts for both endpoints, XLSX row/column counts and Arabic/source-location values, and matching CSV row/schema/location values.
- These edits are in the official workspace source only. The active API image is unchanged, so the fix is not live. Because source files are not bind-mounted, any activation requires a separately authorized API image build and API-only recreate.

### Before/after isolated measurements

The pre-fix progressive fixture (each opportunity had one linked source row/location and a shared geography unit/dataset) reproduced query growth of approximately `3N + 11`: 100 rows / 307 queries; 500 / 1,507; 1,500 / 4,511. In its 1,500-row run, database query work was 49 ms, workbook construction 2.50 s, serialization 323 ms, total 3.30 s, output 399,339 bytes, and observed RSS high-water increase 39.5 MiB.

After batching, the same style of bounded endpoint fixture returned:

| Opportunities | SQL queries | Total response time | Python allocation peak | XLSX bytes | Integrity |
|---:|---:|---:|---:|---:|---|
| 100 | 9 | 0.629 s | 5.8 MiB | 178,534 | 106 sheet rows, 32 columns, Arabic valid |
| 500 | 9 | 2.549 s | 14.59 MiB | 233,857 | 506 sheet rows, 32 columns, Arabic valid |
| 1,500 | 15 | 7.292 s | 39.23 MiB | 373,435 | 1,506 sheet rows, 32 columns, Arabic valid |
| 6,000 | 42 | 32.706 s | 149.3 MiB | 993,785 | 6,006 sheet rows, 32 columns, Arabic valid |

The 6,000-row run was in a disposable container capped at 512 MiB. Its measured process RSS high-water was 464.9 MiB; this high-water includes fixture creation and the isolated test process, so it is not an endpoint-only RSS measurement. It is close enough to the cap that scale-up stopped there. For that run, measured database query time was 19 ms, workbook construction 22.312 s, and remaining serialization/response time 10.375 s. Every workbook opened with `openpyxl`, with the expected row count, 32 columns, and Arabic sample title intact. Query count remained bounded instead of growing per row.

These fixtures validate a substantial improvement and include 6,000 of the 6,678 current opportunity rows. They do not establish full production performance: fixture text/provenance payloads are smaller and less varied than the real records; the observed memory high-water approached the imposed cap; and the live 45-second request failure was not repeated. Accordingly `XLSX_PERFORMANCE` remains `UNRESOLVED` for the full national dataset. A memory-efficient workbook/response phase may still be warranted if separately profiled with representative payload sizes.

### Tests and validation state

- Focused security/export tests after the final source correction: **20 passed, 0 failed**, 2 warnings, 9.22 seconds. This includes the added two-endpoint query-count/value-preservation regression test.
- Full isolated regression after the correction: **706 passed, 1 skipped, 0 failed**, 43 warnings, 58.93 seconds. `pytest-asyncio` was installed to `/tmp` only inside the disposable container; workspace mounted read-only. The skip still requires the separate PostgreSQL advisory-lock fixture. An initial run without the async plugin reported four unsupported async tests; that was a test-runner setup issue, and the completed plugin-enabled run is the reported regression result.
- No full DQ rerun was performed. Full DQ remains incomplete because its export reconciliation invokes the unfiltered full XLSX path. The latest prior fast DQ remains 54/54 PASS; historical full DQ remains 128 PASS / 6 WARNING / 0 FAIL and is not a new post-correction full result.
- CSV and XLSX semantics were checked against isolated fixtures. No live authenticated export was possible; the approved live Admin login remains unestablished and the observed Viewer account remains disabled.

### Updated acceptance fields

- `LIVE_DOCKER_REBIND`: COMPLETE (accepted prior stage; not repeated).
- `API_SECURITY_FIX`: PASS and previously deployed; this XLSX source correction does not alter it.
- `LIVE_API_DEPLOYMENT`: PASS for the previously authorized security correction; **the XLSX performance correction is not deployed**.
- `AUTHENTICATION`: PARTIAL; anonymous checks are corrected live, but valid active Admin/Viewer sessions are not established.
- `AUTHENTICATED_EXPORTS`: PARTIAL; isolated role/export evidence exists, but live authenticated exports remain pending.
- `XLSX_PERFORMANCE`: UNRESOLVED for full national data; N+1 query defect corrected and bounded isolated results pass, but full scale is not accepted.
- `ROLE_SPECIFIC_UI`: PENDING authorized Admin/Viewer session.
- `ONE_CLICK_STARTUP`: PARTIAL; Stop/Restart remain untested and require separate maintenance authorization.
- `CELERY_SCHEDULER`: HEALTHY at the read-only baseline; no scheduler or queue operation performed.
- `DATA_QUALITY`: latest prior fast result 54/54 PASS; full post-deployment DQ incomplete; historical full run 128 PASS / 6 WARNING / 0 FAIL.
- `REGRESSION`: 706 passed / 1 skipped / 0 failed; focused tests 20/20 passed.
- `WORKSPACE_MIGRATION`: PARTIAL.
- `NEXT_DEVELOPMENT_READY`: FALSE.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: NONE by the agent in this follow-up.

### Remaining blockers and required authorization

1. If the user wants this code fix activated, authorize a narrowly scoped API-only build and recreate from the official root. The API has no source bind mount; workspace edits alone do not change the running image. This is a new deployment authorization and is not implied by the earlier security-fix deployment authorization. No deployment was performed here.
2. After any authorized deployment, verify the API image/source hash, readiness, unchanged services/data/schema/scheduler state, and run a bounded filtered export. Do not start with unrestricted full XLSX or full DQ.
3. Keep full national XLSX performance unresolved until a safe representative memory test and authorized post-deployment acceptance prove it; avoid 6,000+ synthetic growth because the capped isolated run approached the cap.
4. Establish approved active Admin and Viewer sessions for live RBAC/export and UI verification. Do not reset passwords or activate the disabled Viewer account as part of this work.
5. Stop/Restart script checks still need separate maintenance authorization.

**Current decision:** `WORKSPACE_MIGRATION = PARTIAL`; `NEXT_DEVELOPMENT_READY = FALSE`. The N+1 source correction is isolated and regression-tested but awaits explicit API deployment authorization; full XLSX acceptance and authenticated UI/access gates remain open.

## XLSX query optimization — controlled deployment preflight — 2026-11-09

**Deployment authorization status: AWAITING_AUTHORIZATION. No deployment command, image tag, live export, service interruption, or service rebuild was performed in this preflight.** This addendum records the approval gate requested by the user and the exact candidate procedure.

### Source and output contract review

- Official root verified: `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`.
- Current workspace `app/main.py` SHA-256: `48D37F40AF69D17F3952E41B1467E00BFBECD1EA08574DF0F164DFCE2E92DDDE`. Current live `/app/app/main.py` SHA-256: `e03ead16abcd590998b9d9d87658ce5d2a7e8cc1a62b212e078071a85dbc79b9`; the live code includes the previously accepted `local_user` fail-closed admin security correction but does not include `_export_geographic_reference_cache`.
- The application diff includes the previously accepted `admin_auth` security correction, already present in the live image, plus the described export-query batching and eager-load changes. No schema, opportunity identity, source-ingestion, scheduler, or business-rule change is in the proposed correction. The new test change adds query-count and exact CSV/XLSX header/value checks.
- The XLSX contract remains 32 headers in the existing `HEADERS` order, with metadata rows 1–5, the table header on row 6, and opportunity records from row 7. Therefore a workbook with 6,006 used rows means 6,000 opportunity rows plus five title/metadata rows and one header row; the metadata tab is separate. The bounded fixture creates 6,000 unique canonical opportunity IDs/titles and returns exactly 6,006 used rows; the 25-row regression verifies the reported count, each sampled data row, metadata count, and exact header order. No output-format alteration was made.
- Focused security/export tests rerun against the final workspace source in a read-only isolated container: **20 passed, 0 failed**, one existing Starlette/httpx warning, 10.46 seconds. Full isolated regression after the app change remains **706 passed, 1 skipped, 0 failed**; the full run is documented in the prior addendum. No new code changes affecting runtime occurred after that run; the final focused rerun included the strengthened exact-schema assertions.

### Live deployment preflight

- Compose identity: `alahsa-local`; exact files: official-root `docker-compose.yml` plus `docker-compose.local.yml`; environment file is `%LOCALAPPDATA%\Sharakat Data Base\.env.local` (contents not read or printed).
- Compose service list includes `api`, `frontend`, `worker`, `scheduler`, `db`, and `redis`, plus the one-shot `migrate` and `local-bootstrap` definitions. Only the six long-running services are currently running. Frontend is the Nginx service and is not in the deployment command.
- Current API: `alahsa-local-api:latest`, image ID `sha256:76a87187dd5b5425344ae504a8d7aef1095116a00ae9d7cb3f90f873a11ed3c5`, running and healthy. Readiness returned 200. Its only host mount is the private backup directory at `/backups`; no application code is bind-mounted. Source change therefore requires a new API image.
- Current API guard check: `local_user` protection is present; live container source does not yet contain the export-cache helper. Anonymous HTTP checks remain 401 for `/api/auth/me` and `/api/admin/users` in the accepted deployed security baseline (no credentials or user state changed here).
- PostgreSQL and Redis are healthy and use `alahsa-local_postgres_data` and `alahsa-local_redis_data`. Schema head remains `0025_source_geographic_coverage`. All model tables already exist. Worker ping returned `pong`; active, reserved, and scheduled task inspections were empty; source-sync, maintenance, notifications, and default broker queue depths were all zero at inspection. Database `SyncJob` states showed **0 active queued/running/retrying jobs**. There is one running `alahsa-local` Beat scheduler, with recent due-task logs; its scheduler container and checkpoint are outside the API-only action.
- The API lifespan in `local_user` calls `init_db()` and `seed_sources()`. Read-only preflight found zero missing model tables, zero default-source field differences for the fields seed updates, zero missing default organization aliases, and the configured bootstrap Admin identity already exists (identity not disclosed). Thus those existing startup routines are expected to be no-op for schema/source defaults/account creation; the Compose command below does not start the `migrate` or `local-bootstrap` services. The previously accepted runtime behavior that startup invokes source seeding is disclosed rather than hidden.
- No Docker image tag has been created yet. If authorized, current rollback image will first be retained as `alahsa-local-api:pre-xlsx-query-20261109`.

### Exact proposed API-only deployment and rollback

PowerShell variable for the existing private Compose environment file:

```powershell
$envPath = Join-Path $env:LOCALAPPDATA 'Sharakat Data Base\.env.local'
```

Only after explicit authorization, proposed steps:

```powershell
docker image tag alahsa-local-api:latest alahsa-local-api:pre-xlsx-query-20261109
docker compose --env-file $envPath -f docker-compose.yml -f docker-compose.local.yml -p alahsa-local build api
docker compose --env-file $envPath -f docker-compose.yml -f docker-compose.local.yml -p alahsa-local up -d --no-deps --no-build --force-recreate api
```

Expected interruption: the API container is replaced once. API-backed requests can fail briefly during that recreate; the frontend/Nginx, PostgreSQL, Redis, Worker, and Beat are not stopped or recreated. `--no-deps` and the explicit `api` target prevent Compose from starting dependencies; the separate `migrate` and `local-bootstrap` services are not invoked. No database volume or schedule/checkpoint is removed. Build time is before the interruption; recreate duration depends on startup/readiness.

If post-deploy acceptance fails, rollback without deleting images or volumes:

```powershell
docker image tag alahsa-local-api:pre-xlsx-query-20261109 alahsa-local-api:latest
docker compose --env-file $envPath -f docker-compose.yml -f docker-compose.local.yml -p alahsa-local up -d --no-deps --no-build --force-recreate api
```

Acceptance would verify only the API container/image changed; readiness; deployed export helper and retained security guard; anonymous auth/admin 401; opportunity, dashboard, geography/filter/search/pagination endpoints; and bounded filtered CSV/XLSX schema, values, integrity, and duration. It would not run an unrestricted national export or full DQ. Full national XLSX would remain unresolved.

### Memory-generation assessment

- Current writer uses a normal `openpyxl.Workbook`, all ORM opportunity rows are materialized, 32 styled cells are created for every opportunity, output is serialized to `BytesIO`, and `getvalue()` returns a further bytes object. The 6,000-row isolated process high-water reached 464.9 MiB under a 512 MiB cap (the high-water includes fixture construction); this is not an endpoint-only RSS figure, but the margin was insufficient to safely grow the fixture. Keep the full national-memory gate unresolved.
- `openpyxl` write-only mode is a viable separate experiment: its documented append-only model supports styled `WriteOnlyCell`s and near-constant writer memory, but it cannot read/write arbitrary cells after rows are appended and must be saved once. The current report title/metadata rows and second metadata sheet would need to be emitted in order before the opportunity rows, while preserving the logo, styles, print/freeze settings, formulas/formatting, and filter semantics. No write-only conversion was included in this patch. [openpyxl optimized modes](https://openpyxl.readthedocs.io/en/stable/optimized.html)
- A temp-file-backed response is also feasible to investigate: Starlette `FileResponse` streams a file; a response background task can remove the uniquely created temp file after transmission. This can eliminate the final full response-byte copy, but it does not by itself remove normal-workbook cell memory. Creation permissions, unique naming, failure cleanup, disconnect behavior, and cross-platform temp cleanup need isolated validation. [Starlette responses](https://www.starlette.io/responses/), [Starlette background tasks](https://www.starlette.io/background/)
- Recommendation: treat lower-memory workbook writing plus bounded database iteration and temp-file delivery as a separately scoped optimization only if a representative payload-size profile still shows unsafe memory after this query fix is deployed. Preserve all rows/columns; never truncate.

### Current decision and explicit authorization gate

- `XLSX_QUERY_OPTIMIZATION`: ISOLATED_PASS; bounded query growth and 20 focused tests pass.
- `XLSX_QUERY_OPTIMIZATION_DEPLOYMENT`: **AWAITING_AUTHORIZATION**; current live image remains unchanged.
- `BOUNDED_LIVE_XLSX`: NOT RUN; cannot be run until deployment authorization is granted and the new helper is live. Then perform only a small filtered request.
- `FULL_DATASET_XLSX`: UNRESOLVED; no unrestricted live attempt.
- `XLSX_PERFORMANCE`: UNRESOLVED for national data because workbook and response remain memory-buffered and the capped fixture approached its limit.
- Existing authentication, authenticated export, role UI, Stop/Restart, full DQ, and workspace acceptance blockers remain as recorded in the preceding addendum.

No authorization is inferred from this preflight request. **Await explicit approval for the specific `api` build and single `api` recreate described above, including the brief API request interruption.** On approval, execute only those steps and then the listed bounded acceptance checks.

### Additional read-only preflight endpoint check

- Immediately before the authorization gate, localhost returned `/api/auth/me` **401**, `/api/admin/users` **401**, `/api/opportunities?limit=1` **200**, `/api/dashboard` **200**, and `/api/filters` **200**. No credentials, sessions, or account state were changed.
- The deployment request gate remains `AWAITING_AUTHORIZATION`; these checks do not exercise the new export code in the live container.

## Authorized XLSX optimization deployment and bounded acceptance — 2026-11-09 11:12 UTC

The user explicitly authorized preserving the old API image, building the API image from the official root, and force-recreating only `api` with `--no-deps`. This section supersedes the preceding `AWAITING_AUTHORIZATION` state. No broader service action was taken.

### Deployment result

- Saved rollback tag `alahsa-local-api:pre-xlsx-query-20261109` points to prior image `sha256:76a87187dd5b5425344ae504a8d7aef1095116a00ae9d7cb3f90f873a11ed3c5`.
- Built only Compose service `api`; no dependency service was built or started. BuildKit reused the requirements layer and copied the workspace app into the candidate image.
- Candidate/current API image: `sha256:86bbebce51e4a4714e2bbb8f2c134d0c58ca4d71d64f8ba307a8face174f0a57`. Its `/app/app/main.py` SHA-256 is `48d37f40af69d17f3952e41b1467e00bfbecd1ea08574df0f164dfce2e92ddde`, matching the verified workspace source. Runtime inspection confirms `_export_geographic_reference_cache` is present and the `local_user` security guard remains present.
- Compose reported only `alahsa-local-api-1` as recreated and started. It is running and healthy; `/health/ready` returned 200. All other five long-running service container IDs and start times are unchanged. PostgreSQL and Redis named volumes remain `alahsa-local_postgres_data` and `alahsa-local_redis_data`. The Worker and the single Beat scheduler were not recreated; no migration or `local-bootstrap` container was started. API restart count is 0 after successful start; `OOMKilled=false`.
- The old image remains available for rollback. If needed, restore `alahsa-local-api:latest` from `alahsa-local-api:pre-xlsx-query-20261109` and run the same official-root Compose `up -d --no-deps --no-build --force-recreate api` command. No volume or data rollback is indicated or authorized.

### Post-deployment runtime and data verification

- Current anonymous `/api/auth/me`: **401**; `/api/admin/users`: **401**.
- `/api/opportunities?limit=1`, `/api/dashboard`, `/api/filters`, `/api/geography/catalog`, and `/api/geography/filter-options`: **200**. Search returned the selected opportunity; pagination returned a different second-page ID.
- PostgreSQL and Redis remained healthy. Alembic head is still `0025_source_geographic_coverage`. Current counts: 6,678 opportunities, 9,468 source opportunities, 55,054 observations; active queued/running/retrying sync jobs: 0. Worker ping: `pong`; active, reserved, and scheduled task inspections were empty. Broker queue depths were 0 at deployment preflight.
- Observation count is 29 higher than the earlier 55,025 snapshot. The most recent successful scheduled source job completed at 10:30 UTC, before this 11:09 UTC API recreate, with zero new Masters; the scheduler remained running. No manual source synchronization was invoked. The agent did not mutate business data. The existing scheduled job is the source of the observation delta, consistent with prior natural scheduler activity.
- Preflight confirmed all model tables exist, no seed-managed source fields differed, no default aliases were missing, and the configured bootstrap Admin identity already existed. API startup's existing `init_db()` and `seed_sources()` calls therefore had no detected missing-table/source-default/bootstrap work. No schema migration ran.

### Bounded live export acceptance

One selected current opportunity was exported using its filtered `map_ids` value. No unrestricted national export was run.

- CSV: HTTP **200**, `text/csv; charset=utf-8`, 1,445 bytes, 2 rows (header plus one opportunity), 32 columns, 30 ms. Title matched the selected opportunity.
- XLSX: HTTP **200**, correct spreadsheet MIME type, 164,189 bytes, 42 ms. `openpyxl` opened it successfully; the opportunity sheet had 7 used rows (five title/metadata rows, the row-6 header, and one opportunity on row 7), exactly 32 columns, headers matched the established `HEADERS` list, metadata reported one opportunity, Arabic text was present, and the selected title matched the CSV. The filter returned exactly the selected opportunity.
- Live memory was not sampled during the 42 ms request. A post-check Docker snapshot showed API memory at 239 MiB / 7.496 GiB with 0.15% CPU; this idle snapshot is not an export peak measurement.
- `BOUNDED_LIVE_XLSX = PASS`. This does not establish full-national XLSX performance.

### Validation and remaining gates

- Focused isolated tests on the final workspace source: **20 passed, 0 failed**, 1 existing warning, 10.46 seconds. The exact CSV header list, XLSX `HEADERS` order, report count, row values, Arabic locations, and bounded query counts are covered.
- Full isolated regression: **706 passed, 1 skipped, 0 failed**, 43 warnings, 58.93 seconds (previous addendum). The skip requires a separate PostgreSQL advisory-lock test fixture. No new DQ run was performed; latest fast DQ remains 54/54 PASS, full post-deployment DQ remains incomplete, and historical full DQ remains 128 PASS / 6 WARNING / 0 FAIL.
- Full dataset XLSX remains unresolved: the workbook is still built in normal in-memory mode and buffered through `BytesIO`; the prior capped 6,000-row process high-water reached 464.9 MiB. Do not run an unrestricted live export or the full DQ export reconciliation. A write-only workbook plus bounded row iteration and temp-file-backed `FileResponse` remains a separately scoped memory optimization requiring isolated compatibility, cleanup, and realistic-payload profiling.
- Admin positive authentication is still unavailable; the observed Viewer account remains disabled. No login retry, account change, or credential handling occurred. Live authenticated exports and role-specific UI checks remain pending approved active Admin and Viewer sessions. The account owner/admin should restore or confirm the existing Admin through the supported account recovery process and activate the existing Viewer through the supported user-management process; credentials should be entered by the user in the authorized app session, not shared in chat. Then verify `/api/auth/me`, Admin `/api/admin/users` 200, Viewer `/api/admin/users` 403, permitted views/exports, and hidden/denied admin controls. Do not reset or enable accounts through this task.
- Stop/Restart script tests remain unrun and require separate maintenance authorization. Existing national Dashboard/Map/Geography acceptance remains accepted; API smoke checks above did not reopen those gates.

### Final acceptance fields

- `LIVE_DOCKER_REBIND`: COMPLETE.
- `API_SECURITY_FIX`: PASS; retained in deployed image.
- `XLSX_QUERY_OPTIMIZATION`: PASS; isolated query batching validated and deployed.
- `XLSX_QUERY_OPTIMIZATION_DEPLOYMENT`: PASS; API-only build/recreate completed.
- `AUTHENTICATION`: PARTIAL; anonymous denial passes; live Admin/Viewer session verification pending.
- `AUTHENTICATED_EXPORTS`: PARTIAL; bounded anonymous filtered export passes; authenticated role-specific exports pending.
- `BOUNDED_LIVE_XLSX`: PASS; one filtered row, valid workbook, correct schema and data.
- `FULL_DATASET_XLSX`: UNRESOLVED.
- `XLSX_PERFORMANCE`: UNRESOLVED for national scale due memory-buffered workbook and capped isolated RSS margin.
- `ROLE_SPECIFIC_UI`: PENDING authorized Admin/Viewer verification.
- `ONE_CLICK_STARTUP`: PARTIAL; Stop/Restart still untested.
- `CELERY_SCHEDULER`: HEALTHY; one Beat, worker responsive and idle at checks, scheduler and checkpoint not recreated.
- `DATA_QUALITY`: latest fast DQ 54/54 PASS; full post-deployment DQ incomplete; historical full result 128 PASS / 6 WARNING / 0 FAIL.
- `REGRESSION`: 706 passed / 1 skipped / 0 failed; final focused tests 20 passed / 0 failed.
- `WORKSPACE_MIGRATION`: PARTIAL.
- `NEXT_DEVELOPMENT_READY`: FALSE.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: NONE by the agent. A natural scheduled job added observations before deployment, with zero new Masters; disclosed above.

**Decision:** the query optimization is deployed and the bounded live export passes. Workspace acceptance remains **PARTIAL** because full national XLSX memory/performance, live authenticated Admin/Viewer exports and UI, full DQ, and Stop/Restart acceptance remain open.

## Low-memory XLSX engineering and isolated acceptance — 2026-11-09

This addendum evaluates the write-only workbook and file-backed response in the official workspace. It does not deploy or restart the API, run a live export, change the database, synchronize a source, or alter scheduler state.

### Root cause and selected design

- After the previously accepted query batching, XLSX still materialized all matching ORM records, built a normal `openpyxl.Workbook`, serialized it to `BytesIO`, and copied the result with `getvalue()`. The 6,000-row historical baseline took **32.706 s**, used **149.3 MiB** of Python allocation peak, and reached **464.9 MiB process RSS high-water** under a 512 MiB cap. That RSS high-water included fixture construction, so it is not an export-only number.
- The isolated runtime contains `openpyxl 3.1.5` and `Starlette 1.10.0`; dependencies and requirements were not changed. The chosen design is openpyxl write-only `WriteOnlyCell` output, SQLAlchemy `yield_per=500` / 500-row partitions, a unique private temporary request directory, and a streaming Starlette `FileResponse`. This preserves append-only workbook generation while avoiding the complete workbook and response byte buffers. The writer still creates row dimensions for established row-height formatting, so memory is measured rather than assumed constant. [openpyxl optimized modes](https://openpyxl.readthedocs.io/en/stable/optimized.html), [Starlette responses](https://www.starlette.io/responses/)
- The PostgreSQL XLSX read uses a read-only repeatable-read transaction so the count displayed in metadata and the streamed rows share a database snapshot. SQLite regression fixtures continue to use their normal isolated transaction behavior.

### Workbook contract and compatibility

- The established order remains `الفرص الاستثمارية`, then `معلومات التقرير`. The opportunity sheet has exactly **32 established Arabic headers** in `HEADERS` order, title and metadata rows 1–5, header row 6, and opportunities beginning at row 7. Therefore 6,000 opportunities occupy **6,006 used rows**. The metadata sheet keeps its 17-row layout and `B8` opportunity count.
- Automated reference comparison builds the same two-record workbook through the old normal writer and the optimized writer, then compares every cell value, type, format, font, fill, alignment, hyperlink, row height, column width, sheet settings, print settings, images, conditional-formatting ranges and formulas, and merged-cell state. It passes. Empty exports, unknown/invalid dates, formula-injection escaping, and text treatment also pass.
- The 6,000-row performance workbook reopened successfully with two expected sheet names, 32 columns, 6,006 used rows, metadata count 6,000, the exact 6,000 expected synthetic titles in order, no missing or duplicate titles, Arabic text, and all streamed bytes received. The 6,000-row data is synthetic and is not a substitute for acceptance against the full national dataset.
- CSV behavior and filters were not changed. Isolated export reconciliation tests cover selected filters, CSV/XLSX headers and values, source/location fields, taxonomy, deadline, and geographic subsets. Visual inspection in Excel was not performed; any manual Excel rendering check remains pending.

### Same-fixture performance and resource comparison

Both paths used the same deterministic disposable SQLite fixture at each size: unique synthetic opportunities, one source record and source location per opportunity, and a shared geographic-reference hierarchy. Runs used Docker with networking disabled, a read-only project mount, SQLite under `/tmp`, and hard 512 MiB memory and swap limits. The normal path used the existing workbook builder plus `BytesIO`/`getvalue`; the optimized path used the production endpoint function and streamed `FileResponse` into a discard sink. Memory deltas are process RSS above the post-seed baseline; cgroup current-memory values are sampled maxima, not kernel high-water counters.

| Opportunities | Main rows | Baseline queries | Baseline seconds | Baseline RSS delta | Optimized queries | Optimized seconds | Optimized RSS delta | XLSX bytes (optimized) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7 | 10 | 0.0569 | 0.41 MiB | 11 | 0.0772 | 1.34 MiB | 164,011 |
| 100 | 106 | 10 | 0.1994 | 1.41 MiB | 11 | 0.2483 | 1.88 MiB | 178,592 |
| 1,000 | 1,006 | 13 | 1.6192 | 18.68 MiB | 20 | 1.8772 | 6.70 MiB | 304,069 |
| 3,000 | 3,006 | 25 | 4.9756 | 52.82 MiB | 56 | 5.8510 | 3.39 MiB | 579,944 |
| 6,000 | 6,006 | 43 | 10.2024 | 89.13 MiB | 110 | 10.5889 | 9.09 MiB | 993,202 |

- At 6,000 rows, the optimized path is **3.8% slower** end to end in this paired untraced run, while reducing sampled process RSS growth by **89.8%** (89.13 MiB to 9.09 MiB). The endpoint’s observed absolute process RSS peak was 124.84 MiB after a 115.75 MiB post-seed baseline; sampled cgroup current reached 126.50 MiB under the 512 MiB cap. Database execution was 0.0189 s across 110 batched queries. The baseline’s process RSS peak was 269.36 MiB after a 180.22 MiB baseline; sampled cgroup current reached 264.62 MiB. The different process starting RSS is why the endpoint RSS delta, rather than the two absolute peaks, is the primary comparison.
- A separate allocation-tracing run measured a **17.44 MiB Python allocation peak** for 6,000 rows. Tracemalloc raised the run time to 35.90 s, so that timing is excluded from the A/B comparison. The 6,000-row temporary-directory peak was **17,965,304 bytes** (about 17.1 MiB), including worksheet XML scratch and final XLSX. The final file was 993,202 bytes; `FileResponse` streamed all 993,202 bytes.
- Query count is higher in write-only mode because source-review, location, and geography lookups repeat once per 500-row partition. It is bounded by batch count (110 queries for 6,000 rows), not per opportunity. No N+1 query behavior was observed. Query count and SQL execution time are in the benchmark evidence file.
- Exact results and benchmark scripts: [benchmark JSON](low-memory-xlsx-benchmark-20261109.json), [optimized runner](../../../../scripts/benchmark_low_memory_xlsx.py), [normal-writer reference runner](../../../../scripts/benchmark_normal_xlsx_reference.py).

### Temporary-file, failure, and authorization checks

- Exports use `%TEMP%` / the container system temp root, outside OneDrive. The application root and per-request unpredictable directories are owner-only (`0700`); output files are created exclusively with owner-only permissions. No route accepts or exposes a filesystem path. The single Uvicorn process permits one concurrent XLSX export and returns HTTP 429 with `Retry-After: 30` for another request.
- Storage checks require at least 16 MiB free, estimate 16 KiB per opportunity up to the 128 MiB cap, and reject final files exceeding 128 MiB with a safe 507 response. Stale request directories older than 24 hours are removed at the next export attempt. Openpyxl worksheet XML scratch files are kept in that same private request directory. A process termination can leave that directory behind; the next export removes it once stale, and normal process shutdown also invokes openpyxl cleanup.
- Success, generation failure, write-cap rejection, insufficient-disk rejection, busy-slot rejection, repeated cleanup, client-send failure/disconnect, unique directories, restrictive permissions, and stale-directory cleanup have focused tests. The descriptor closes on pre-response failure. File cleanup and slot release execute from both the background callback and response `finally`, idempotently.
- The DQ reconciliation helper calls the route directly instead of sending an ASGI response. It now opens the response file path and explicitly cleans the response afterward; this prevents a direct internal caller from retaining the file or export slot. Production authentication/RBAC policy and the security dependency were not changed. Local role/export fixture checks pass; live authenticated Admin/Viewer downloads remain unverified.

### Validation results

- Focused XLSX/storage/security/export/geography/taxonomy/deadline tests: **101 passed, 1 skipped, 0 failed**, 1 warning, 17.21 s. The skip requires the isolated PostgreSQL advisory-lock fixture.
- Dedicated `tests/test_data_quality.py`: **39 passed, 0 failed**, 36 existing Alembic configuration deprecation warnings, 15.67 s.
- Final complete isolated regression on the final source: **715 passed, 1 skipped, 0 failed**, 43 warnings, 80.49 s. `pytest-asyncio` was installed only under `/tmp` in the disposable runner; the project mount was read-only. No live PostgreSQL, source sync, or account was used.
- Fast live read-only DQ remains the previously accepted **54/54 PASS** result. No new live DQ was run. Full post-deployment DQ remains incomplete; the report’s historical full result is 128 PASS / 6 WARNING / 0 FAIL. Full DQ against the complete national snapshot is not accepted by a synthetic 6,000-row benchmark.
- `git diff --check` for the files changed by this optimization passed. A repository-wide diff check also encounters pre-existing overlong paths under deleted portable-package screenshot folders; those paths are unrelated to this work.

### Changed files, deployment, and remaining gates

- Runtime and integration: `app/excel_export.py`, new `app/export_storage.py`, `app/main.py`, and `app/data_quality.py`.
- Tests and reproducibility: `tests/test_excel_presentation.py`, `tests/test_export_storage.py`, `tests/test_opportunities_search_count.py`, `scripts/benchmark_low_memory_xlsx.py`, `scripts/benchmark_normal_xlsx_reference.py`, and the benchmark JSON above. No requirements or dependency file changed.
- No API image was built or recreated for this change. The previous recorded live API image remains `sha256:86bbebce51e4a4714e2bbb8f2c134d0c58ca4d71d64f8ba307a8face174f0a57`; this turn did not re-inspect or alter the running services. The API Dockerfile copies `app/`; there is no dependency change. For a future controlled API-only deployment, first tag the then-current live image as rollback, build only `api`, and recreate only `api`; verify the actual container memory and writable temp-space limits before activation. No deployment command is authorized by this task.
- Isolated 6,000-row performance is accepted for the synthetic fixture, but **full-national XLSX remains unresolved**: the current national snapshot has 6,678 opportunities, and the exact dataset and its payload variety were not exported or validated here. A safe isolated full-snapshot/representative-payload run should precede any deployment. No truncation or data-shape change was made.
- Workspace-wide blockers remain: live Admin/Viewer authentication and authenticated exports; role-specific UI verification; full post-deployment DQ; complete national XLSX acceptance; and authorized Stop/Restart checks. These were not reopened or changed.

### Latest status fields

- `LOW_MEMORY_XLSX_IMPLEMENTATION`: **PASS** — incremental writer and file-backed delivery implemented and benchmarked.
- `ISOLATED_WORKBOOK_COMPATIBILITY`: **PASS** — automated contract comparison against the normal workbook builder.
- `ISOLATED_XLSX_PERFORMANCE`: **PASS WITH TRADEOFF** — 6,000 rows, 10.59 s, 3.8% slower than the paired normal writer, with 89.8% lower measured endpoint RSS growth.
- `ISOLATED_RESOURCE_SAFETY`: **PASS** — 512 MiB cap; 6,000 rows peaked at 126.50 MiB sampled cgroup current and 17.1 MiB temp disk; failure/lifecycle tests pass.
- `ISOLATED_FULL_SCALE_VALIDATION`: **PARTIAL** — 6,000 synthetic rows; the full 6,678-row national dataset remains unverified.
- `LIVE_XLSX_DEPLOYMENT`: **PENDING / NOT PERFORMED**.
- `FULL_DATASET_XLSX`: **UNRESOLVED**.
- `AUTHENTICATION`: **PARTIAL**; `AUTHENTICATED_EXPORTS`: **PARTIAL**; `ROLE_SPECIFIC_UI`: **PENDING**.
- `ONE_CLICK_STARTUP`: **PARTIAL**; Stop/Restart checks remain pending separate maintenance authorization.
- `DATA_QUALITY`: latest fast read-only **54/54 PASS**; full live DQ **INCOMPLETE**.
- `REGRESSION`: **715 passed / 1 skipped / 0 failed**.
- `WORKSPACE_MIGRATION`: **PARTIAL**; `NEXT_DEVELOPMENT_READY`: **FALSE**.
- `PRODUCTION_BUSINESS_DATA_MUTATIONS`: **NONE** by the agent in this task.

**Current decision:** the low-memory implementation and 6,000-row isolated performance/resource gates pass. It is **not yet ready for a controlled deployment** until full-national isolated acceptance is completed. Live deployment, authentication, UI, full DQ, and startup acceptance remain pending. No production service or data was changed.

## Final workspace relocation verification and national-development handoff — 2026-11-09 12:36 UTC

This short check separates the accepted physical workspace relocation from the broader operational backlog. It used read-only Docker inspection, existing API routes, Redis PING, Celery worker ping, and scheduler logs. No container was rebuilt or restarted; no batch script, export, migration, DQ run, sync, or account action was performed.

### Relocation verification

- All six long-running `alahsa-local` containers are running. Their `com.docker.compose.project.working_dir` labels all point to `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`.
- The only active host bind mounts are the API and Worker backup mounts under `%LOCALAPPDATA%\Sharakat Data Base\backups`. There are no application source-code bind mounts and no active bind mount to the previous `C:\Sharakat Data Base` folder. Frontend and scheduler have no host binds. PostgreSQL and Redis remain attached to `alahsa-local_postgres_data` and `alahsa-local_redis_data`.
- Docker health checks report API, PostgreSQL, and Redis **healthy**. Frontend root returned HTTP 200. `/health/ready` returned `{"status":"ready","checks":{"database":"ok","redis":"ok","worker":"ok"}}`.
- `/api/opportunities?limit=1` returned one item and total **6,657 current opportunities**. `/api/dashboard` returned total **6,657** and **6,507 active**. `/api/data-dashboard/geography-summary` returned **6,657** unique Masters, **13 regions**, and **149 governorates**. `/api/data-dashboard/geography` returned `map_scope=NATIONAL`, total **6,657**, **5,889** mapped records and **5,847** map points using `taadeen-public-gis-20261102-v3`.
- Redis answered authenticated `PING` with **PONG**. Celery `inspect ping` returned **pong** from one worker node. The single scheduler container is running and its recent logs show periodic due-task dispatches and worker-heartbeat scheduling. Compose does not define Docker health checks for frontend, Worker, or scheduler; their HTTP, Celery, and scheduler-log checks above provide their current operational evidence.
- Existing cold-start/readiness and `Platform Status.bat` evidence remains valid from the Startup Scripts section above. Stop/Restart scripts were not invoked and remain separately unverified.
- No relocation-specific failure was found. PostgreSQL and Redis volumes were preserved, and the current database is readable through the API.

### Closure boundary and separate backlog

- `WORKSPACE_RELOCATION = ACCEPTED_AND_CLOSED`.
- `LIVE_DOCKER_REBIND = ACCEPTED_AND_CLOSED`.
- `WORKSPACE_MIGRATION = PARTIAL` remains the broader acceptance result. It still includes live Admin/Viewer authentication and exports, role-specific UI, full post-deployment DQ, full-national XLSX acceptance/deployment, and Stop/Restart maintenance verification. Those unrelated pending checks do not reverse the successful physical relocation.
- No change was made to the source-only low-memory XLSX implementation; it remains undeployed. National UI, Dashboard, Map, and Geography acceptance remain unchanged.
- `READ_ONLY_NATIONAL_DEVELOPMENT_READY = TRUE`; the new workspace is available for non-disruptive development. `NEXT_DEVELOPMENT_READY` for the broader production acceptance definition remains **FALSE** until its listed gates are complete.

### National source scheduling handoff — Furas identity reconciliation

`NATIONAL_SOURCE_SCHEDULING = PARTIAL`. The next development task is a **read-only, isolated identity-crosswalk replay/contract test** using the durable 2026-11-05 capture and its retained record-level adjudication. It should verify deterministic membership, source-key exact matches, one-to-one identity candidates, and idempotent classification while making zero production changes. Keep the capture populations separate:

- Original population: **6,511** provider records; aggregate exact matches **5,870** and **641** unmatched. The exact 641 record IDs/payloads were not retained and cannot be reconstructed from the stored membership digest. This population must not be replaced by the later capture.
- Later durable population: **6,548** unique provider IDs; against the current 6,546 Furas source rows, **5,870** exact source-key matches, **678** capture-only IDs, and **676** current-source-only IDs. No absence is interpreted as removal or expiration.
- Of the later 678 unmatched IDs, **346** share OBJECTID and exact title with a current source row. The latest adjudication identifies **75** evidence-backed existing-identity alias proposals and **603** records that must remain review-required/source-only. The 75 mappings are proposals pending governance approval; they have not been applied.

The replay should assert these exact separate populations, retain the raw provider IDs, permit only the 75 proposed mappings as dry-run outcomes, and leave all 603 unresolved records unpromoted. Before acceptance-baseline closure, recover the original 6,511/641 member artifact from its operator/archive or obtain an explicit baseline amendment. Do not apply aliases without governed approval. Furas national enumeration, scheduling activation, removals, ingestion, merging, and production pilots remain disabled/not authorized.

Evidence used: [workspace acceptance and historical startup checks](WORKSPACE-POST-CUTOVER-ACCEPTANCE-20261109.md), [Furas reconciliation](../nationwide-source-expansion/FURAS-641-IDENTITY-RECONCILIATION-20261105.md), [678-record adjudication](../nationwide-source-expansion/FURAS-678-IDENTITY-ADJUDICATION-20261105.json), and [latest national scheduling readiness](../nationwide-source-expansion/NATIONAL-SOURCE-SCHEDULING-READINESS-UPDATE-20261105-v2.md).
