# Furas National Production Readiness

## Superseding recovery update — 2026-11-02

The previous production-readiness status predates the completed `local_user` recovery and is not the current live state. Job 692 remains unchanged and non-resumable. Recovery Job 694 completed after deployment of the snapshot membership/checkpoint preservation fix; full DQ passed with zero FAIL. The live API, Worker, and Beat now run the recovery image at `sha256:3ad925fef8999a11b073e152b1cb6abccc033636b952aeb569a9c4d07ec6a2da`, Alembic remains 0025, and readiness is HTTP 200. National UI/map and future national enumeration/removal controls remain disabled. See [FURAS-SNAPSHOT-STABILITY-RECOVERY-20261102.md](FURAS-SNAPSHOT-STABILITY-RECOVERY-20261102.md) for evidence and counts.

**Date:** 2026-11-01 (Asia/Amman)  
**Status:** PARTIAL for production rollout; resumable checkpoint implementation and isolated validation are complete.  
**Production changes in this task:** none. Production migrations, image deployment, flag changes, manual syncs, and backfill remain prohibited by the current task.

## Decision

The Furas nationwide collector now persists per-batch checkpoints in the existing SyncJob.metrics_json. Each page's SourceOpportunity upserts and cursor commit in one database transaction. A resumed scan validates exact source/scope identity, rechecks every committed page fingerprint before continuing, rechecks the full page set and final count/ID set before completion, and keeps removal reconciliation disabled until the complete snapshot passes integrity checks.

An isolated live interruption/resume succeeded. Production remains unchanged at 0023 with national runtime and flags off. This task deliberately stops before production.

## Current production state

Read-only verification after isolated validation reported:

| Measure | Value |
|---|---:|
| Alembic revision | 0023_quant_commercial |
| SourceOpportunity rows | 3,180 |
| Master rows / current unmerged Masters | 587 / 566 |
| Active sync jobs | 0 |
| Maximum sync-job ID | 673 |
| NATIONAL_UI_ENABLED | false |
| NATIONAL_MAP_ENABLED | false |
| FURAS_NATIONAL_ENUMERATION_ENABLED | false |

Images remain alahsa-api:lifecycle-fix-20261101, alahsa-worker:lifecycle-fix-20261101, and alahsa-beat:lifecycle-fix-20261101. No national runtime image was deployed. The existing shared lifecycle patch remains live; sync_source still finalizes through the shared atomic transition helper. No new Master, SourceOpportunity, review, audit, job-history, or schema changes were made in production.

## Backup and migration baseline

- Fresh production backup: backups/20261101T163551Z-furas-readiness.dump
- SHA-256: 439b6985c269c05a9289d8c7bd9df65e18a448d28ac9bab9a11acaf0f453491c
- Backup verification and restore test: **PASSED** in isolated PostgreSQL 16.
- Explicit isolated migration path: 0023_quant_commercial → 0024_national_geography → 0025_source_geographic_coverage: **PASSED**.
- Primary-key and selected canonical-field fingerprints matched before/after the isolated migrations.
- Production migrations 0024 and 0025: **NOT APPLIED**.

The checkpoint itself uses the existing JSON job-metrics column and adds no migration.

## Checkpoint design

The durable checkpoint is stored under SyncJob.metrics_json["furas_checkpoint"]; the source rows and cursor are committed in the same transaction. No parallel lifecycle system or checkpoint table was added.

Checkpoint fields include:

checkpoint_version, job_id, scan_run_id, source_key, layer_url, where, enumeration_scope, collector_version, source_record_schema_version, page_size, source generation metadata, expected count, sorted OBJECTID digest, scope fingerprint, current offset/batch, last committed offset/page, last successful source ID, records seen, unique source IDs processed, completed pages, per-page payload hashes, scan/checkpoint timestamps, completion state, terminal status, removal eligibility, duplicate count, row insert/update counters, and interruption history.

The public layer exposes no reliable edit-generation timestamp. The collector therefore hashes every feature page. On resume it rereads and validates all committed pages before starting at last_committed_offset. Before completion it rereads all feature pages, then repeats the count and OBJECTID enumeration. Any scope/filter/version/count/ID/payload mismatch rejects the cursor and leaves the scan incomplete; it does not silently restart with a stale checkpoint.

National capture calls the existing _safe_record path with Master creation disabled. Existing safe matches may remain linked; new Masters are not created. A session-level PostgreSQL advisory lock keyed by exact enumeration scope prevents two workers owning the same resumable scope simultaneously. The existing per-transaction ingestion lock remains in place for page writes.

