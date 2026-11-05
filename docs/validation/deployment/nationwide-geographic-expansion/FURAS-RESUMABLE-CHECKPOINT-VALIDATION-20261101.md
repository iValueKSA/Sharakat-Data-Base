# Furas Resumable Checkpoint Validation

**Date:** 2026-11-01 (Asia/Amman)  
**Result:** COMPLETE for isolated checkpoint validation. Production was not changed.

## Implementation

Checkpoint metadata is stored under SyncJob.metrics_json.furas_checkpoint. There is no new migration or competing lifecycle model. On a new run, the collector uses the current job's resumable checkpoint or adopts the most recent incomplete Furas checkpoint from a failed/abandoned attempt. It rebinds the checkpoint to the new job only after validating identity.

Identity includes:

- Source key and ArcGIS layer URL.
- Exact source WHERE filter, including current date cutoff.
- Enumeration scope (AL_AHSA_SUBSET_V1 or SAUDI_NATIONAL_V1).
- Collector and source-record schema versions.
- Batch size, ArcGIS service version/geometry metadata.
- Expected count and SHA-256 over deterministically ordered OBJECTIDs.
- A derived scope fingerprint over the identity above.

The checkpoint tracks scan_run_id, job_id, offset, batch/page, last committed page, last successful official source ID, records seen, unique processed official IDs, per-page payload hashes, row insert/update totals, scan start/update times, completion/terminal state, reconciliation eligibility, duplicate count, and resume/interruption evidence.

## Transaction and resume protocol

1. Query and validate the ArcGIS count and full OBJECTID set; sort IDs deterministically and form 100-ID batches.
2. For a resumed run, re-fetch every previously committed feature page and compare its canonical payload hash to the stored page hash. Reject resume on any changed or incomplete page.
3. Fetch the next batch and validate that every expected OBJECTID appears exactly once.
4. Upsert each SourceOpportunity through the existing ingestion rules. National checkpoint capture disables new Master creation while preserving existing deterministic matches.
5. Update the cursor, source-ID set, counters, and page hash in the same SQLAlchemy transaction.
6. Commit rows and checkpoint together. Only after commit does the adapter request the next page.
7. Before declaring completion, re-fetch every page and compare payload hashes, then repeat source count and ID enumeration. Any drift leaves the checkpoint incomplete and removals disabled.
8. Only a fully complete, verified checkpoint can enter the existing Furas scope/removal guard. Empty scans remain blocked by the existing empty-enumeration rule.

Failed jobs retain their last committed checkpoint as history. Retries/new jobs can resume from it. Scope, collector, schema, query, ID-set, or payload mismatch results in STALE_ACTION=REJECT; the checkpoint is not silently reset. A PostgreSQL session advisory lock per exact scope prevents concurrent owners across workers; the existing transactional ingestion advisory lock remains in use for each page.

The public ArcGIS layer returned no reliable edit timestamp. Page-content hashes, committed-page revalidation, final all-page revalidation, and a final count/ID re-enumeration provide the source-change barrier.

## Deterministic test evidence

Focused suite result: **101 passed, 1 skipped**. The skipped case requires an isolated PostgreSQL URL. It was run separately against the isolated PostgreSQL instance and passed.

| Case | Evidence |
|---|---|
| A: stop after first committed page | Cursor persisted at offset 100; next fetch was not requested. |
| B: halfway interruption | Synthetic 200-record scan stopped at 100/200, resumed, and completed with 200 unique official IDs. |
| C: failure before commit | Database rollback left zero rows and no advanced checkpoint; retry started from the same page. |
| D: failure after commit/before next fetch | First page rows and cursor persisted atomically; resumed run skipped the committed page. |
| E: worker/process restart | New sync job/process discovered the prior PostgreSQL checkpoint and resumed. |
| F: Redis restart/task retry | Redis was restarted after the real scan; PostgreSQL checkpoint rows remained intact. Worker heartbeat and post-restart DQ then passed. |
| G: scope mismatch | Resume validator rejects local/national scope mismatch. |
| H: collector version mismatch | Resume validator rejects changed collector version. |
| I: HTTP/feature request error | Fetch failure leaves cursor at the last committed page. |
| J: malformed/truncated page | Empty/missing expected OBJECTIDs fail page validation and do not advance the cursor. |
| K: duplicate official IDs | Duplicate official IDs are retained once, integrity warning recorded, completion false, removals disabled. |
| L: unexpected empty page | Scan fails incomplete without advancing that page. |
| M: final page | Completed scan reaches final offset and marks enumeration_complete=true. |
| N: partial removal attempt | Existing reconciliation helper refuses partial/incomplete evidence; partial removals remain 0. |
| O: completed reconciliation | Completed national scan enters existing source-presence and scope guards; 0 removals were warranted. |
| P: two owners | PostgreSQL advisory lock returns one owner; second same-scope worker is rejected until release. |

