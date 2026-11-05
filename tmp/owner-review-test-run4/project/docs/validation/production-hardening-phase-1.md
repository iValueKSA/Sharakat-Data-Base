# Production Hardening – Phase 1 validation

**Status:** `PRODUCTION_HARDENING_PHASE_1_COMPLETE` for the requested single-computer Windows deployment. The local runtime, worker recovery, PostgreSQL backup, and isolated restore were executed and verified on 2026-10-13. This gate does not claim an internet-hosted enterprise deployment, external TLS ingress, off-host disaster recovery, SMTP delivery, or external CI acceptance.

The single-computer Windows deployment mode and launchers are documented in [local Windows runbook](../runbooks/local-windows.md) and [launcher validation](local-windows-launcher.md). The application is running locally at `http://localhost:8080`; all persistent storage remains on this computer.

## Architecture

The current state and target topology are documented in [production architecture](../architecture/production-architecture.md). The ten source adapters and their existing provenance, qualification, cross-source matching, and public-coverage behavior are retained. Production is designed as FastAPI + static frontend + PostgreSQL + Redis + Celery workers + Celery Beat; source work stays in the existing service pipeline.

## Scheduler and worker reliability

Celery and Redis ran in Compose. Beat dispatched scheduled heartbeat, queue, and notification tasks. A queued heartbeat task completed and persisted its result. Two concurrent KFU enqueue requests produced one accepted task and one `SKIPPED_ALREADY_RUNNING`; the KFU sync completed with 0 new and 0 updated records. A dedicated temporary worker's child process was killed during a late-ack task; Celery redelivered the same task ID, and attempt 2 completed successfully. A synthetic stale KFU job was marked `ABANDONED` and its retry completed. Temporary worker, task file, and Redis test keys were removed.

## Authentication, authorization, and audit

Production requires PostgreSQL, Redis, a secret key, HTTPS public URL, and exact CORS origins. Production uses opaque server-side, eight-hour HTTP-only cookies and scrypt hashes; Admin, Analyst, and Viewer roles are enforced. Login has throttling, failed-login counters, temporary lockout, user disablement, and session revocation. Privileged API mutations create audit events; source pause/resume, user lifecycle, and system settings also record named audit events. Authentication and role tests pass. SSO and a cross-site request forgery token are not included; SSO is Phase 2, and deployment requires same-site cookies plus exact-origin CORS.

## Alerts and notifications

PostgreSQL alert events are deduplicated by fingerprint and track severity, source, open/acknowledged/resolved state, acknowledgement actor, and timestamps. Source/parser/collection, opportunity-created, material deadline/status/location, stale-sync, and backup events are supported. Daily deadline reminders use configurable `DEADLINE_ALERT_DAYS` thresholds (default 30, 14, 7, 3, and 1 day), skip expired/cancelled opportunities, and are covered by a deduplication test. Email is a separate SMTP adapter/queue and is disabled unless explicitly configured. Microsoft Teams, WhatsApp, Telegram, and Slack remain future channels. Delivery retries and paging escalation beyond the persisted alert dashboard are not yet verified.

## Observability

Request correlation IDs, JSON request logs, safe production error bodies, security headers, `/health`, `/health/live`, `/health/ready`, `/metrics`, source health, system status, schedule visibility, stale-source status, queue counts, and slow-query logging are implemented. Metrics are process-local API request counters plus system-status queries; full Prometheus job/adapter/worker histograms and external infrastructure monitoring remain outstanding. Readiness checks the local database, Redis, and worker heartbeat, not external source websites.

## Database and migrations

Production rejects SQLite. PostgreSQL 16.15 ran locally; Alembic reached `0016_source_type_text (head)` and `pg_trgm` 1.6 was present. The transactional one-time import marker reports 230 imported opportunities, 2,831 source rows, 7,603 source observations, 10 sources, and 200 source-sync jobs. The original SQLite database and safety copy were retained. After subsequent successful scheduled/manual syncs, the local database has 270 opportunities, 2,871 source rows, 7,603 observations, and 213 source-sync jobs. PostgreSQL also performed the live KFU sync and restore-count checks.

