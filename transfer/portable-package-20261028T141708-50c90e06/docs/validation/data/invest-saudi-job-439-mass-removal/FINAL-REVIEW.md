# Invest Saudi Job 439 Mass-Removal Integrity Review

**Project:** Al-Ahsa Investment Opportunities Platform  
**Review date:** 2026-10-22  
**Result:** COMPLETE

## Executive finding

Job 439 completed successfully and enumerated the full national Invest Saudi scope: 2,431 unique official IDs across four endpoints. Its reported `removed_records_count=2,423` was not a count of real source removals. Before the job, all 2,423 affected source rows were already marked `أزيلت من المصدر`; Job 439 saw every one of them in the national scan, but the adapter returned only the eight Al-Ahsa-qualified rows to the service's presence set. The service therefore treated the other 2,423 present-but-unqualified rows as absent and recounted them.

The actual new source-lifecycle removal transitions attributable to Job 439 were **0**. The 2,423 erroneous lifecycle labels were corrected to `غير محددة` only after this cause and the full affected ID set were proven. Raw payloads, source identities, observation history, Master identities, and merge lineage were retained. A separate, valid three-miss reconciliation deactivated nine stale `Investment projects` dataset memberships; those are not source-row removals and are not part of the 2,423 counter.

## Fixed live snapshot and Job 439

Snapshot captured at `2026-10-22 12:39:44 UTC` after correction:

| Measure | Value |
|---|---:|
| Master rows / current / merged | 547 / 526 / 21 |
| SourceOpportunity rows / Invest Saudi | 3,138 / 2,555 |
| Invest Saudi lifecycle: `أزيلت من المصدر` / `غير محددة` | 124 / 2,431 |
| Invest Saudi linkage: unlinked / current Master / merged Master | 2,536 / 19 / 0 |
| Observations | 21,538 |
| Open reviews | 498 (10 duplicate, 15 location, 0 qualification, 473 conflict) |
| Sync jobs | 443 |
| Active queued/running/retrying jobs at final status read | 0 |

Job 439: source `استثمر في السعودية` (Invest Saudi), job status `SUCCESS`, state `COMPLETED`, trigger `scheduled`; queued `2026-10-22T12:01:09.005461Z`, started `12:01:09.186402Z`, completed `12:03:25.553162Z`, duration 136.36676 seconds. Celery task `84da562d-eaa0-4f7a-b5ef-f453cf6d8881`, correlation `5659faf477da4ddfb8e1e0299334121e`, worker `dd94af8a1408:9`, attempt 1, no error. Scan complete was true: 26/26 aggregate pages, 2,431 records received, parsed, and unique official IDs. Counters were created 0, updated 0, unchanged 8, reported removed 2,423; 2,407 rejected, 8 active, 16 location-review count. Job-window observations: 2,547; reviews created/resolved/reopened: 0/0/0. Retry count was not stored separately.

`SUCCESS`, `COMPLETED`, and `scan_complete=true` all hold for this job, and the pre-fix implementation did enter removal reconciliation. In the current implementation, task completion alone is insufficient: all expected endpoint and pagination checks plus scope and population guards must pass before reconciliation.

## Scope, datasets, pagination, and identifiers

The same four unfiltered national GET endpoints were used by Job 411 and Job 439, with `page` and `per_page=100`; no location, date, or status request filters were applied. Al-Ahsa qualification is a later evidence-based filter used to decide which records can enter the local Al-Ahsa Master population. It must not define national source presence.

| Dataset / endpoint | Job 411 | Job 439 | Delta | Pages Job 439 |
|---|---:|---:|---:|---:|
| Opportunities | 1,771 | 1,771 | 0 | 18/18 |
| Investment projects | 338 | 338 | 0 | 4/4 |
| PIF opportunities | 184 | 184 | 0 | 2/2 |
| Regional opportunities | 138 | 138 | 0 | 2/2 |
| **Total** | **2,431** | **2,431** | **0** | **26/26** |

All four endpoint collectors completed; aggregate received/parsed/unique counts match the reported endpoint totals. Failed pages, unexpected empty pages, missing ranges, parse failures, duplicate IDs, and duplicate endpoint memberships were 0. Exact HTTP response codes and per-endpoint successful-page counters were not retained; the adapter raises on non-2xx and the completed job's aggregate pagination evidence is retained. No dataset returned zero or a reduced population.

The immediately previous successful complete Invest Saudi enumeration was Job 411 (completed `2026-10-21T12:02:39.153637Z`); Job 438 was a different source. Job 411 and Job 439 each had 2,431 unique IDs: intersection 2,431, previous-only 0, Job-439-only 0. No missing or duplicate official IDs were found. The extraction/normalization behavior (ID, else slug, else link; trim; normalize numeric IDs; case-fold other IDs; namespace with `investsaudi:`) was stable. The four endpoint scopes and filters were unchanged.

