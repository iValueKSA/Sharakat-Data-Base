# Furas Job Lifecycle Ordering Race Fix — 2026-11-01

## Result

The shared sync-job lifecycle now uses guarded, atomic state transitions. A stale worker, scheduler recovery path, or cancellation request cannot move a terminal job back into an active state. Successful service finalization records the terminal status, terminal state, and finish time together before the sync-job consistency DQ check runs.

The fix is implemented and validated in isolated tests. It has not been deployed to production, so live Furas verification remains pending. No manual source sync, backfill, production write, or migration was performed for this task.

## Root cause and ordering

Inspection of the service and worker code confirmed two shared lifecycle defects:

1. In `sync_source`, the success status was visible to the same transaction while `job_state` was still `RUNNING` and `finished_at` was null. `evaluate_data_quality()` ran in that window. The consistency gate therefore observed and recorded the transient mismatch before the service wrote the terminal state and finish time. This explains a failing DQ observation even when the eventual job row was terminal and coherent.
2. After the service returned, the Celery worker redundantly wrote lifecycle fields. Retry handling could also take a failure row back to `RETRYING`. Stale recovery and queued-job cancellation had direct lifecycle writes without a state guard. Those stale writers could overwrite or regress a terminal state.

The service runs ingestion/reconciliation under the existing PostgreSQL advisory transaction lock. The advisory lock is acquired before source and opportunity writes. Before this fix, lifecycle fields were written through separate ORM assignments; there was no compare-and-set condition that made a terminal transition exclusive. In the success path, the DQ check ran before the terminal fields were finalized. The task worker then made another lifecycle write after service return. These ordering assumptions were not safe under overlapping worker/recovery activity.

No source-specific Furas behavior was added. The shared job lifecycle was corrected for all sources.

## State machine and transition guarantee

Active states are `QUEUED`, `RUNNING`, and `RETRYING`. Terminal states are `ABANDONED`, `FAILED`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `CANCELLED`, and `SKIPPED_ALREADY_RUNNING`.

Allowed transitions are centralized in `app/sync_lifecycle.py`:

| From | To |
| --- | --- |
| `QUEUED` | `RUNNING`, `ABANDONED`, `FAILED`, `CANCELLED`, `SKIPPED_ALREADY_RUNNING` |
| `RUNNING` | `RETRYING`, `ABANDONED`, `FAILED`, `COMPLETED`, `COMPLETED_WITH_WARNINGS` |
| `RETRYING` | `RUNNING`, `ABANDONED`, `FAILED` |
| Terminal states | No outbound transitions |

`transition_sync_job()` performs a guarded SQL `UPDATE` against the expected current state and atomically sets state, status, and—when terminal—`finished_at`. The update is a compare-and-set: only one writer from a given prior state can win. Repeating the same terminal finalization is harmless and preserves the original finish time. A losing stale ORM object does not flush over the winning row.

On success, service ingestion and review writes are flushed before the job-row compare-and-set. The transaction then writes the terminal lifecycle fields and invokes DQ, so the gate reads a coherent terminal state. The worker does not repeat successful finalization. Deferred worker failures remain `RUNNING` until the task chooses `RETRYING` or `FAILED` through the same guarded transition. Transaction rollback occurs before a retry/failure lifecycle update, releasing ingestion locks first.

## Deadlock interaction

The existing advisory-lock ordering is retained. The lifecycle row is not locked across opportunity ingestion or reconciliation writes: those writes are flushed before the terminal compare-and-set acquires the job row. DQ follows the terminal update and does not perform source ingestion. On a failed ingestion transaction, rollback releases transaction locks before the worker records retry/failure state. Deadlock retries therefore follow `RUNNING → RETRYING → RUNNING` without a terminal regression or a new lock inversion. Furas missing-record reconciliation remains fail-closed for incomplete/partial collection.

## Code and tests changed

