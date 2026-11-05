# Scheduled Sync & Job Lifecycle Reliability Deep Review

**Result:** `SCHEDULED_SYNC_JOB_LIFECYCLE_RELIABILITY_DEEP_REVIEW = COMPLETE`  
**Evidence snapshot:** 2026-10-21 12:30 UTC (15:30 Asia/Amman)  
**Manual source sync:** `FALSE`

## Scope and live snapshot

This review covered scheduled sync lifecycle, Job 212, lock/retry/recovery behavior, source-specific runtimes and freshness, Beat scheduling, sync DQ gates, and the admin job activity display. Earlier data-quality, coverage, identity, review-governance, and sector-classification reviews were not reopened.

The live database held **415 sync jobs**. At the evidence snapshot, there were no RUNNING, QUEUED, or RETRYING jobs, no current pending jobs, and **0 illegal lifecycle records**. Celery active/reserved/scheduled views were available and empty; the `source_sync` queue depth was 0; scoped source-sync locks and reservations were absent. Database-running-without-task, live-sync-task-without-job, duplicate same-source running jobs, and orphaned locks were all 0.

Two naturally scheduled jobs appeared since the 413-job starting snapshot: Job 414 (Furas) completed with 0 new and 0 updated records; Job 415 (Al-Ahsa Opportunities) completed with 84 reported updates and 0 new records. Both were scheduled, complete scans. They were not manually triggered. The review itself made no opportunity, observation, review, identity, or source-content edits; its only live record correction was Job 212 lifecycle adjudication with audit evidence.

## Job 212 adjudication

**Classification:** `C. DEAD_TASK_WITH_UNFINALIZED_DB_STATUS`  
**Secondary fact:** later successful syncs superseded its scan opportunity.

Job 212 is KFU (source 5), created/started 2026-10-13 07:39:10 UTC. Its Celery task ID and owning worker identity are null; its heartbeat never advanced from start; it processed 0 pages and 0 records; completeness is false; removal count is 0. Live worker inspection found no matching task, and neither `source-sync:5` nor `source-sync-enqueued:5` existed. The worker service itself was online, so the evidence is absence of a task/owner, not absence of the worker process.

The record already had `job_state=ABANDONED` from a prior stale recovery while `status` remained `RUNNING` and `finished_at` remained null. Later successful KFU jobs 213, 227, 261, 308, 333, 358, 369, and 395 confirm the old scan was superseded. Job 395 is the latest successful KFU job in the captured history (2026-10-21 06:01:12 UTC).

The source-specific interval from Job 212 start to the next KFU job start contained 0 SourceOpportunity first-seen rows, 0 SourceObservation first-seen rows, 0 QualificationReview rows, and 0 SourceContentItem rows. The job counters also show no scan or removals. Job 212 was reconciled to the established terminal state `ABANDONED`; original start, source, attempt, correlation, task ID and heartbeat were preserved, `finished_at` was populated, and scan completeness set false. AuditEvent 89 and a SystemEvent document the adjudication. No history was deleted or rewritten.

## Lifecycle and recovery design

`SyncJob` is stored in `source_sync_jobs`; status and job_state are `String(40)` columns rather than database enums. The implementation states and terminal transitions are recorded in [job-lifecycle-state-machine.json](job-lifecycle-state-machine.json). Legal operation includes queue to run, bounded retry to run, and terminal success/warning/failure/cancel/skip/abandon outcomes. Active states have no finish timestamp; terminal states have one. The live consistency gate found 0 violations.

The Beat scheduler runs stale recovery every 300 seconds. Recovery fails closed if any Celery active/reserved/scheduled inspection is unavailable. A RUNNING or RETRYING job becomes ABANDONED only after its source-specific heartbeat/start threshold is exceeded, its task is absent from all three worker views, and its source lock is absent. Old queued jobs use the corresponding queue-age rule and task/lock checks. Recovery writes a system event, preserves lineage, clears only a matching reservation token, and requeues each enabled source once. There is no startup hook; the periodic five-minute recovery is the automatic mechanism. Recovery is idempotent for terminalized rows.

Source profiles use successful-job history only. With at least eight successes the stale limit is `max(hard limit + 600 seconds, 3 × p95, 2 × observed maximum)`; sparse histories use at least 3,600 seconds and the hard-limit-plus-600-second floor. The source-specific results are:

| Source | Successful runs | Median (s) | p95 (s) | Max success (s) | Stale threshold (s) |
|---|---:|---:|---:|---:|---:|
| Furas | 82 | 5.077 | 19.558 | 253.894 | 2,400 |
| Al-Ahsa Opportunities | 70 | 7.268 | 32.828 | 195.460 | 2,400 |
| AHDA | 33 | 28.475 | 175.222 | 3,399.773 | 6,800 |
| Invest Saudi | 38 | 48.537 | 108.520 | 123.759 | 2,400 |
| KFU | 29 | 0.752 | 6.277 | 6.322 | 2,400 |
| MODON | 13 | 7.331 | 14.370 | 14.370 | 2,400 |
| NCP | 21 | 29.191 | 36.229 | 39.306 | 2,400 |
| NHC | 8 | 5.998 | 7.346 | 7.346 | 2,400 |
| PIF | 9 | 13.503 | 15.996 | 15.996 | 2,400 |
| MWAN | 8 | 16.251 | 20.206 | 20.206 | 2,400 |

Celery soft and hard task limits are 1,740 and 1,800 seconds. The source lock and enqueue reservation use owner tokens with Redis `SET NX EX`, TTL 2,400 seconds, and compare-and-delete Lua release. The TTL outlives the hard timeout by 600 seconds. Locking is source-specific, so unrelated sources can run concurrently. There is no lease renewal; the hard task limit is shorter than the lock TTL. A live task or source lock prevents stale recovery.

Retries are bounded to four, with 60/300/900/3,600-second backoff plus 0–30 seconds jitter. Network timeouts, transient connection/DNS failures, HTTP 429/5xx, and transient SQLAlchemy connection errors can retry. Authentication, permanent HTTP 401/403/404, parser/structure, validation and configuration failures are terminal. Retries keep one SyncJob, correlation ID and Celery task lineage while incrementing attempt number. Unclassified exceptions are not retried and finalize the job as failed.

## Ingestion and data safety

`service.sync_source` marks scan completeness false before retrieval and only permits absence/removal reconciliation after a complete successful enumeration. Failed attempts reset stale prior-attempt counters and completeness; valid observations written before an incomplete failure are retained without claiming a complete scan. Adapter/parser/timeout/DB exceptions finalize or enter bounded retry, and recovery sets incomplete scans to `pagination_complete=false`. Focused regression cases exercise partial-scan removal protection, retry resets, worker loss, lock ownership, cancellation, broker-inspection failure and active-task false-stale prevention.

The periodic dispatcher distinguishes source `last_attempted_sync` from `last_successful_sync`. Freshness is evaluated without changing source coverage or health semantics; the source matrix is in [source-freshness-matrix.json](source-freshness-matrix.json).

## Scheduler and freshness

Beat uses UTC with `enable_utc=true`; application timestamps are timezone-aware UTC and PostgreSQL stores timezone-aware timestamps. There are 9 Beat entries and 0 duplicate schedules. The due-source dispatcher runs each minute and checks the configured source interval with a 15-minute minimum. All 10 enabled adapter sources have an explained schedule; unexplained enabled sources without schedules: 0. An enqueue reservation and per-source lock prevent an overlapping schedule from starting duplicate ingestion.

Four sources currently age beyond the freshness threshold: MODON (6), NCP (7), NHC (8), and MWAN (10). These remain warnings; no source sync was started to change them. One historical sync runtime anomaly, job 393, is also surfaced for review. Freshness and coverage warnings do not produce DQ failures.

## DQ, tests and interface

The final read-only full live DQ evaluated 65 gates: **61 PASS, 4 WARNING, 0 FAIL**. All sync liveness, state-consistency, concurrency, reconciliation, lock and partial-scan safety gates passed. The sync warning samples are four aged sources and runtime anomaly job 393. Full details are in [sync-operational-dq-results.json](sync-operational-dq-results.json).

The full regression suite passed **301 tests, 0 failures** using a temporary SQLite database in a container with network disabled. There were 22 existing deprecation warnings from Starlette/httpx and Alembic. Focused lifecycle, DQ, ingestion and security tests also passed earlier (70 passed) after the reliability changes. Test results are isolated from live PostgreSQL and Redis.