## Reconstruction and the 2,423-row set

The closest retained pre-run snapshot is the verified PostgreSQL dump `backups/20261022T074005Z-55451748.dump`, created 4 hours 21 minutes before Job 439; SHA-256 `d43bc8cb9883a63368caaf8f0191dd0ff134e70d5e038b0675c6176e16fc45d6`. Reconstruction confidence is **HIGH** for row identities and lifecycle values in that dump, and uses Job 411 last-seen evidence for the scan population; it is not an exact point-in-time snapshot at Job 439 start.

Before Job 439 there were 2,555 Invest Saudi rows: 2,547 already marked removed and 8 unspecified. Job 411 had seen 2,431 unique official IDs; 124 other IDs were historical and absent from the current Job 411 scope. All 2,423 counted rows were among the 2,431 IDs seen in both Job 411 and Job 439. Thus for the alleged removal set:

- Source rows counted: 2,423; unique official IDs: 2,423.
- Previously present -> removed: 0; already falsely removed -> counted again: 2,423.
- Noncomparable scope: 0; missing official IDs: 0; duplicate rows: 0; other: 0.
- Not seen in Job 439: 0; seen in immediately previous successful Invest Saudi scan: 2,423.
- National unlinked: 2,412; linked to current Masters: 11; Al-Ahsa-qualified: 0.
- Dataset split: Opportunities 1,765; Investment projects 336; PIF opportunities 184; Regional opportunities 138.

The raw payload status was null and the records were not Al-Ahsa-qualified; they should not have been treated as Al-Ahsa Master opportunities, but their national source identities were present. Following correction, the 2,423 rows are `غير محددة` with missing-confirmation count reset to zero. The other 124 rows remain historically removed because they were absent from the complete current-scope enumeration. No Invest Saudi source rows were physically deleted.

## Counter cause, remediation, and audit

Before the fix, the service constructed `seen_ids` from only the adapter's returned qualified records (8), while the adapter had enumerated and retained all 2,431 national `raw_candidates`. The 2,423 candidates omitted from the qualified return were processed as missing. The historical `removed_records_count` therefore counted candidates routed through that path rather than only persisted present-to-removed transitions. Its historical Job 439 value was not rewritten.

The service now builds Invest Saudi presence from every national `raw_candidate`, regardless of Al-Ahsa qualification, and reports `source_lifecycle_newly_removed_count` for actual new transitions. Reconciliation returns a row as removed only when its lifecycle really changes. The nine valid Investment-project membership deactivations are separate: each ID was missing in two earlier complete scans and reached its third confirmation in Job 439. Membership count changed 347 -> 338; source rows and official identities remain retained.

After proving the root cause, an audited transaction corrected the 2,423 false lifecycle flags and their missing-check state. Raw payloads were unchanged. Eleven linked current Masters had previously been projected from their sole Invest Saudi source row; their derived source status was corrected to `غير محددة`. No Master status changed during Job 439 itself, and no Master was cancelled solely because of source removal. SystemEvent 590 (`INVEST_SAUDI_JOB439_INTEGRITY_REMEDIATION`) stores the full per-row evidence ledger, raw-payload hashes, prior/current statuses, job reference, actor, timestamp, and Master projection details. The ledger is available in `mass-removal-remediation-ledger.json`.

## Future safeguards and quality checks

Invest Saudi reconciliation now validates all four expected endpoint identities, GET request shape, page size and parameters, per-endpoint completeness, successful pagination, and unexpected empty pages. It compares per-dataset population and third-miss candidate ID sets against up to five comparable successful scans; the allowance is the larger of one 100-row page and three median absolute deviations. A first scan exceeding that allowance is held and audited; a second complete scan can confirm only if scope signatures and the exact candidate source IDs match. Empty, failed, partial, or changed-scope datasets block reconciliation. Dataset membership remains endpoint-scoped, and three consecutive complete successful misses are still required. Source removal is not cancellation.

Read-only full live DQ after remediation and the final code deploy: 99 gates, 94 PASS, 5 WARNING, 0 FAIL. All seven removal safety gates passed; incomplete-scan removals, scope-mismatch removals, unreconciled removal counters, and Master cancellations from source removal were all zero. The five warnings are the existing generic source-page action warning (782 records; zero generic URLs exposed as opportunity actions), open-review backlog (498), legacy historical review audit metadata (120), one aggregated source freshness gate (MODON, NHC, and MWAN; NCP is not included), and Job 393 runtime anomaly. No new mass-removal warning was introduced. Invest Saudi source health at snapshot: technical `HEALTHY`, coverage `COMPLETE_PUBLIC_SOURCE`, freshness `HEALTHY`.

