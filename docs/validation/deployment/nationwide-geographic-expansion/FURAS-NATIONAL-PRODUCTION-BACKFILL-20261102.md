# Furas National Production Deployment and Backfill — 2026-11-02

**Result: STOPPED BEFORE BACKUP, MIGRATION, DEPLOYMENT, OR SOURCE CAPTURE.**

The only connected runtime discovered is Docker Compose project `alahsa-local`, and its API has `ENVIRONMENT=local_user`. This does not establish a production target. The task's stop rule requires stopping before migration when the production pre-deployment gate cannot be verified. No production backup, schema write, runtime replacement, manual sync, or source capture was performed.

## Current live read-only snapshot

Captured from the running `alahsa-local-api-1` database on 2026-11-02 (local time):

| Measure | Observed value |
|---|---:|
| Runtime environment | `local_user` |
| Alembic revision | `0023_quant_commercial` |
| Total Masters (`opportunities`) | 587 |
| Current, unmerged Masters | 566 |
| SourceOpportunity rows | 3,180 |
| Furas SourceOpportunity rows | 436 |
| Furas linked to existing Masters | 436 |
| Source observations | 35,626 |
| Qualification reviews | 0 |
| Location reviews | 26 |
| Sync jobs | 690 |
| Active sync jobs | 0 |
| Maximum job ID | 690 |
| Duplicate Furas source IDs | 0 |
| Audit events | 3,764 |

The previous readiness report recorded maximum job ID 673. The live database now reports 690, so natural operations have occurred since that snapshot. This task did not change those jobs. National UI, map, and enumeration variables are unset in the local-user API container; their fail-closed default is false. The previously verified production report also recorded all three flags false.

## Live service checks

- API container is running and Docker reports it healthy; `/health` returned 200 and `/health/ready` returned 200.
- Frontend returned HTTP 200.
- PostgreSQL and Redis containers report healthy.
- Worker Celery inspection returned `pong`.
- Beat process is running.
- Active source jobs: 0.

These checks describe the local-user stack only. They do not establish production health.

## Runtime and migration evidence

The running local-user containers still use the previously deployed lifecycle-only images:

| Service | Tag | Image ID |
|---|---|---|
| API | `alahsa-api:lifecycle-fix-20261101` | `sha256:ae6560e822c65a3df27dc72576411d712f72816bca726b7e42b979012d933301` |
| Worker | `alahsa-worker:lifecycle-fix-20261101` | `sha256:f87b2d1d7a974f9255304e3b40f3bf0c314417606de54e5dc6e5c521a936a097` |
| Beat | `alahsa-beat:lifecycle-fix-20261101` | `sha256:87db93f8068221f75ea52fd26c29a5e957026bacb35e889a55a1d70b304613b0` |

These IDs match the lifecycle patch manifest. The lifecycle fix therefore remains present in the running local-user stack. The Furas checkpoint/geography runtime has **not** been deployed. No candidate production images were built or started. Revision remains exactly 0023; 0024 and 0025 were not applied. The standard Compose migration command remains `alembic upgrade head`, so no standard startup path was invoked.

## Bootstrap removal protection

The national checkpoint completion path now recognizes the first successful national scan after a prior local-scope scan and withholds removal reconciliation for that bootstrap. It records `first_national_bootstrap=true`, `reconciliation_executed=false`, and a false `removal_reconciliation_allowed` checkpoint value. Subsequent complete national runs continue through the existing scope/removal guards.

Regression coverage seeds a prior successful local job and an existing source row absent from the national snapshot. The row remains present and its missing counter stays zero. Focused test: **1 passed**. Repository suite: **645 passed, 1 skipped, 42 warnings**.

## Production gate and resulting status

The production-target identity gate failed because the available service identifies as `local_user`; no separate production Compose project, production endpoint, or production deployment identity was available to verify. Per the task stop condition, execution ended before backup and migration. The older 2026-11-01 readiness backup is not a substitute for the required fresh production backup.

```text
FRESH_PRODUCTION_BACKUP_VERIFIED = FALSE (NOT CREATED)
FRESH_BACKUP_RESTORE_TEST = NOT RUN
FRESH_SNAPSHOT_0023_TO_0025 = NOT RUN FOR THIS DEPLOYMENT
LIFECYCLE_FIX_PRESERVED = TRUE (RUNNING LOCAL-USER IMAGE IDS MATCH MANIFEST)
FURAS_CHECKPOINT_CODE_DEPLOYED = FALSE
PRODUCTION_MIGRATION_0024 = NOT_APPLIED
PRODUCTION_MIGRATION_0025 = NOT_APPLIED
PRODUCTION_ALEMBIC_HEAD = 0023_quant_commercial (LOCAL-USER STACK)
FURAS_NATIONAL_RUNTIME_DEPLOYED = FALSE
FURAS_NATIONAL_PRODUCTION_BACKFILL = NOT_STARTED
PRODUCTION_FURAS_JOB_ID = NONE
FURAS_PUBLIC_RECORDS_FOUND = NOT_RUN
SOURCEOPPORTUNITIES_BEFORE = 3180 (CURRENT LOCAL-USER SNAPSHOT)
SOURCEOPPORTUNITIES_AFTER = 3180 (NO TASK WRITES)
FURAS_SOURCE_ROWS_BEFORE = 436
FURAS_SOURCE_ROWS_AFTER = 436
SOURCEOPPORTUNITIES_INSERTED = 0
SOURCEOPPORTUNITIES_UPDATED = 0
SOURCEOPPORTUNITIES_REMOVED = 0
FIRST_NATIONAL_BOOTSTRAP_REMOVALS = 0 (NO RUN)
NEW_MASTERS_CREATED = 0
CURRENT_MASTERS_BEFORE = 566
CURRENT_MASTERS_AFTER = 566
DUPLICATE_FURAS_SOURCE_IDS = 0
CHECKPOINT_FINAL_STATE = NOT_STARTED
POST_BACKFILL_DQ_FAIL = NOT_RUN
RUNTIME_ROLLBACK_READY = TRUE (PREVIOUS IMAGE IDS RECORDED)
DATABASE_ROLLBACK_READY = FALSE (FRESH BACKUP NOT CREATED)
NATIONAL_UI_ENABLED = FALSE (UNSET / FAIL-CLOSED DEFAULT)
NATIONAL_MAP_ENABLED = FALSE (UNSET / FAIL-CLOSED DEFAULT)
FURAS_NATIONAL_ENUMERATION_ENABLED_AFTER_BACKFILL = FALSE (NO BACKFILL)
MANUAL_FURAS_PRODUCTION_SYNCS = 0
OTHER_MANUAL_SOURCE_SYNCS = 0
FABRICATED_OPPORTUNITIES = 0
FABRICATED_COORDINATES = 0
```

To resume this rollout safely, the deployment target must be identified as a production runtime rather than `local_user`. Keep the current national flags off until the fresh backup, isolated restore/migration proof, runtime artifact checks, and production health gates are complete.
