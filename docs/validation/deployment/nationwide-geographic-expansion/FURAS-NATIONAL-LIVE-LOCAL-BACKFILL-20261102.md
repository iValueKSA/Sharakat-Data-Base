# Furas National Live User Environment Capture — 2026-11-02

## Superseding recovery status — 2026-11-02

The initial Job 692 capture described below is now followed by a successful controlled recovery. Job 692 remains an immutable historical failure and was not resumed. A post-692 backup was restore-tested; snapshot/checkpoint fixes were deployed; new Job 694 completed against 6,484 persisted ArcGIS object IDs with 1 insert, 6,483 updates, zero removals, zero new Masters, and zero duplicate Furas provider keys. Pre- and post-capture full DQ each reported 130 pass, 4 warnings, and 0 fail. The patched API, Worker, and Beat are running; `/health/ready` is HTTP 200. Beat is restored, with future national enumeration and removal reconciliation disabled. A naturally scheduled AlAhsa Opportunities Job 693 occurred during repair before the controlled scan; no additional sync job appeared after Beat was restored. Full details: [FURAS-SNAPSHOT-STABILITY-RECOVERY-20261102.md](FURAS-SNAPSHOT-STABILITY-RECOVERY-20261102.md).

**Result: PARTIAL — the one authorized nationwide capture committed its pages but failed final source-generation revalidation.** The run stopped after that failure. No retry, resume, Master promotion, other manual source sync, or post-capture DQ run was performed.

## Target and safety boundary

The target was the confirmed live user environment: Compose project `alahsa-local`, `ENVIRONMENT=local_user`, URL `http://localhost:8080`, database `sharakat_local`. No environment-mode change was made. National UI/map/dashboard flags remained false. The capture used one manual Furas dispatch only. Source rows remain unpromoted; no new Masters or bootstrap removals were made.

## Fresh backup, rehearsal, and rollback

The live database was backed up immediately before migration:

| Item | Value |
|---|---|
| Backup | `backups/20261102T070412Z-furas-live-pre0023.dump` |
| Created (UTC) | `2026-11-02T07:04:17.069074+00:00` |
| Size | 15,275,213 bytes |
| SHA-256 | `c5848b2311bf8dbab345d4bf7c410fc6fabcbfec8acd95f5cfcfb96b249c8adf` |
| Backup revision | `0023_quant_commercial` |
| Archive validation | Passed; 346 entries |
| Isolated restore | Passed into disposable PostgreSQL 16 instance |

All pre-migration table fingerprints, primary-key sets, and schemas matched between the live snapshot and restored copy. On the restored copy only, migrations `0024_national_geography` then `0025_source_geographic_coverage` applied successfully. Existing business IDs/data remained identical; added geography fields were NULL and the three new geography tables were empty. Alembic `check` still reports pre-existing baseline drift (`local_setup_state` and custom `*_prod` indexes); these objects were present in the pre-migration snapshot and were not introduced by 0024/0025.

Rollback was prepared before the live writes. Restore the three prior image IDs to roll back runtime; restore the fresh pre-migration dump if database rollback is required. No rollback was executed.

## Runtime and live migration

The deployed API, Worker, and Beat image tag was `furas-national-live-20261102`; all three candidate images resolve to `sha256:5f9ffb43373dd836f0eaee9d08abc19bc25d6683f12c889cd6f885773bb5f7cf`. The image includes the lifecycle race fix, nationwide Furas enumeration, resumable checkpoints, geographic code, and the first-national-bootstrap removal guard. The separately built frontend image is `alahsa-local-frontend:furas-national-live-20261102`, digest `sha256:858270fadf4b28edcbc4219f5df785e9ab1b8586bf7e96e3ab49bfb9eef95c5c`.

Previous runtime image IDs recorded for rollback:

| Service | Previous image ID |
|---|---|
| API | `sha256:ae6560e822c65a3df27dc72576411d712f72816bca726b7e42b979012d933301` |
| Worker | `sha256:f87b2d1d7a974f9255304e3b40f3bf0c314417606de54e5dc6e5c521a936a097` |
| Beat | `sha256:87db93f8068221f75ea52fd26c29a5e957026bacb35e889a55a1d70b304613b0` |

Live migrations were applied explicitly and in order: `0024_national_geography`, then `0025_source_geographic_coverage`. Live Alembic head is exactly `0025_source_geographic_coverage`. No synthetic geography rows or coordinates were loaded. PostgreSQL and Redis persistent volumes were not stopped, deleted, or recreated.

The platform passed API/readiness, frontend, PostgreSQL, Redis, worker, and existing Al-Ahsa API checks before capture. After the capture failed, Beat was kept paused to prevent another scheduled attempt. The worker was restored to `FURAS_NATIONAL_ENUMERATION_ENABLED=false`; Celery ping returns `pong`. Current frontend root returns HTTP 200 and PostgreSQL/Redis remain healthy. Current `/health/ready` returns HTTP 503 because its worker-heartbeat check is stale while Beat is paused; this is recorded as a current health limitation, not a successful readiness result. No Furas task is active or queued. The API, worker, and frontend national UI/map/dashboard flags are false.

## DQ gates

Immediately before capture, the persisted live DQ run `14829b2377a5493288e006efe77eb101` recorded **130 pass, 4 warning, 0 fail**. Warning keys were `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`, `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`, `SOURCE_LAST_SUCCESS_TOO_OLD`, and `SYNC_RUNTIME_ANOMALY`.

Post-capture DQ was **not run**. The source scan failed final revalidation and the stop condition was followed. Do not interpret the pre-capture DQ as post-capture validation.

## Manual capture and checkpoint

Exactly one manual Furas job was dispatched:

