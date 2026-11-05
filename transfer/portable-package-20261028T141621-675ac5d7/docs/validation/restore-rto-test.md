# Local PostgreSQL restore and recovery-time validation

**Status:** Executed locally on 2026-10-13 (Asia/Amman).

These results measure the single-computer Windows deployment. They do not demonstrate off-host recovery or an internet-hosted production service.

| Measure | Target | Measured |
|---|---:|---:|
| RPO objective | <= 24 hours | Daily backup task is configured; a full 24-hour cadence was not observed during this test |
| RTO objective | <= 4 hours | Local Start path reached ready about 24 seconds after Docker Desktop started |
| Backup duration | — | 0.78 seconds from manifest timestamps |
| Restore duration | — | About 3.4 seconds end-to-end for isolated DB creation and restore command |
| API recovery smoke | — | HTTP 200 for `/health/live`, `/health/ready`, and `/api/opportunities?limit=1` against the restored DB |

## Backup artifact

- ID: `20261013T083522Z-29148109`
- Path: `backups/20261013T083522Z-29148109.dump`
- Size: 3,366,395 bytes
- SHA-256: `955cb296adf15b8c950288abc4979fbb9bc8bb14b0042cd952996c37fbff2b0f`
- Format: PostgreSQL custom archive, created by PostgreSQL 16 client to match the PostgreSQL 16.15 server.
- Status: `SUCCESS`, executed through `app.tasks.run_database_backup` on the Celery maintenance queue.

The earlier PostgreSQL 17 client archive was not used for the accepted restore because PostgreSQL 16 does not recognize the newer `transaction_timeout` setting emitted by that client. The runtime image now installs the PostgreSQL 16 client from the official signed PGDG repository; a new backup/restore cycle passed with the matching major version.

## Restore verification

The dump restored with `pg_restore --exit-on-error --no-owner --no-acl` into the separate database `sharakat_local_restore_test`. The restore target was confirmed absent before creation. The primary `sharakat_local` database was not overwritten. Primary and restored counts matched at the backup snapshot:

- Opportunities: 270
- Source opportunities: 2,871
- Source observations: 7,603
- Sources: 10
- Source sync jobs: 210 at the backup snapshot
- Duplicate candidates: 25; pending: 20
- Location reviews: 17; pending: 17
- Qualification reviews: 0
- Opportunity data conflicts: 104; open taxonomy: 14; open field: 8
- Change history: 169
- Merge audit: 5
- Audit events: 6
- Multi-source masters: 7
- `pg_trgm`: 1.6

The primary now has 213 sync jobs because local lock and stale-recovery validation added three job records after the backup. Opportunity, source, observation, review, conflict, history, and audit counts remain equal. The restored API returned `ready` and a non-empty opportunities page.

## Recovery limitations

The measured restore used the same local PostgreSQL server and local disk. The daily schedule emitted Beat dispatches, but this test did not wait a full day to observe a scheduled backup artifact. Retention deletion, deliberate backup failure alerts, off-host replication, machine-loss recovery, and a full 24-hour RPO measurement remain outside this local acceptance run.