## Isolated live interruption and resume

The fresh backup was restored into a disposable PostgreSQL environment, explicitly migrated to 0025 for current runtime compatibility, and run with national Furas enabled only inside that isolated environment.

| Attempt | Result |
|---|---|
| First run, Job 674 | Deliberately stopped after first committed batch. State FAILED, offset 100, page 1, 100 records processed, 93 SourceOpportunity inserts, 7 updates, 0 removals. |
| New process, Job 675 | Resumed from Job 674 at offset 100; completed at offset 6,494 after 65 total batches and full snapshot revalidation. |

Final isolated source result:

- Live public total: **6,494**; unique official Furas IDs: **6,494**.
- SourceOpportunity rows after scan: **6,555**, all unique.
- Job 675 cumulative inserts: **6,119**; updates: **375**; removals: **0**.
- New Masters: **0**; Masters remained 587 total / 566 unmerged.
- Furas-linked existing Masters remained 436; no additional source-to-Master links were created.
- Furas qualification reviews remained 0; Furas location reviews remained 1, unchanged from the restored baseline.
- Final checkpoint: COMPLETE; enumeration_complete=true, source_generation_revalidated=true, removal_reconciliation_allowed=true, last committed offset 6,494, 65 batches, no duplicate official IDs.
- The complete-scan removal check ran under existing source-presence rules and removed 0 rows. The interrupted first run removed 0.

The historical 6,494 count was not used as a code constant; the run used the live count/ID enumeration and compared the observed result to that live response.

## Interruption and safety tests

Focused Furas, lifecycle, ingestion, and DQ tests: **101 passed, 1 skipped**. The PostgreSQL-only advisory-lock test was then run against the isolated database: **1 passed**. The skipped test is the PostgreSQL lock test when a PostgreSQL test URL is not supplied; it passed separately against the isolated PostgreSQL instance.

Coverage includes:

- Commit-only cursor advancement; failure before commit leaves no page cursor.
- Stop after a committed page; new job resumes at the next safe offset.
- Halfway interruption of a 200-record synthetic scan resumes with 200 unique IDs and no duplicate rows.
- Worker/process restart and Redis restart leave the PostgreSQL checkpoint authoritative.
- Changed committed payload, changed source IDs, changed scope, and changed collector version reject resume.
- Feature-page truncation/empty page does not advance that page.
- Duplicate official IDs are deterministically deduplicated and make completion false.
- Final-page completion, partial-scan removal block, complete-scan removal guard, and concurrent PostgreSQL checkpoint ownership.
- Checkpoint DQ rejects a successful job carrying an incomplete checkpoint.
- Shared lifecycle monotonicity/CAS tests remain in regression.

Full regression after the implementation: **645 passed, 1 skipped, 42 warnings**. Warnings are existing Starlette/httpx and Alembic deprecations.

## Isolated DQ and Redis restart

The scan's immediate post-sync DQ ran before an isolated worker heartbeat was available and recorded one API_WORKER_STANDARDIZATION_PARITY failure. The DQ gate was not weakened. After starting the isolated worker and its Redis service, DQ-only validation passed **54 / 0 warning / 0 fail**. Redis was then restarted; the PostgreSQL checkpoints for Jobs 674 and 675 remained intact, the worker heartbeat was re-established, and a second post-restart DQ-only run again passed **54 / 0 warning / 0 fail** (run ID d299fe0448cf4e27894005f54512b738).

## Required status

