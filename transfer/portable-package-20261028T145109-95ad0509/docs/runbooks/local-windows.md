# Local Windows platform

## Architecture

The end-user workstation runs the same PostgreSQL, Redis, FastAPI, static frontend, Celery worker, and Celery Beat services as the production reference through Docker Desktop Compose. All services and storage stay on the local computer. Only the frontend is published, bound to `127.0.0.1:8080`; PostgreSQL and Redis have no host-published ports. The local Compose project is `alahsa-local`.

PostgreSQL and Redis use persistent named volumes (`alahsa-local_postgres_data`, `alahsa-local_redis_data`). Backups are bind-mounted to the project `backups/` directory. `Stop Platform.bat` runs `docker compose stop`; it never removes containers or volumes. Docker Desktop's VM disk holds named volumes, so include Docker Desktop's disk data in the workstation backup plan.

## Start and stop

First time only, double-click `Install Platform Requirements.bat`. It writes a non-secret host diagnostic to `logs/local-requirements-diagnostic.log`, verifies the official Docker Desktop WinGet package, prepares WSL2 (without installing a Linux distribution), and asks for a normal Windows restart when required. After restart, run the installer again; it resumes Docker installation and launches `Start Platform.bat`. Every normal day, double-click `Start Platform.bat`. The PowerShell launcher checks required files, Docker CLI/Compose and Engine, protects local settings, checks port 8080, builds/starts the stack, checks the migration, API/database/Redis/worker health, Beat startup, and frontend response, then opens `http://localhost:8080`. A second click is idempotent and opens the existing healthy platform. Startup details go to `logs/startup.log`.

Double-click `Stop Platform.bat` for a clean Compose stop. It preserves PostgreSQL/Redis volumes and backups. `Restart Platform.bat`, `Platform Status.bat`, and `Create Desktop Shortcuts.bat` are convenience launchers. The shortcut launcher creates Start, Stop, and Status shortcuts on the Windows desktop.

If Docker Desktop is installed but stopped, Start attempts to launch it and waits up to ten minutes for Docker Engine. The first-run installer waits up to fifteen minutes during the initial Docker Engine boot and stops if first-run Docker prompts need attention. No source sync is manually triggered by Start. Celery Beat retains the configured source schedules. Nginx resolves the API service through Docker's embedded DNS so an Engine restart that changes the API container IP does not leave a stale upstream address.

## First run and existing data

The launcher generates `.env.local` with local-only PostgreSQL, Redis, and session credentials; the file is ignored by Git and its Windows ACL is restricted to the current user. A protected copy is kept in `%LOCALAPPDATA%\Sharakat Data Base` so losing the project copy does not silently rotate credentials for an existing database volume. If both copies are missing while the Postgres volume exists, startup stops and does not generate replacements.

The one-shot `local-bootstrap` service runs after Alembic. It requires the target database name to be exactly `sharakat_local`, requires an empty target without an import marker, makes a verified SQLite safety backup under `backups/`, then transactionally imports the source tables from `data/al-ahsa-live.db`, preserving IDs, relationships, JSON, timestamps, job state, and row counts. It advances PostgreSQL sequences and creates a local Admin only if the imported database has no users. Existing users are preserved. The source SQLite file is mounted read-only and never modified. A persisted marker prevents repeat imports. If a partial or non-empty unmarked Postgres database is found, setup refuses to merge or overwrite it.

The current SQLite source was inspected read-only and backed up before setup. Its verified safety copy is [al-ahsa-live.db](../../backups/pre-local-postgres-20261013-101428/al-ahsa-live.db), 55,570,432 bytes, SHA-256 `3e4e99782c8fe7b5368b9dc0c6afdb9e75ab48ebd785a69e4678d7f5953b0364`. It contains 230 opportunities, 2,831 source rows, 7,603 source observations, 10 sources, 200 sync jobs, and no existing users. The manifest records counts and SQLite `integrity_check=ok`.

For the first Admin login, the launcher creates `Local Admin Credentials.txt` with a random local-only password. Keep this file private. Login remains enabled; the launcher does not bypass authentication.

The credential file is an initial-bootstrap artifact, not a live password store. It can become stale after a controlled password reset. The current local account is `admin@local`; use the credential delivered through the approved operator channel. Never put a temporary password in this runbook, reports, or source control.

