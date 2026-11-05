# One-click Windows launcher validation

**Date:** 2026-10-13 (Asia/Amman)  
**Local URL:** `http://localhost:8080`  
**Local launcher gate:** `ONE_CLICK_LOCAL_PLATFORM_COMPLETE`

## Windows runtime

| Item | Verified result |
|---|---|
| Windows | Windows 11 Pro, version `10.0.26300`, x64 |
| Virtualization | WSL2 backend is active; Docker Engine runs Linux containers. WMI firmware virtualization flags reported false while `HypervisorPresent=True`; the working WSL2 Engine is the operational check. |
| WSL | `3.0.3.0`; Docker Desktop distribution uses WSL version 2 |
| Docker Desktop | `4.95.0` |
| Docker Engine | `29.8.2`, client and server |
| Compose | v5.6.0 |
| Backend | WSL2; Docker VMM was not selected |

The first-time installer configured WSL2 and required a Windows restart. The user restarted; the installer resumed, verified/installed Docker Desktop through WinGet, started the platform, and returned PASS. The requirements installer was rerunnable and did not reinstall working dependencies.

## Launch and service checks

| Acceptance item | Result | Evidence |
|---|---|---|
| `Install Platform Requirements.bat` | PASS | Installer diagnostic and final PASS are in `logs/local-requirements-diagnostic.log` |
| Compose validation/build | PASS | Compose config succeeded; API, worker, scheduler, migration, bootstrap, and frontend images built |
| PostgreSQL | PASS | PostgreSQL 16.15 healthy; Alembic `0016_source_type_text (head)`; `pg_trgm` 1.6 |
| SQLite import | PASS | 230 opportunities, 2,831 source rows, 7,603 observations, 10 sources, 200 sync jobs imported transactionally; local admin initialized |
| Redis | PASS | Redis health check and API readiness both report `ok` |
| API / frontend | PASS | `/health/ready` is `ready`; frontend and API routes return HTTP 200 |
| Worker / Beat | PASS | Worker ping and heartbeat task succeeded; Beat logs show minute schedule dispatch |
| Start button opens browser | PASS | `Start Platform.bat` opened `http://localhost:8080`; a browser process targeted the local URL |
| Admin login | PASS | Local credential file logged in as Admin; `/api/auth/me` verified the role; logout succeeded |
| Status button | PASS | Shows Docker, PostgreSQL, Redis, API, Frontend, Worker, Scheduler, and Readiness as RUNNING |
| Desktop shortcuts | PASS | Start, Stop, and Platform Status shortcuts point to the root BAT launchers |
| Python tests | PASS | 104 passed; one Starlette deprecation warning |

## Persistence and task execution

The local PostgreSQL database currently contains 270 opportunity rows (265 unmerged masters: 259 active and 6 historical; 5 merged rows), 2,871 source opportunities, 7,603 observations, 10 sources, and 213 sync jobs. It has 7 multi-source masters, 20 pending duplicate candidates, 17 pending location reviews, 0 pending qualification reviews, 14 open taxonomy conflicts, and 8 open field conflicts.

- Stop then Start stopped every service without removing volumes. Counts matched exactly: opportunities 270, source opportunities 2,871, observations 7,603, sources 10, sync jobs 213, duplicate candidates 25, location reviews 17, qualification reviews 0, data conflicts 104, change history 169, merge audit 5, audit events 6.
- Docker Desktop was stopped through its supported CLI, then `Start Platform.bat` launched Desktop and restored the full stack. The latest run reached ready 24 seconds after Start began and opened the browser. Counts remained stable.
- Two concurrent KFU enqueue attempts returned one `QUEUED` and one `SKIPPED_ALREADY_RUNNING`. The accepted sync reported 0 new and 0 updated records.
- A temporary isolated Celery worker task had its child process killed while running. Celery redelivered it; attempt 2 completed under the same task ID. A synthetic stale KFU job became `ABANDONED` and its retry completed. The probe did not use or mutate source data.
- Redis-backed CORS, login throttling, API rate limiting, secret injection, protected-mode HSTS, and generic 500 response checks passed. Temporary rate-limit keys and the test worker were removed.

## Backup and restore

The real Celery backup task produced:

- File: `backups/20261013T083522Z-29148109.dump`
- Size: 3,366,395 bytes
- SHA-256: `955cb296adf15b8c950288abc4979fbb9bc8bb14b0042cd952996c37fbff2b0f`
- Backup duration: 0.78 seconds

The archive restored with `pg_restore --exit-on-error` into the separate `sharakat_local_restore_test` database. Primary and restored table counts, review states, multi-source count, and `pg_trgm` matched. A temporary API smoke against the restored database returned HTTP 200 for live, ready, and opportunities. The PostgreSQL 17 client archive was rejected during the first restore attempt because PostgreSQL 16 does not support its `transaction_timeout` setting; the runtime image was changed to use PostgreSQL 16 client tools, and the replacement backup restored cleanly. The SQLite working database and its pre-migration safety copy remain untouched.

See [restore and RTO validation](restore-rto-test.md) for snapshot counts and timing limits.

## Launcher behavior fixes

- PowerShell now handles Compose progress written to stderr without treating successful startup as a failure.
- Stop waits for containers to finish shutting down and verifies no project container remains running. It never removes volumes.
- Nginx uses Docker's embedded resolver for API routing and preserves the request URI. This fixed a stale API IP and path-forwarding issue discovered during Docker Desktop restart testing.
- Docker CLI is added to the launcher process PATH so the credential helper is discoverable.
- PostgreSQL backup tools in the application image match the PostgreSQL 16 server major version.

## Scope limits

This validates the local single-computer deployment only. The local UI is HTTP on loopback. The Admin credential filename matches the explicit `.gitignore` exclusion and its ACL grants full control to the current Windows account; this workspace has no `.git` metadata for `git check-ignore`. An external HTTPS proxy, off-host backup replication, actual 24-hour retention cadence, deliberate backup-failure alerting, SMTP delivery, machine-loss recovery, and GitHub Actions were not exercised. They are not blockers for the requested local launcher gate.
