# Furas Job Lifecycle Race — Post-Deployment Natural Verification

## Cutoff and scope

The deployment cutoff is **2026-11-01 15:51:59 UTC**, as recorded in the [production deployment report](FURAS-JOB-LIFECYCLE-RACE-PRODUCTION-DEPLOYMENT-20261101.md) and [patch manifest](LIFECYCLE-PRODUCTION-PATCH-MANIFEST-20261101.json).

For this report, a post-deployment source job is one whose `queued_at` (the persisted creation/queue timestamp; `SyncJob` has no `created_at` column) or `started_at` is at or after that cutoff. Production was queried in a transaction marked `READ ONLY`; no job, audit, DQ, source, or configuration row was changed by this verification.

## Natural source-job observations

At 2026-11-01 16:00:32 UTC, the production query found **zero** source jobs queued or started at/after the deployment cutoff. The maximum job ID remained 671. Therefore there are no eligible post-deployment jobs to report individually, and no source job has tested the new lifecycle code in production yet.

Post-deployment Beat/worker logs show normal maintenance activity only:

- Naturally scheduled `enqueue_due_sources` tasks returned `queued: []` at each observed interval.
- Naturally scheduled stale-job recovery returned `abandoned_running: 0`, `abandoned_queued: 0`, and `requeued_sources: []`.
- No `sync_source_task` execution appeared in the post-cutoff worker logs.

These maintenance tasks confirm the scheduler and worker are communicating, but they do not count as a source job exercising finalization. No task was forced to create evidence.

## Lifecycle and DQ assessment

There were no post-deployment source jobs, so observed terminal regressions and new post-fix consistency failures are both zero. The absence of eligible jobs means the shared lifecycle fix remains **pending natural-job verification**, not passed or failed. Furas-specific verification also remains pending because no natural post-deployment Furas job occurred.

The existing `SYNC_JOB_STATE_CONSISTENCY` gate remains unchanged. The latest persisted DQ results are historical and predate deployment:

- 2026-11-01 15:11:11 UTC: `FAIL`, sample job 670.
- 2026-11-01 15:10:52 UTC: `FAIL`, sample job 671.
- 2026-11-01 13:10:04 UTC: `FAIL`, sample job 669.

All are before the 15:51:59 UTC cutoff. The read-only query found no DQ run at/after the cutoff, so these are historical evidence and do not count as a new post-fix lifecycle failure. No historical row or DQ result was rewritten.

## Current production safety

- Alembic head: `0023_quant_commercial`.
- `NATIONAL_UI_ENABLED`, `NATIONAL_MAP_ENABLED`, and `FURAS_NATIONAL_ENUMERATION_ENABLED`: false.
- API: running and Docker healthy; `/health` and `/health/ready` returned 200.
- Worker: running; Celery inspection returned `pong`.
- Beat: running; naturally scheduled maintenance tasks were observed.
- PostgreSQL and Redis: running and Docker healthy.
- Active sync jobs: 0.
- Historical jobs 644, 651, 652, 666, 668, 669, 670, and 671 were not edited or retried by this verification.
- Manual source syncs: 0. Backfills: 0. Production schema changes: 0.

## Required status

```text
POST_DEPLOYMENT_JOBS_FOUND = 0
POST_DEPLOYMENT_COMPLETED_JOBS = 0
POST_DEPLOYMENT_TERMINAL_REGRESSIONS = 0
NEW_POST_FIX_SYNC_JOB_STATE_CONSISTENCY_FAILURES = 0
LIVE_SHARED_LIFECYCLE_VERIFICATION = PENDING_NATURAL_JOB
POST_DEPLOYMENT_FURAS_JOBS = 0
FURAS_LIVE_VERIFICATION = PENDING_NATURAL_FURAS_JOB
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
PRODUCTION_ALEMBIC_HEAD = 0023_quant_commercial
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
PRODUCTION_SCHEMA_CHANGES = 0
HISTORICAL_JOB_ROWS_CHANGED = 0
```