| Field | Value |
|---|---|
| Job ID | `692` |
| Celery task ID | `1233bb01-d75a-4fc3-a9fd-7d16e4fe1c94` |
| Scope | `SAUDI_NATIONAL_V1` |
| Scope fingerprint | `06bbb2125e86a0ff394c54569beb1d660ada5ef1c4b8ba813fafbaa0dee24af7` |
| Started | `2026-11-02 07:15:51.628894+00:00` |
| Finished | `2026-11-02 07:18:05.648221+00:00` |
| Pages committed | 65 of the enumerated scan |
| Public source IDs found / received / parsed / unique | 6,483 / 6,483 / 6,483 / 6,483 |
| Inserted / updated / removed | 6,109 / 374 / 0 |
| Terminal state | `FAILED`; `pagination_complete=false`; no source total recorded |
| Error | `Source feature page changed during scan: 31` |

The persisted `metrics_json.furas_checkpoint` was inspected. It records `enumeration_complete=false`, `removal_reconciliation_allowed=false`, and the page-31 stale rejection. The exception handler replaced the detailed checkpoint object with this rejection summary: the job no longer contains the last committed offset, processed-ID list, or page fingerprints. The job columns still record 65 pages and 6,483 unique records, but these counters are not enough to resume safely. **Checkpoint final state: FAILED; detailed resumable checkpoint was lost on stale-error handling.** Job 692 itself remains preserved; no retry, cursor reset, or new job was started. This is a code defect to fix and regression-test before any future capture.

The committed Furas provider key is stored in `source_opportunity_id` (raw payload `OPPORTUNITYID`). The final table contains 6,545 Furas rows and 6,545 distinct provider keys; duplicate provider-key groups: 0. The separate `official_source_id_original` and normalized columns are not populated by this adapter and were not used for the uniqueness check.

## Data state and activity separation

| Measure | Before | After | Change attributable to Job 692 |
|---|---:|---:|---:|
| SourceOpportunity | 3,180 | 9,289 | +6,109 inserted; 374 updated |
| Furas SourceOpportunity | 436 | 6,545 | +6,109 rows |
| Masters | 587 | 587 | 0 |
| Current Masters | 566 | 566 | 0 |
| Source observations | 35,626 | 42,109 | +6,483 |
| Qualification reviews | 0 | 0 | 0 |
| Location reviews | 26 | 26 | 0 |
| Sync jobs | 690 | 692 | 1 manual Furas job; 1 natural scheduled job |

Job 691 was a natural scheduled NCP task (`SUCCESS`, scheduled), created during runtime validation before the controlled Furas dispatch. It is separate from task-initiated changes. No other manual source sync was started. Active jobs after Job 692: 0. Source rows were not promoted, no new Master records were created, and no source rows were removed. Existing links for the original 436 Furas rows remain; all newly inserted national rows are unlinked.

## Required status

```text
LIVE_TARGET = alahsa-local
LIVE_ENVIRONMENT = local_user
FRESH_LIVE_BACKUP_VERIFIED = TRUE
FRESH_BACKUP_RESTORE_TEST = PASSED
FRESH_LIVE_SNAPSHOT_0023_TO_0025 = PASSED
RUNTIME_ROLLBACK_READY = TRUE
DATABASE_ROLLBACK_READY = TRUE
LIFECYCLE_FIX_PRESERVED = TRUE
CHECKPOINT_CODE_DEPLOYED = TRUE
LIVE_MIGRATION_0024 = APPLIED
LIVE_MIGRATION_0025 = APPLIED
LIVE_ALEMBIC_HEAD = 0025_source_geographic_coverage
LIVE_RUNTIME_DEPLOYED = TRUE
LIVE_PLATFORM_CURRENT_READINESS = NOT_READY (API /health/ready 503; worker heartbeat stale while Beat is paused)
LIVE_FURAS_NATIONAL_CAPTURE = PARTIAL
LIVE_FURAS_JOB_ID = 692
FURAS_PUBLIC_RECORDS_FOUND = 6483
SOURCEOPPORTUNITIES_BEFORE = 3180
SOURCEOPPORTUNITIES_AFTER = 9289
FURAS_SOURCE_ROWS_BEFORE = 436
FURAS_SOURCE_ROWS_AFTER = 6545
SOURCEOPPORTUNITIES_INSERTED = 6109
SOURCEOPPORTUNITIES_UPDATED = 374
SOURCEOPPORTUNITIES_REMOVED = 0
FIRST_NATIONAL_BOOTSTRAP_REMOVALS = 0
NEW_MASTERS_CREATED = 0
CURRENT_MASTERS_BEFORE = 566
CURRENT_MASTERS_AFTER = 566
DUPLICATE_FURAS_SOURCE_IDS = 0 (provider keys)
CHECKPOINT_FINAL_STATE = FAILED (stale rejection summary persisted; detailed cursor/page fingerprints unavailable)
PRE_CAPTURE_DQ_FAIL = 0
POST_CAPTURE_DQ_FAIL = NOT RUN (capture failed; stopped)
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED_AFTER_CAPTURE = FALSE
LIVE_ENVIRONMENT_MODE_CHANGED = FALSE
MANUAL_FURAS_LIVE_SYNCS = 1
OTHER_MANUAL_SOURCE_SYNCS = 0
FABRICATED_OPPORTUNITIES = 0
FABRICATED_COORDINATES = 0
BEAT_AFTER_CAPTURE = PAUSED
``` 

**Disposition:** leave Job 692 and its failure summary untouched for review. Do not resume this checkpoint or start another Furas scan. Before a future capture, investigate both the changing source page and the checkpoint-loss exception path; repair and test checkpoint preservation, then prepare a new controlled run. Keep Beat paused and national flags off while the API readiness check remains 503.