The admin activity view was verified in Edge/Playwright at 1920×1080. It retained RTL, had no horizontal overflow, exposed finished time, attempt, error and recovery state, and showed no page errors. The UI check used a test-only admin identity and a fixture row; it validates display rendering, while live job state and DQ were checked separately. The screenshot is [admin-job-lifecycle-1920x1080.png](admin-job-lifecycle-1920x1080.png).

## Deployment and final assertions

The refreshed API and worker images now contain the source-specific threshold helper and are healthy. PostgreSQL, Redis, scheduler and frontend were not restarted. The DB and Redis named volumes were preserved. Source sync was never manually triggered, and the full sector review/classification was not rerun.

- `ILLEGAL_JOB_STATE_RECORDS_REMAINING = 0`
- `JOB_212_ADJUDICATED = TRUE`
- `JOB_212_PARTIAL_BUSINESS_WRITES = 0`
- `JOB_212_FALSE_REMOVALS_REMAINING = 0`
- `DB_RUNNING_WITHOUT_LIVE_TASK = 0`
- `LIVE_SYNC_TASK_WITHOUT_DB_JOB = 0`
- `ORPHANED_DISTRIBUTED_LOCKS_REMAINING = 0`
- `ACTIVE_LONG_RUNNING_JOB_FALSE_STALE = FALSE`
- `ACTIVE_SYNC_CAN_LOSE_LOCK_AND_ALLOW_DUPLICATE_SYNC = FALSE`
- `UNBOUNDED_SYNC_RETRIES = FALSE`
- `RETRY_LINEAGE_TRACEABLE = TRUE`
- `UNHANDLED_EXCEPTION_CAN_LEAVE_RUNNING_JOB = FALSE`
- `WORKER_CRASH_RECOVERY = PASSED`
- `RESTART_STALE_JOB_RECOVERY = PASSED`
- `TIMEOUT_CAN_LEAVE_RUNNING_JOB = FALSE`
- `PARTIAL_SCAN_CAN_TRIGGER_FALSE_REMOVALS = FALSE`
- `REMOVAL_DETECTION_REQUIRES_COMPLETE_SUCCESSFUL_SCAN = TRUE`
- `FAILED_SYNC_MARKED_AS_COMPLETE = FALSE`
- `LAST_ATTEMPT_SEPARATE_FROM_LAST_SUCCESS = TRUE`
- `UNEXPLAINED_ENABLED_SOURCES_WITHOUT_SCHEDULE = 0`
- `DUPLICATE_BEAT_SCHEDULES = 0`
- `OVERLAPPING_SCHEDULE_CAN_START_DUPLICATE_INGESTION = FALSE`
- `LIVE_DQ_FAILING_GATES = 0`
- `FULL_REGRESSION_SUITE = 301 passed / 0 failed`
- `UNEXPLAINED_BUSINESS_DATA_CHANGES = 0` (natural scheduled Job 415 reported 84 updates and is separately recorded)
- `MANUAL_SOURCE_SYNC_STARTED = FALSE`

`SCHEDULED_SYNC_JOB_LIFECYCLE_RELIABILITY_DEEP_REVIEW = COMPLETE`

## DQ warning-count reconciliation addendum

A focused, read-only DQ evaluation was run solely to retrieve the complete warning gate array omitted from the original operational evidence export. It used a PostgreSQL `REPEATABLE READ, READ ONLY` transaction and `persist=false`; it did not rerun the lifecycle review, persist a DQ event, modify business records, or start sync. At 2026-10-21 12:37:47 UTC it returned 65 gates: 61 PASS, 4 WARNING, 0 FAIL.

The four warning gates are `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION` (782 Invest Saudi records), `OPEN_REVIEW_BACKLOG` (578 open cases at this reconciliation), `SOURCE_LAST_SUCCESS_TOO_OLD` (one aggregated gate covering four source IDs: MODON 6, NCP 7, NHC 8, MWAN 10), and `SYNC_RUNTIME_ANOMALY` (a separate gate for completed Job 393). Thus four sources plus Job 393 do not mean five warning gates: the four sources are samples under one gate. All four gate records and actions are in [dq-warning-reconciliation.json](dq-warning-reconciliation.json).

`DQ_WARNING_COUNT_RECONCILIATION = PASSED`; all four warnings are explained and unexplained warnings = 0. No source freshness, Job 393, or Job 212 data was changed. `MANUAL_SOURCE_SYNC_STARTED = FALSE`.