Focused tests: 37 passed, 0 failed (36 guard tests plus the Invest Saudi/Furas compatibility test). Full regression on an isolated temporary SQLite database: 474 passed, 0 failed; live PostgreSQL was not used by the suite. No source sync was manually started. Natural scheduled jobs 437–443 are retained with source labels, state, pagination counters, record counters, and timestamps in `natural-jobs-437-443.json`. No independent before-snapshots exist for deriving source, Master, observation, or review deltas for those jobs, so those deltas are marked unknown rather than inferred as zero.

## Required assertions

```text
INVEST_SAUDI_JOB_439_MASS_REMOVAL_INTEGRITY_REVIEW = COMPLETE
JOB_439_TECHNICAL_SUCCESS = TRUE
JOB_439_COMPLETE_ENUMERATION = TRUE
JOB_439_REMOVAL_LOGIC_ALLOWED_TO_RUN = TRUE
JOB_439_REPORTED_REMOVED = 2423
ACTUAL_NEW_REMOVAL_TRANSITIONS_ATTRIBUTABLE_TO_439 = 0
ALREADY_REMOVED_ROWS_COUNTED_AGAIN = 2423
NONCOMPARABLE_SCOPE_ROWS_COUNTED = 0
REMOVED_COUNTER_COUNTS_ONLY_NEW_TRANSITIONS = FALSE
PREVIOUS_INVEST_SAUDI_JOB_ID = 411
PREVIOUS_JOB_UNIQUE_OFFICIAL_IDS = 2431
JOB_439_UNIQUE_OFFICIAL_IDS = 2431
PREVIOUS_ONLY_IDS = 0
JOB_439_ONLY_IDS = 0
MULTI_DATASET_SCAN_COMPLETENESS_STRICT = TRUE
INVEST_SAUDI_PAGINATION_COMPLETE = TRUE
OFFICIAL_ID_EXTRACTION_CHANGED = FALSE
SOURCE_SCOPE_CHANGED = FALSE
SOURCE_FILTER_CHANGED = FALSE
PROVEN_FALSE_REMOVALS = 2423
POTENTIAL_FALSE_REMOVALS = 0
VALID_REMOVALS = 0
REMOVAL_COUNTED_NATIONAL_UNLINKED = 2412
REMOVAL_COUNTED_AL_AHSA_QUALIFIED = 0
REMOVAL_COUNTED_LINKED_TO_CURRENT_MASTER = 11
CURRENT_MASTERS_WITH_SOURCE_REMOVED_BY_439 = 0
MASTER_STATUS_CHANGED_DUE_TO_439 = 0
MASTER_CANCELLED_SOLELY_FROM_INVEST_SAUDI_REMOVAL = 0
JOB_439_REVIEW_CREATIONS = 0
JOB_439_REVIEW_RESOLUTIONS = 0
JOB_439_REVIEW_REOPENS = 0
PHYSICALLY_DELETED_INVEST_SAUDI_SOURCE_ROWS = 0
RAW_PAYLOADS_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MASS_REMOVAL_CONFIRMATION_REQUIRED = TRUE
DATASET_SCOPED_REMOVAL_COMPARISON = TRUE
PARTIAL_DATASET_CAN_TRIGGER_REMOVAL = FALSE
DQ_REMOVAL_ON_INCOMPLETE_SCAN = 0
DQ_SCOPE_MISMATCH_REMOVALS = 0
DQ_REMOVAL_COUNTER_UNRECONCILED = 0
DQ_MASTER_CANCELLED_FROM_SOURCE_REMOVAL = 0
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_IDENTITIES_PRESERVED = TRUE
MERGE_LINEAGE_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
FOCUSED_TESTS = 37 passed / 0 failed
FULL_REGRESSION_SUITE = 474 passed / 0 failed / RERUN
LIVE_DQ_TOTAL_GATES = 99
LIVE_DQ_PASS = 94
LIVE_DQ_WARNING = 5
LIVE_DQ_FAIL = 0
```

### Evidence files

The requested JSON evidence set is stored beside this report: Job snapshot and counter semantics, pre/post reconstruction, per-dataset and pagination comparisons, official-ID comparison, full 2,423-row population analysis and deterministic sample, Master/review impact, guard analysis, audited remediation ledger, live DQ result, and focused/full test results. Per-page HTTP codes, exact start-time snapshot, and independent pre/post deltas for natural non-Invest-Saudi jobs were not persisted and are explicitly treated as limitations.

