# Database backup and restore

## Objectives and backup scope

Initial objectives are RPO at most 24 hours and RTO at most 4 hours. Celery Beat requests a daily `pg_dump` custom-format backup. Each artifact has a JSON manifest with backup ID, UTC start/completion, bytes, location, and SHA-256. Defaults retain 7 daily, 4 weekly, and 3 monthly restore points. Backups are written to `/backups`; mount this to encrypted durable storage with access controls and off-host replication before production use. Do not treat a local Docker volume as disaster recovery.

## Verify and restore

1. Select a successful manifest and verify its SHA-256 against the dump (`Get-FileHash -Algorithm SHA256` on Windows or `sha256sum` on Linux).
2. Create a separate recovery database and credentials. Never restore over the live database during a test.
3. Restore with `pg_restore --clean --if-exists --no-owner --no-acl --dbname <recovery-url> <backup.dump>`.
4. Run `alembic upgrade head` against the recovery database, then check Alembic version, source/master/observation counts, review queues, and representative Arabic/English rows.
5. Record restore start/end, backup ID, checksum, counts, and elapsed time in the incident record. A backup is not considered verified until this separate restore succeeds.

## Failure response

`BACKUP_FAILED` is CRITICAL. Inspect the worker logs by request/job correlation ID, check PostgreSQL availability, free space, permissions, `pg_dump` compatibility, and backup-volume health. Preserve the previous good restore point. Repair the cause and run one manual backup task; verify its manifest and checksum.

## Current verification status

The repository contains the automated backup task and restore procedure. A PostgreSQL restore has not been executed in this workspace because Docker/PostgreSQL are unavailable. Record the first successful staging restore before production cutover.