Open `http://localhost:8080`; if signed out, use the user button in the upper toolbar, then enter the existing account credentials in the login dialog. Select the signed-in user button to open **الحساب الشخصي**, then select **تغيير كلمة المرور** to rotate that account's password:

1. سجّل الدخول إلى المنصة.
2. افتح **الحساب الشخصي** من زر المستخدم في الشريط العلوي.
3. اختر **تغيير كلمة المرور**.
4. أدخل كلمة المرور الحالية.
5. أدخل كلمة المرور الجديدة (12 محرفًا على الأقل، وبحد أقصى 256 محرفًا).
6. أكّد كلمة المرور الجديدة.
7. اختر **حفظ كلمة المرور الجديدة**.

Use **تسجيل الخروج** from the same account menu when finished. A successful change verifies the current password on the server, writes only the existing scrypt password hash, records a `PASSWORD_CHANGED` audit event without credential material, rotates the current session cookie, and revokes other sessions for that user. The password endpoint uses the existing eight-attempt/five-minute Redis-backed throttle and the account lockout policy. CSRF protections remain the existing JSON-only request path, exact-origin CORS allow-list, and HTTP-only SameSite=Lax session cookie. Sessions use a server-side token and expire after eight hours. The local loopback deployment uses HTTP, so `Secure` is false by design; do not expose this listener beyond `127.0.0.1`.

The in-app page is the normal self-service rotation path. If the Admin cannot sign in, the separate emergency recovery path remains an authorized local-only reset for the existing `admin@local` account, updating only its scrypt credential and lockout fields and recording `PASSWORD_RESET`. Never create another Admin account, reset the database, or store/print the password or hash in a report.

## Ports and local exposure

The frontend URL is `http://localhost:8080`. Compose binds it to loopback only. PostgreSQL and Redis remain on the Compose network and are not available on public or LAN interfaces. The API is reachable through the frontend proxy only. Compose reserves frontend proxy address `172.31.240.10` so the API trusts forwarded headers only from that address; the external network is not used for application infrastructure.

## Daily operations

- **Start:** double-click `Start Platform.bat`; wait for the ready message and open `http://localhost:8080`.
- **Status:** double-click `Platform Status.bat`; confirm API, PostgreSQL, Redis, worker, scheduler, and frontend are healthy. `GET /health/live` checks process liveness; `GET /health/ready` checks database, Redis, and worker readiness. The local `/metrics` endpoint is available through the API for operational inspection.
- **Restart:** use `Restart Platform.bat` only when a service/configuration change or recovery requires it. Confirm readiness afterward. Do not restart a healthy stack merely to refresh dashboard data.
- **Stop:** double-click `Stop Platform.bat` for a clean Compose stop. It keeps the named database/cache volumes and backups; never use `down -v` for routine stopping.
- **Browse:** use the Arabic navigation for overview/dashboard, opportunities and filters, map, official sources, and the Review Workbench. The map groups nearby markers; open a marker to see its listed Masters. The sources view separates technical health from public coverage.
- **Scheduled work:** Celery Beat owns recurring source schedules. A successful sync is followed by the autonomous review resolver. Do not start a source sync manually during normal use. Confirm a zero actionable review backlog in the Workbench after scheduled processing.
- **Review Workbench:** filter by queue status/domain/source and inspect evidence before a human decision. A zero open queue is valid; use the resolved-status filter to inspect history. Do not use merge/reopen/decision actions as a health check.
- **DQ:** a `FAIL` gate is an actionable defect and blocks handover; preserve its gate key, observed value, affected records, and timestamp. A `WARNING` is not automatically a defect: use `final-known-limitations.json` to distinguish accepted public-coverage limits, historical audit gaps, and operational monitoring.
- **Exports:** CSV and XLSX are read-only downloads from the opportunity view. Confirm exported rows against the dashboard count when investigating a discrepancy.
- **Logs and metrics:** inspect `logs/startup.log`, Docker service logs, `/health/ready`, and `/metrics`. Keep correlation/job IDs with any incident note; never copy passwords, tokens, or source secrets into reports.

## Troubleshooting

