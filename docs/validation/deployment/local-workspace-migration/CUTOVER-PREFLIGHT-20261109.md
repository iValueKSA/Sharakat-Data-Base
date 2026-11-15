# Live Docker Cutover Preflight — 2026-11-09

**Disposition: READY FOR AUTHORIZED MAINTENANCE; CUTOVER NOT STARTED.** The user instruction requires pausing before a maintenance interruption when authorization is needed. This report captures read-only inventory and a tested database safety dump so the proposed operation is reviewable.

## Scope and active runtime

- Official workspace: `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`.
- Existing Compose project: `alahsa-local`.
- Active Compose metadata still points to `C:\Sharakat Data Base\docker-compose.yml` and `docker-compose.local.yml`.
- Six live services in that project: `api`, `frontend`, `worker`, `scheduler`, `db`, `redis`. All are healthy/running as applicable. No `migrate` or `local-bootstrap` service is running.
- Current project network: `alahsa-local_default`.
- `db` uses image `postgres:16-alpine`, volume `alahsa-local_postgres_data` mounted at `/var/lib/postgresql/data`.
- `redis` uses image `redis:7-alpine`, volume `alahsa-local_redis_data` mounted at `/data`; AOF is enabled and last write status is `ok`.
- `api` and `worker` have only a backup bind mount, currently from the old root’s `backups` directory. `frontend` and `scheduler` have no host bind mounts. No live container has the project source code mounted into it.
- The new-root resolved Compose configuration retains `alahsa-local_postgres_data` and `alahsa-local_redis_data`. It changes API/worker backup binds to `%LOCALAPPDATA%\Sharakat Data Base\backups`, and resolves the bootstrap SQLite seed from the new root as read-only.
- New-root build context is the official path. API image content matched the new-root application tree except one `__init__.py` hash difference; frontend content matched except `index.html` byte-level line endings. No rebuild is indicated for the migration-only configuration change; the planned cutover uses existing images with `--no-build`.

## Database safety evidence

- Live PostgreSQL is healthy; identity is `sharakat_local` on PostgreSQL 16.15.
- Read-only counts before cutover: `opportunities` 6,678; `source_opportunities` 9,468; `source_observations` 54,967; Alembic version `0025_source_geographic_coverage`.
- A new custom-format `pg_dump` was created outside OneDrive at `%LOCALAPPDATA%\Sharakat Data Base\backups\workspace-migration-20261109T082421Z.dump`.
- SHA-256: `4BB2E52513C990A3D5491F50C914FC6A7EA8310591F0D35D4C8A0EC2E6690211`.
- Archive inspection succeeded (389 TOC entries). Restore succeeded in an isolated, network-disabled PostgreSQL 16 container; restored counts matched exactly: 6,678 / 9,468 / 54,967; schema head matched `0025_source_geographic_coverage`. The isolated container was stopped and automatically removed. The live database was not modified.
- Existing named volumes were not replaced. No volume reset or prune was run.

## Celery, Redis, and source safety

- At the inspection time, Celery `active`, `reserved`, and `scheduled` reports were empty; queue lengths for `source_sync`, `maintenance`, `exports`, `notifications`, `document_processing`, and `celery` were all zero.
- Beat has a persisted `/app/celerybeat-schedule` file. It emits its existing due-source dispatcher every minute and also retains daily/weekly maintenance schedules. This file must be preserved and restored into a not-yet-started replacement scheduler container before Beat starts.
- Redis had no current scheduler leader lock; the latest Beat tick was `2026-11-09T08:28:07Z`.
- The Furas national enumeration and removals environment flags are unset in both the private config and running API; the feature-gate default is false. They remain disabled.
- The enqueue-due-sources task is already part of the existing Beat schedule. No manual sync or schedule change was performed.

## Other Compose project

A separate `alahsa-transfer-test-1a3f8332` project is also running, with its own network, database, Redis, scheduler, and port 18080. It is not attached to `alahsa-local` volumes or network and was not touched. Its API is unhealthy; it is not part of this migration cutover.

## New-root startup and local checks

- Compose config validation from the official root passed.
- `Platform Status.bat` ran from the official root and reported Docker, PostgreSQL, Redis, API, frontend, worker, scheduler, and readiness running.
- Current `/health/ready`, dashboard, data dashboard, source registry, source coverage, geography catalog, and geography summary endpoints returned HTTP 200. Unauthenticated `/api/auth/me` returned HTTP 401.
- No authenticated Admin/Viewer browser session was used. Authenticated CSV/XLSX exports and role-specific UI checks remain pending.
- The prior migration turn recorded a 703 passed / 1 skipped full regression and 128 PASS / 6 WARNING / 0 FAIL DQ run. Those are historical pre-cutover results, not post-cutover results. No post-cutover test has run.

## Proposed controlled cutover (awaiting authorization)

1. During a short maintenance window, stop the six live `alahsa-local` services only after confirming active/reserved/scheduled tasks and queue lengths are still zero.
2. Preserve Beat’s `/app/celerybeat-schedule` file outside the container and verify its checksum.
3. Recreate only `api`, `frontend`, `worker`, `scheduler`, `db`, and `redis` from the new-root Compose files using the same `alahsa-local` project and private AppData config; use `--no-deps --force-recreate --no-build`. Do not start `migrate` or `local-bootstrap`.
4. Preserve the two existing named volumes and network. Restore the Beat state file into the not-yet-started scheduler container, then start the services and verify mounts and Compose labels.
5. Verify health, counts, service uniqueness, Beat state, and that no source job was triggered by the cutover. Run post-cutover acceptance only after readiness.

This action will briefly interrupt localhost web access and DB/Redis connections. It does not reset, replace, or relocate persistent data. The scheduler will pause during the maintenance window; its existing schedule state will be restored so cadence is retained. **No service stop, recreation, or one-click cold-start test has yet been run.**

## Acceptance still pending

- User authorization for the maintenance interruption described above.
- Rebind and cold-start test from the official root.
- Before/after live Compose labels and mount verification.
- Post-cutover data and readiness checks; authenticated role/export/UI acceptance.
- Fresh full DQ and isolated full regression results.

Until these pass, workspace migration remains **PARTIAL**.
