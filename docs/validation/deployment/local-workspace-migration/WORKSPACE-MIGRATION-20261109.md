# Local Workspace Migration Validation — 2026-11-09

## Result

**Status: PARTIAL**

The new checkout, its Compose configuration, local startup helper, data files, and canonical tests validate from the official OneDrive path. Existing database and Redis volumes are preserved and the currently running platform is healthy. The running containers still identify the former `C:\Sharakat Data Base` directory as their Compose working directory. Rebinding the live services was not performed because it would recreate worker/scheduler containers and could affect scheduled source work. A controlled rebind and cold start remain necessary before the migration can be accepted as complete.

## Workspace and compatibility

- Official root verified: `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`.
- The project structure includes Docker Compose, FastAPI, Nginx, PostgreSQL, Redis, Celery worker/scheduler, Alembic, frontend assets, tests, and Windows scripts.
- The Compose project identity remains `alahsa-local`. Configuration validation from the new root succeeded and resolves the existing named volumes `alahsa-local_postgres_data` and `alahsa-local_redis_data`.
- The PowerShell local-platform helper parses successfully and composes commands with the AppData private config path and `alahsa-local` project identity. Its already-running readiness branch found the existing frontend and reported ready.
- Unicode/space path smoke test passed with a disposable container bind mount: frontend HTML and SQLite seed bytes were readable from this root. Compose bind paths resolve correctly. Required runtime files inspected were locally readable and had no cloud-placeholder flags.
- Runtime/backup configuration was moved outside OneDrive. 100 existing backup files were copied to `%LOCALAPPDATA%\Sharakat Data Base\backups`; all 100 hashes matched, with no missing or extra files. Existing originals remain in place. Private config was backed up before updating its backup directory.
- Operational source/startup files contain no hardcoded old-root references. One old-root dependency remains: the active containers’ Compose label points to `C:\Sharakat Data Base`. Historical reports and generated `tmp` copies were excluded from that source count and left unchanged. The portable setup README path example was made generic.

## Data and live service checks

- Existing volumes: `alahsa-local_postgres_data` and `alahsa-local_redis_data`, both created 2026-10-13 and mounted by the active stack. No volume reset or replacement occurred.
- Read-only database/API evidence: 6,678 `opportunities` rows, 9,468 `source_opportunities`, and 6,657 current Master records returned by the API. Historical reference values are not treated as fixed live expectations.
- DQ observation reported 54,967 observations, 14 configured sources (13 enabled), 13 open reviews, and migration head 0025.
- `http://localhost:8080/health/ready`: HTTP 200; database, Redis, and worker readiness were healthy.
- Dashboard, data dashboard, sources, source coverage, geography catalog, and geography summary API routes returned HTTP 200. Opportunity summary showed 6,657 current Masters. The geography catalog and summary were available. No visual browser acceptance was run in this migration validation.
- Unauthenticated `/api/auth/me` returned HTTP 401, preserving the authentication boundary. An authenticated session was not used; export authorization and role-specific UI behavior remain unverified here.
- CSV/XLSX export responses were not accepted as verified: the initial endpoint probe exceeded its time window before export results were recorded.

## Configuration and tests

- `docker compose --env-file <AppData private config> -f docker-compose.yml -f docker-compose.local.yml -p alahsa-local config --quiet`: PASS.
- PowerShell parse checks for local-platform and its start/stop/status/installation scripts: PASS.
- Full canonical test suite, isolated in a disposable container with the project mounted read-only and a temporary SQLite database: **703 passed, 1 skipped, 43 warnings** in 76.63 seconds. `pytest-asyncio` was installed only in that disposable container. No application database or volume was modified.
- Focused pinned source-logo contract after LF normalization: **3 passed**. `.gitattributes` now pins LF for source-logo SVGs and PEM certificate files so Windows checkout conversion does not invalidate byte-hash checks.
- Full DQ, read-only/non-persisting: **128 PASS, 6 WARNING, 0 FAIL** (run `dbb0825b45f345488fb7a9e36314fbeb`). Warnings included the already-known Furas, MODON, and NHC conditions.

## Changes made

- `docker-compose.local.yml`: backup binds use configurable absolute `LOCAL_BACKUP_PATH`, defaulting to relative `./backups` for portable installs.
- `scripts/local-platform.ps1`: local non-portable config, credentials, and backups use private AppData; portable installs retain their existing root-relative paths and Compose project identity.
- `.gitattributes`: LF rules for pinned source-logo SVGs and PEM certificates.
- `app/static/source-logos/*.svg` and the pinned PEM working copies: normalized line endings for Windows checkout integrity.
- `PORTABLE-SETUP-README.md`: removed the obsolete old-root example.
- No business data, source identity, schedule, or PostgreSQL/Redis volume was changed. No source synchronization was run.

## Remaining acceptance work

1. Rebind the existing Compose project from the new root during an approved maintenance window, preserving the same named volumes and environment.
2. Verify a cold start from the new root and confirm readiness without triggering any source synchronization.
3. In an authorized signed-in session, verify search, pagination, map and geographic filters, CSV/XLSX exports, and role-based permissions.

Until those steps pass, development from the new checkout is validated but the live workspace migration is not fully closed.