- **Requirements restart pending:** Restart Windows, then double-click `Install Platform Requirements.bat`; the `.local-setup/reboot-required` marker documents the pending step.
- **Docker Desktop missing:** Double-click `Install Platform Requirements.bat` once prerequisites are ready.
- **Engine starting:** Leave the launcher open while it waits; it times out after ten minutes and records the failure in `logs/startup.log`.
- **Port 8080 occupied:** Close the unrelated application using that port, then retry.
- **Saved DB volume but missing `.env.local`:** the launcher restores its per-user settings copy. If both are gone, it refuses to start rather than changing stored database credentials.
- **Migration/bootstrap/service error:** See `logs/startup.log` and `docker compose` service logs using the [Platform Status launcher](../../Platform%20Status.bat). Do not delete volumes to troubleshoot.
- **Admin password lost:** if signed in, use **الحساب الشخصي → تغيير كلمة المرور**. If the Admin cannot sign in, use an authorized local-only reset for the existing `admin@local` row, update only its scrypt credential and lockout fields, and record `PASSWORD_RESET` without storing/printing the password or hash. If no approved reset operator is available, stop and request one; do not recreate the account or reset the database. The initial credential file can be stale.

### Incident handling

- **Source failure or stale freshness:** inspect the source row, latest job state, last successful scan/scope verification, failure reason, and configured coverage. A source may be healthy technically while public coverage remains limited. Let the scheduled retry proceed; do not use manual sync as a diagnostic. Escalate repeated failures through the source owner/runbook and preserve the last good source records.
- **Stuck sync job:** compare the job heartbeat/state with Celery active, reserved, and scheduled task views using Platform Status/logs. Check Redis and worker health first. Do not delete the job, reset its status, or enqueue a duplicate while a lease/task may still exist. Let the scheduler's recovery path run; escalate with job ID and timestamps if it remains nonterminal.
- **Actionable review backlog becomes nonzero:** open the Workbench, inspect evidence and reason, and route only cases that need a human decision. Use source recheck only where evidence is stale/insufficient. Do not bulk-close or merge to restore a zero count; confirm autonomous resolution has finished before declaring the queue settled.
- **DQ returns `FAIL`:** preserve the complete read-only report and gate details, stop handover/related release activity, and investigate without editing business rows. Correct only the proven cause with audit provenance, then run the gate(s) required by the approved change scope.
- **Mass-removal anomaly:** do not delete source rows or manually rerun sync. Reconcile the exact completed source scan IDs with source-scope membership and actual state transitions. Separate records merely absent from a local subset from proven source removals. Require repeated complete-scan evidence and an audited remediation plan before changing any status.
- **Database recovery:** follow the [database restore runbook](database-restore.md) and restore to a separate recovery database first. Never restore over `sharakat_local` during a test.

## Future change process

The baseline is a comparison point, not a freeze on future improvements. Record a **CHANGE REQUEST**, **ENHANCEMENT**, **BUG FIX**, or **NEW SOURCE INTEGRATION**, compare affected counts, behavior, DQ, security, and UI evidence to `ALAHSA_PLATFORM_BASELINE_2026_10`, and retain the previous baseline/report.

- **Level 1 — UI / low risk:** layout, labels, and presentation without changing API contracts or data semantics. Validate Arabic/RTL and the five standard viewport sizes plus focused UI tests.
- **Level 2 — business logic / source rules:** eligibility, normalization, classification, schedules, review behavior, or exports. Define before/after invariants, provenance and rollback; add focused tests, run the full isolated regression, then use read-only live DQ/reconciliation appropriate to the change.
- **Level 3 — schema / identity / lifecycle / major integration:** migrations, canonical identity, merge/removal behavior, authentication/session lifecycle, or a new source. Require a reviewed migration/restore plan, isolated full regression, explicit audit and safety checks, staged validation, and an updated source/operations matrix before enabling.

For a new source, follow [Adding a source](new-source.md). Do not interpret this readiness baseline as approval to run an unplanned sync or mutate live review decisions.

## Backups

The original SQLite file has a verified safety copy before migration. The importer makes another SQLite safety copy immediately before import. PostgreSQL scheduled backups are written to the persistent project `backups/` directory. To verify restore behavior, use a separate local database named `sharakat_local_restore_test`; never restore over `sharakat_local`.