Additional checks confirm checkpoint advancement rejects committed=false, source snapshot changes reject old cursors, and the new FURAS_CHECKPOINT_INTEGRITY DQ gate fails a successful job carrying an incomplete cursor. Existing lifecycle transition tests continue to cover terminal monotonicity and atomic compare-and-set.

## Real isolated public scan

Database source: fresh verified backup restored into disposable PostgreSQL 16; migrations 0024 and 0025 applied explicitly to that isolated copy. No production database was used.

| Field | First attempt | Resumed attempt |
|---|---:|---:|
| Job ID | 674 | 675 |
| State | FAILED by controlled clean stop | SUCCESS / COMPLETED |
| Starting offset | 0 | 100 |
| Last committed offset | 100 | 6,494 |
| Completed batches | 1 | 65 total |
| Public source count | 6,494 | 6,494 |
| SourceOpportunity inserts in scan | 93 | 6,119 cumulative |
| SourceOpportunity updates in scan | 7 | 375 cumulative |
| Removals | 0 | 0 |
| New Masters | 0 | 0 |

Final uniqueness check: 6,555 Furas SourceOpportunity rows and 6,555 unique source IDs. Existing Furas links remained 436; qualification reviews remained 0; location reviews remained 1, equal to the restored pre-scan baseline. Master totals remained 587 overall / 566 current unmerged.

Final checkpoint for Job 675:

- scan_run_id: 1412c9e5c2ea4984030afc2ec331582f
- scope: SAUDI_NATIONAL_V1
- expected/seen/unique IDs: 6,494 / 6,494 / 6,494
- committed offset and page count: 6,494 and 65
- enumeration_complete: true
- source_generation_revalidated: true
- removal_reconciliation_allowed: true after the completed scan passed source-scope guards
- actual removals: 0
- duplicate official IDs: 0

## DQ and regression

The inline post-sync DQ initially ran before an isolated worker heartbeat was available and recorded API_WORKER_STANDARDIZATION_PARITY as a failure. The gate was not weakened. With an isolated maintenance worker and Redis running, a DQ-only run passed 54 gates, 0 warning, 0 fail. Redis was restarted; the checkpoint remained in PostgreSQL, the worker heartbeat was restored, and the post-restart DQ-only run again passed 54 gates, 0 warning, 0 fail (run ID d299fe0448cf4e27894005f54512b738).

Focused tests: 101 passed, 1 skipped; PostgreSQL advisory-lock test: 1 passed separately.  
Full regression: **645 passed, 1 skipped, 42 warnings**.  
Warnings were existing Starlette/httpx and Alembic deprecations.

## Production boundary

Production was verified read-only after isolated validation:

- Alembic remains 0023_quant_commercial.
- Migrations 0024 and 0025 remain NOT_APPLIED.
- Current lifecycle-patch API/worker/Beat tags remain deployed.
- Furas national runtime is not deployed.
- Furas national enumeration, national UI, and national map flags remain false.
- Production counts remained 3,180 SourceOpportunity rows; 587 Masters / 566 current Masters; 0 active jobs; maximum job ID 673.
- Manual production syncs, production data changes, and production schema changes: 0.

No production backfill was performed. The checkpoint implementation is ready for a separate artifact/deployment approval step; this validation task ends here.