~~~text
FURAS_RESUMABLE_CHECKPOINTS = COMPLETE (ISOLATED ONLY)
CHECKPOINT_PERSISTENCE = PASSED
CHECKPOINT_ADVANCES_ONLY_AFTER_COMMIT = TRUE
CHECKPOINT_SCOPE_MISMATCH_REJECTED = TRUE
STALE_CHECKPOINT_HANDLING = PASSED (REJECT; NO SILENT RESTART)
CONCURRENT_RESUME_COLLISION = PREVENTED
FURAS_RESUME_AFTER_INTERRUPTION = PASSED
ISOLATED_FURAS_NATIONAL_SCAN = PASSED
FURAS_PUBLIC_RECORDS_FOUND = 6494
UNIQUE_FURAS_SOURCE_IDS = 6494
SOURCEOPPORTUNITIES_INSERTED = 6119
SOURCEOPPORTUNITIES_UPDATED = 375
SOURCEOPPORTUNITIES_REMOVED = 0
NEW_MASTERS_CREATED = 0
PARTIAL_SCAN_REMOVALS = 0
CHECKPOINT_FINAL_STATE = COMPLETE
ISOLATED_DQ_FAIL = 0 (POST-RESTART DQ-ONLY RUN)
FOCUSED_TESTS = 101 PASSED / 1 SKIPPED; POSTGRES LOCK TEST 1 PASSED
FULL_REGRESSION = 645 PASSED / 1 SKIPPED
PRODUCTION_ALEMBIC_HEAD = 0023_quant_commercial
PRODUCTION_MIGRATION_0024 = NOT_APPLIED
PRODUCTION_MIGRATION_0025 = NOT_APPLIED
FURAS_NATIONAL_RUNTIME_DEPLOYED = FALSE
FURAS_NATIONAL_PRODUCTION_BACKFILL = NOT_STARTED
MANUAL_PRODUCTION_SOURCE_SYNCS = 0
BUSINESS_DATA_CHANGES_PRODUCTION = 0
PRODUCTION_SCHEMA_CHANGES = 0
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
~~~

**Final decision at the time:** checkpoint implementation and isolated validation are complete. The 2026-11-02 live-user rollout below supersedes the earlier stop statements for current environment state.

## 2026-11-02 controlled rollout attempt

The attached controlled deployment request initially stopped because the only running application stack identified itself as Compose project `alahsa-local` with `ENVIRONMENT=local_user`. The user then confirmed that this is the intended LIVE USER ENVIRONMENT. The earlier refusal to treat this environment as a deployment target is superseded by the confirmed terminology and subsequent authorized rollout documented below.

At the initial read-only inspection, API and readiness returned 200, frontend returned 200, PostgreSQL and Redis were healthy, worker ping returned `pong`, and Beat was running. The 2026-11-02 live-user rollout subsequently created a fresh backup, rehearsed restoration and migrations, deployed the approved runtime, applied 0024/0025 explicitly, and ran one manual Furas scan. That scan committed 65 pages and 6,483 unique provider IDs but failed final revalidation because source page 31 changed. It was not retried. Current disposition, status fields, counts, checkpoint state, and readiness limitation are in [FURAS-NATIONAL-LIVE-LOCAL-BACKFILL-20261102.md](FURAS-NATIONAL-LIVE-LOCAL-BACKFILL-20261102.md). Current API `/health/ready` is 503 while Beat is paused; national flags are off.

The first-national bootstrap removal guard is now covered by a regression test that seeds a successful local-scope job and an absent prior Furas row; the row is preserved and its missing counter remains zero. Focused test passed (1); the repository suite passed **645 tests, 1 skipped, 42 warnings**.

See [FURAS-NATIONAL-LIVE-LOCAL-BACKFILL-20261102.md](FURAS-NATIONAL-LIVE-LOCAL-BACKFILL-20261102.md) for the completed rollout record and exact status fields. The older [FURAS-NATIONAL-PRODUCTION-BACKFILL-20261102.md](FURAS-NATIONAL-PRODUCTION-BACKFILL-20261102.md) remains as historical evidence of the earlier stop and has been superseded for current state.

## 2026-11-02 confirmed LIVE USER ENVIRONMENT rollout — final state

The confirmed target is `alahsa-local` / `local_user`, not a separate hosted production environment. A fresh pre-migration dump was verified and restored in isolation; the restored snapshot migrated explicitly from 0023 through 0024 and 0025. The approved runtime retained the lifecycle fix and deployed checkpoint/national-source code. Live schema reached exactly `0025_source_geographic_coverage`.

One authorized manual Furas national capture ran as Job 692. It processed 6,483 unique provider IDs (65 committed pages; 6,109 inserts; 374 updates; zero removals), then failed complete-source revalidation when page 31 changed. The stale-error handler overwrote the detailed checkpoint with a rejection summary, leaving no committed offset or page fingerprints to resume safely. The job itself remains for audit; do not retry it. Masters remained 587 total / 566 current; no Masters were created. Post-capture DQ was not run because the capture failed and the task's stop condition applied. Beat remains paused, the Furas enumeration flag was restored to false, UI/map remain off, and current API readiness is 503 due to a stale worker-heartbeat check while Beat is paused. Fix and regression-test checkpoint preservation and investigate the source page drift before a future capture.