## Backups and restore

The Celery backup task created `backups/20261013T083522Z-29148109.dump` (3,366,395 bytes, SHA-256 `955cb296adf15b8c950288abc4979fbb9bc8bb14b0042cd952996c37fbff2b0f`) in 0.78 seconds. It restored with matching PostgreSQL 16 tools into the separate `sharakat_local_restore_test` database. All checked table counts, review queues, multi-source counts, and `pg_trgm` matched; a temporary application smoke against that restored DB returned HTTP 200 for live, ready, and opportunities. Backup creation-to-restore-command took about 3.4 seconds. The detailed [restore/RTO report](restore-rto-test.md) records the limits of these local measurements. Off-host encrypted storage and backup retention/failure-alert exercises remain deployment follow-ups.

## Deployment and security

The API image is multi-stage and non-root; frontend, migration, API, worker, scheduler, PostgreSQL, and Redis have separate Compose services. Secrets are injected from environment at runtime and excluded from the Docker build context; `.env.example` lists names only. The frontend binds to loopback for an HTTPS edge proxy/load balancer. Production startup rejects insecure URL/database/Redis/CORS configuration. Rate limiting uses Redis in production. Spreadsheet formula escaping and streaming CSV/write-only XLSX export are implemented. Dynamic source URL administration and attachment downloading are not supported by the current UI; adapters use code-defined official routes and preserve attachments as metadata, avoiding user-controlled fetch targets and file execution.

## CI and runbooks

CI configuration includes backend lint, offline Python fixtures, JavaScript syntax validation, `pip-audit`, PostgreSQL migration/single-head checks, and API/frontend image builds. The current local suite passed 104 tests. Docker Compose config and all service images built; Windows PowerShell launcher/status scripts ran successfully; protected settings-file ACLs were checked. GitHub Actions was not run and is not required for the local-only acceptance gate. Operational runbooks cover source failure, parser failure, restore, worker, Redis, scheduler, deployment, rollback, staging, and future source onboarding.

## Regression and controlled live sync

The ten sources were synced in their established order against a copy of the local database after migration. Each returned `SUCCESS`; all reported 0 new, 0 updated, and 0 removed records. Master/source/observation counts exactly matched the original. The NHC public-route checker recorded three new HTTP 403 route observations (English category mirror, English Real Estate Stimulation page, and public investor-intake shell); the required Arabic category route succeeded, so NHC remained `HEALTHY` with `PUBLIC_COVERAGE_LIMITED`. These three route observations are classified `VALID_LIVE_CHANGE` and documented in [NHC route criticality](nhc-route-criticality.md). Aggregate opportunity data was `DATA_STABLE`; there were 0 unexplained data changes and 0 parser regressions. This regression ran on the isolated SQLite copy, not on a production PostgreSQL/Celery deployment.

## Infrastructure environment

The verification host is Windows 11 Pro, build 26300, x64, at `C:\Sharakat Data Base`. Docker Desktop 4.95.0 / Engine 29.8.2, Compose v5.6.0, WSL 3.0.3, PostgreSQL 16.15, Redis 7, API, frontend, worker, and scheduler were present and running. The selected backend is WSL2. A full Windows restart had been completed before validation; Docker Desktop stop followed by `Start Platform.bat` also restarted the engine and made the platform ready. See [infrastructure evidence](production-phase1-evidence/environment.md).

## Docker validation

The API, migration, worker, scheduler, local-bootstrap, and frontend images built successfully. Compose started all six long-running services; PostgreSQL, Redis, API, worker, frontend, and readiness were healthy. Stop/start and Docker Desktop stop/Start-button tests preserved the same core table counts. Runtime secrets were present in container environment but absent from API image config/history. Nginx now resolves the API service dynamically so Docker Desktop restarts that change container IPs do not leave the frontend proxy stale. Services run non-root where configured. The frontend is bound only to loopback.

