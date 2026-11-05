# Furas Job 666 — read-only lifecycle analysis

**Result:** `FURAS_JOB_666_ROOT_CAUSE = CONFIRMED`  
**Recovery executed:** `FALSE`

This investigation used read-only SQL transactions, Redis key/TTL inspection, existing DQ event records, and source inspection. No source job was run, retried, edited, or restarted. No DQ gate or historical event was changed.

## Job 666 lifecycle

| Observation | Value |
|---|---|
| Job / source | `666` / Furas (`source_id=1`) |
| Trigger | Scheduled; not initiated by this task |
| Started | `2026-11-01 12:08:03.911067 UTC` |
| Post-sync fast DQ started | `2026-11-01 12:08:53.730069 UTC` |
| Post-sync fast DQ completed | `2026-11-01 12:09:05.230518 UTC` |
| Job finished | `2026-11-01 12:09:05.640867 UTC` |
| Job state at final snapshot | `SUCCESS / COMPLETED`, `finished_at` populated |
| Pages / records | 5 / 5 pages; 375 unique records |
| Error | None |
| Worker | `f21e353c6d6f:9`; heartbeat at `12:09:05.692019 UTC` |
| Celery task ID / correlation ID | Both present |
| DQ result | 48 PASS, 0 WARNING, 1 FAIL; `SYNC_JOB_STATE_CONSISTENCY`, sample `[666]` |

The DQ run completed **410.349 ms before** the job's terminal `finished_at`. At the final read-only snapshot, Job 666 itself was coherent and terminal. There were no active sync jobs. Redis showed no source-sync lock, enqueue key, or scheduler leader key; the scheduler heartbeat and worker heartbeat were present with expiring TTLs. These are current infrastructure indicators, not per-job execution proofs.

## Root cause

The lifecycle gate evaluated the database snapshot while the job was still being finalized. In the sync completion path, `evaluate_data_quality(..., trigger="post_sync", persist=True)` runs in `app/service.py` around line 1443, before the same path assigns `job.job_state="COMPLETED"` and `job.finished_at` around lines 1448–1449. The DQ snapshot therefore sees a successful status paired with a still-running state and no finish timestamp. The job is set to its terminal state afterward.

The timing pattern recurred:

| Job | Source | DQ completed | Job finished | DQ sample |
|---:|---|---|---|---|
| 666 | Furas | 12:09:05.230518 | 12:09:05.640867 | 666 |
| 667 | Source 4 | 12:45:31.558458 | 12:45:31.635093 | 667 |
| 668 | Source 2 | 13:08:35.499082 | 13:08:35.562354 | 668 |
| 669 | Source 1 | 13:10:04.530074 | 13:10:04.589712 | 669 |

At the final snapshot, the latest DQ run for Job 669 had the same single failure and Job 669 itself was already `SUCCESS / COMPLETED`. This repeated short gap is consistent with a systematic lifecycle ordering race, not an active stuck Job 666 or a current lock/worker ownership conflict. The failure remains persisted and should not be erased or described as a clean DQ result.

## Prior jobs and operational context

- **Job 644, Furas:** `FAILED / FAILED`, deadlock while updating opportunity 249; terminal failure, not an active job.
- **Job 651, Furas:** `FAILED / FAILED`, deadlock while updating opportunity 249; terminal failure, not an active job.
- **Job 652, source 2:** `SUCCESS / COMPLETED`; its post-sync check also caught the transient lifecycle ordering window.
- **Jobs 667–669:** automatically scheduled, completed successfully, and each produced the same transient lifecycle-gate sample-before-finish pattern.
- Final production snapshot: 0 active jobs; Redis `scheduler:last_tick` and worker heartbeat present; no source-sync lock/enqueue or scheduler-leader key.

The scheduler remained independently active during the review. Jobs 668/669 and their DQ records were automatic activity, not task-initiated syncs. This task performed no manual sync, retry, source edit, job edit, DQ mutation, or recovery action.

## Safest future recovery

1. Review and separately approve an application change that persists the terminal job state, `finished_at`, and completion markers before the post-sync lifecycle DQ snapshot is evaluated. Preserve transactional integrity and existing failure semantics.
2. Deploy that code through the normal reviewed process with national Furas enumeration still disabled.
3. Validate the ordering in isolation. Then run an approved DQ-only check against the already completed state and verify `SYNC_JOB_STATE_CONSISTENCY` passes. Do not rerun or retry historical Jobs 644, 651, or 666 to clear their stored evidence.
4. Keep national Furas enumeration off until source-specific completeness, pagination/reconciliation scope, serialization, safeguards, and a separate explicit approval are satisfied.

No part of this future procedure was executed here.

## Final status

```text
FURAS_JOB_666_ROOT_CAUSE = CONFIRMED
FURAS_JOB_666_RECOVERY_ACTION = FIX_LIFECYCLE_ORDER_THEN_APPROVED_DQ_ONLY_VALIDATION
FURAS_JOB_666_RECOVERY_EXECUTED = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
```