- `app/sync_lifecycle.py` — centralized transition graph and atomic compare-and-set helper.
- `app/service.py` — finalizes success/warnings before DQ; uses guarded terminal transitions and supports deferred worker failure finalization.
- `app/tasks.py` — guarded claim, retry, failure, stale-recovery, and enqueue lifecycle writes; removed redundant successful finalization.
- `app/main.py` — queued cancellation uses guarded transition.
- `tests/test_sync_job_state_transitions.py` — stale writers, competing finalizers, idempotency, terminal monotonicity, partial/zero-page behavior, deadlock retry, and scheduler/worker overlap cases.
- `tests/test_sync_lifecycle_reliability.py` — retryable worker failure remains active while transitioning to `RETRYING`.
- `tests/test_data_quality.py` — valid terminal job passes and intentionally inconsistent synthetic job fails the unchanged consistency gate.
- `tests/test_ingestion.py` — verifies the lifecycle fields visible when DQ executes.

Three browser/map diagnostic scripts were confirmed temporary and unreferenced, then removed: `tests/helpers/diagnose_browser.cjs`, `tests/helpers/diagnose_map_popup.cjs`, and `tests/helpers/diagnose_map_reset_popup.cjs`.

## Validation

- Focused lifecycle, DQ, ingestion, nationwide safety, and production-security tests: **117 passed**, 36 warnings.
- Full regression, run once after the shared lifecycle changes: **633 passed**, 41 warnings, 77.52 seconds.
- The DQ consistency gate and its threshold/severity were not changed. Synthetic coherent terminal histories passed; an intentionally inconsistent history failed at severity `FAIL`.
- Deterministic stale-snapshot/competing-writer tests passed. These exercise overlapping writer orderings through the compare-and-set without relying on timing sleeps.
- Partial and zero-page scans produce coherent terminal outcomes and do not trigger removal reconciliation.

## Production read-only snapshot

After code work, a single read-only transaction (`SET TRANSACTION READ ONLY`, followed by rollback) against `alahsa-local-api-1` reported:

- Alembic revision: `0023_quant_commercial`.
- `NATIONAL_UI_ENABLED`, `NATIONAL_MAP_ENABLED`, `NATIONAL_DASHBOARD_ENABLED`, and `FURAS_NATIONAL_ENUMERATION_ENABLED`: all false.
- Active jobs (`QUEUED`, `RUNNING`, `RETRYING`): 0 at the snapshot.
- Historical rows inspected and not modified: jobs 644, 651, 652, 666, 668, and 669. Their observed states remained as stored: 644/651 `FAILED`; 652/666/668/669 `COMPLETED` (with successful status for 652/666/668/669).
- The live database had naturally generated jobs 670 and 671 by the time of inspection; 670 was an Al-Ahsa `retry` completed successfully and 671 was a Furas `retry` completed successfully. Neither was initiated by this task. These rows are not evidence that this code fix is live: production was not deployed or manually exercised.
- Read-only table counts at the snapshot: 11 sources, 587 opportunities, 3,180 source-opportunity links, 0 qualification reviews, 26 location reviews, and maximum sync-job ID 671. No task action wrote business or review data, created a job, or changed schema.
- No test geographic fixture was imported. No manual source sync or backfill was run.

The natural `retry` job rows are disclosed separately from the protected historical IDs; this task did not alter or retry jobs 651, 666, 668, or 669.

## Required status

```text
FURAS_JOB_LIFECYCLE_RACE_FIX = COMPLETE
ROOT_CAUSE = CONFIRMED
TERMINAL_STATE_IS_MONOTONIC = TRUE
ATOMIC_STATE_TRANSITIONS = TRUE
STALE_WRITER_CAN_REGRESS_TERMINAL_STATE = FALSE
CONCURRENCY_TESTS = PASSED
DQ_GATE_CHANGED = FALSE
SYNC_JOB_STATE_CONSISTENCY_SYNTHETIC_TEST = PASSED
FULL_REGRESSION = 633 PASSED
LIVE_FURAS_FIX_VERIFIED = FALSE
HISTORICAL_JOB_ROWS_CHANGED = 0
MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
BUSINESS_DATA_CHANGES = 0
REVIEW_DATA_CHANGES = 0
PRODUCTION_SCHEMA_CHANGES = 0
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
NATIONAL_UI_ENABLED_PRODUCTION = FALSE
NATIONAL_MAP_ENABLED_PRODUCTION = FALSE
TEMP_DIAGNOSTIC_SCRIPTS = REMOVED
```