## PostgreSQL validation

PostgreSQL 16.15 started cleanly with `pg_trgm` 1.6 and Alembic `0016_source_type_text`. The app executed live queries and the KFU sync. The current database has 270 opportunities, 2,871 source rows, 7,603 observations, 10 sources, 213 sync-job rows, 17 pending location reviews, 20 pending duplicate reviews, 14 open taxonomy conflicts, and 8 open field conflicts. PostGIS is not required. The full restore count comparison is in [restore evidence](production-phase1-evidence/restore-test.txt).

## Redis validation

Redis pinged successfully from API and workers; health readiness reported Redis and worker `ok`. Docker Desktop restart brought Redis and Celery back. Redis-backed API rate limits were exercised and the temporary keys were cleared. PostgreSQL remains authoritative for source records, opportunities, audit, alerts, and job history; Redis holds broker, reservation, and lock state.

## Worker and scheduler validation

Worker and Beat containers ran. Beat emitted due-task dispatch logs. Real Celery task IDs are recorded for heartbeat, backup, KFU lock, and worker-loss recovery. Concurrent KFU enqueues yielded one `QUEUED` and one `SKIPPED_ALREADY_RUNNING`. A worker child process was killed and the late-ack task was redelivered and completed on its second attempt. Stale-job recovery marked one deliberately stale test job `ABANDONED` and its KFU retry completed. No production source was changed by the worker-interruption probe.

## Backup execution and restore

The backup task produced a custom-format PostgreSQL dump, with a checksum manifest. `pg_restore --exit-on-error` restored it into the previously absent `sharakat_local_restore_test`; table counts and extensions matched the primary at the backup snapshot. API live/ready/opportunities checks against the restored database returned HTTP 200. Retention deletion behavior and backup-failure alerting were not forced.

## RPO and RTO validation

The design targets remain RPO <= 24 hours and RTO <= 4 hours. A real backup completed in 0.78 seconds and the restore operation completed successfully; the `Start Platform` path reached ready about 24 seconds after Docker Desktop was started. These local point-in-time measurements are comfortably within the RTO target but do not prove a full 24-hour backup cadence or off-host recovery.

## Runtime security tests

Local protected-mode smoke verified HSTS and generic 500 responses without leaking exception text. CORS allowed the configured localhost origin and rejected an unrelated origin. Login throttling and API rate limiting passed against Redis. Secrets were injected at runtime and absent from the image config/history. Dynamic source URL administration is not exposed, so no user-controlled source-fetch/SSRF route exists to exercise. A real internet-facing TLS terminator and forwarded-header chain are outside the local HTTP-only deployment and were not tested.

## Outstanding risks

- External HTTPS termination, off-host encrypted backup replication, SMTP delivery, and operational backup retention/failure alert tests remain deployment follow-ups.
- GitHub Actions was not run; local validation is the acceptance evidence for this single-computer request.
- API metrics do not yet provide full job/queue/worker histograms, and the UI does not yet provide a complete operational dashboard for queue, worker, scheduler, and backups.
- The `PRODUCTION_HARDENING_PHASE_1_COMPLETE` gate here applies to the local single-machine deployment only. It does not represent an internet-hosted enterprise production service.
- Off-host encrypted backup storage remains necessary if the user later needs recovery from loss of this computer.

## Infrastructure evidence index

Per-component outputs are under [production-phase1-evidence](production-phase1-evidence/), with the complete local acceptance matrix in [launcher validation](local-windows-launcher.md) and measured recovery timings in [restore/RTO report](restore-rto-test.md). The local Docker/PostgreSQL/Redis/Celery/Beat/backup/restore checks now have runtime evidence.
