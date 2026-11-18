# Furas baseline test failure disposition

**Date:** 2026-11-16  
**Scope:** isolated diagnosis; production read-only  
**Decision:** `FURAS_BASELINE_FAILURES=FORMALLY_DISPOSITIONED_OUTDATED_TEST_EXPECTATIONS`; the two original pytest cases remain failing as written and are not reported as passing. `KFU_RELEASE_GATE=CONDITIONAL_NON_REGRESSION_SUPPORTED; NOT_DEPLOYED`.

## Required status

- `FURAS_BASELINE_TEST_DISPOSITION=OUTDATED_SOURCE_ROW_COUNT_EXPECTATIONS`
- `TEST_A_ROOT_CAUSE=UNKNOWN_NATIONAL_IDS_ARE_QUARANTINED; TEST_EXPECTS_SOURCEOPPORTUNITY_INSERTS`
- `TEST_B_ROOT_CAUSE=REPLAY_CORRECTLY_QUARANTINES_UNKNOWN_IDS; TEST_EXPECTS_120_INSERTS`
- `BASELINE_TEST_RESULTS=EACH_TEST_FAILED_3_OF_3_ON_ORIGINAL_WORKER_IMAGE_USING_DISPOSABLE_POSTGRES`
- `CANDIDATE_TEST_RESULTS=EACH_TEST_FAILED_3_OF_3_ON_APPROVED_KFU_IMAGE_USING_IDENTICAL_DISPOSABLE_POSTGRES_FIXTURE`
- `TEST_ENVIRONMENT_EQUIVALENCE=PASS; SAME_TEST_COPY, INPUT, ENVIRONMENT, POSTGRES_SCHEMA_RESET, AND ASSERTIONS`
- `REAL_DATA_INTEGRITY_RISK=NONE_DETECTED_IN_THESE_SCENARIOS; NO_DUPLICATE_SOURCE_ROWS, MASTER_ROWS, OR_PARTIAL_PAGE_WRITES`
- `KFU_ADAPTER_CHANGE_IMPACT=KFU_ADAPTER_CLASS_ONLY; NO_FURAS_OR_SHARED_SYNC_CODE_CHANGED`
- `SOURCE_IDENTITY_RISK=NONE_INTRODUCED; SOURCE_IDENTITY_AND_QUARANTINE_IMPLEMENTATION_HASHES_MATCH_BASELINE`
- `TEST_HARNESS_FIX_REQUIRED=NO; TEMPORARY_DATABASE_HELPER_ADAPTATION_ONLY; ORIGINAL_ASSERTIONS_UNCHANGED`
- `ISOLATED_FIX_RESULTS=DISPOSITION_ASSERTIONS_PASSED_3_OF_3_PER_CASE_ON_BOTH_IMAGES; NO_SOURCE_OR_TEST_FILES_CHANGED`
- `EXISTING_FURAS_DEFECTS=NO_TRANSACTION_OR_IDENTITY_DEFECT_CONFIRMED; PER_RECORD_QUARANTINE_EVIDENCE_RETENTION_REMAINS_A_SEPARATE_OPEN_REVIEW_ITEM_BEFORE_NATIONAL_ACTIVATION`
- `FURAS_SAFETY_FLAGS=ENUMERATION_FALSE; REMOVALS_FALSE; RCU_SCHEDULED_SYNC_FALSE`
- `KFU_SPECIFIC_TEST_RESULTS=36_PASSED; BROADER_WORKER_ADAPTER_SUITE_104_PASSED_2_OPTIONAL_SKIPPED`
- `KFU_DEPLOYMENT_NON_REGRESSION_EVIDENCE=CONDITIONAL_SUPPORT; KFU_FIXTURES_PASS_AND_FURAS_BASELINE_BEHAVIOR_IS_IDENTICAL`
- `KFU_RELEASE_GATE_DECISION=CONDITIONAL_NON_REGRESSION_SUPPORTED; THIS_DIAGNOSIS_DOES_NOT_AUTHORIZE_DEPLOYMENT`
- `PRODUCTION_DATA_MUTATIONS=0`
- `PRODUCTION_DEPLOYMENT_STATUS=NOT_DEPLOYED`

## Reproduction method and repeatability

The original tests call `sync_source("furas")` with synthetic provider IDs `OFF-1` through `OFF-120` and set `FURAS_NATIONAL_ENUMERATION_ENABLED=true`, `FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED=false`. The tests' `make_db()` helper hard-codes in-memory SQLite. For the requested database comparison, a temporary out-of-tree copy changed only that helper to connect to a disposable PostgreSQL 16 database and drop/recreate its schema before each case. The test bodies and assertions were byte-for-byte unchanged. Identical test copies, fixtures, environment flags, and clean schema resets were used against the original Worker image and the approved KFU candidate. No runner joined the production network or used production credentials.

Each original test failed on each image in **3/3 runs** on PostgreSQL. The original SQLite executions had the same failing assertions on both images. A separate state-capture harness repeated the exact fixture flow 3 times per image; all six baseline/candidate scenario state pairs were identical. A diagnostic assertion set based on the existing national Furas quarantine contract passed 3/3 times for each scenario on both images. The original assertions were not edited, skipped, or marked as passing.

Evidence files in this directory contain full one-run pytest traces, all three repeated results per image, and before/after state snapshots for both images:

- [Baseline PostgreSQL failure traces](baseline-pg-failure-traces.log)
- [Candidate PostgreSQL failure traces](candidate-pg-failure-traces.log)
- [Baseline three-repeat results](baseline-pg-three-repeat-results.log)
- [Candidate three-repeat results](candidate-pg-three-repeat-results.log)
- [Baseline before/interruption/replay states](baseline-postgres-diagnostic-state.jsonl)
- [Candidate before/interruption/replay states](candidate-postgres-diagnostic-state.jsonl)

## Test A — interruption after a committed page

**Expected by the current test:** after the first committed page of 100, persist 100 new SourceOpportunity rows in addition to the preseeded `LOCAL-ABSENT` row, then persist 20 more on resume. Its first failing assertion expected 101 source rows; actual was 1.

**Observed on both images, 3/3:** before sync there was one source row (`LOCAL-ABSENT`), zero Masters and source observations, and one completed prior job. The controlled interruption occurred after page 1's callback committed. The failed job retained checkpoint offset 100/page 1, 100 processed provider IDs, `source_rows_inserted_total=0`, and `quarantined_records_total=100`. SourceOpportunity count remained 1; Master and SourceObservation counts remained 0. Resume succeeded at offset 120 with 120 processed IDs, zero inserted rows, 120 quarantined IDs, source count 1, and Master/SourceObservation counts 0. The pre-existing local row and its missing-check count were unchanged.

The KFU-independent behavior is consistent: page progress was durable after the controlled post-commit interruption; resumption used the checkpoint and did not duplicate provider IDs or create Masters. The test mistakes quarantined, unrecognized national IDs for records expected to be inserted.

## Test B — injected failure before page commit

**Expected by the current test:** after replay, persist 120 SourceOpportunity rows. Its failing assertion expected 120; actual was 0.

**Observed on both images, 3/3:** before sync there were zero source rows, Masters, SourceObservations, or jobs. The injected `_safe_record` exception occurred before the page callback could commit. The failed job had no Furas checkpoint; source rows, observations, and Masters remained zero. After removing the fault, replay succeeded through 120 IDs, with `source_rows_inserted_total=0`, `quarantined_records_total=120`, and source/observation/Master counts still zero. No partial source row or checkpoint from the failed attempt remained.

The failure assertion is again incompatible with national quarantine: replay correctly processes and counts these unknown IDs without creating SourceOpportunity or Master records.

## Contract evidence and proposed expectation change

`app/furas_identity_quarantine.py` calls the exact-key/approved-alias resolver. A `NOT_FOUND` national provider ID returns a `QUARANTINE` decision (`UNRECOGNIZED_PROVIDER_ID`) without persistence. In `app/service.py`, a quarantine decision increments the checkpoint's quarantine count and skips `_safe_record`'s normal persistence path. The separate `tests/test_furas_identity_quarantine.py` explicitly asserts that an unknown national ID creates no SourceOpportunity or SourceObservation, does not flush unrelated pending ORM state, and leaves the Master unchanged. Thus the current row-count expectations in the two failing sync tests contradict the accepted safety contract.

Proposed test update, without weakening transaction or identity guarantees:

1. **Test A:** assert source count stays 1 and only `LOCAL-ABSENT` remains; Master count stays 0; first committed checkpoint is offset 100 with 100 processed/quarantined and 0 inserted; replay completes at offset 120 with 120 processed/quarantined and 0 inserted; no removals or changes to the old row.
2. **Test B:** assert the injected pre-commit failure leaves zero source rows, zero Masters, and no checkpoint; replay completes at offset 120 with 120 processed/quarantined and 0 inserted; source and Master counts remain zero.

These expectation changes would test the intended page/cursor transaction behavior and unknown-ID quarantine rather than require unsafe insertion. No test file has been changed in this task.

## Candidate comparison

The full production-to-candidate `app/adapters.py` diff is limited to `KfuAdapter` implementation and its parser version. Shared adapter base classes, Furas adapter code, source identity resolution, service transaction boundaries, page callbacks, retry behavior, and task behavior did not change. The diff adds top-level KFU panel parsing, panel-scoped document associations, listing-only provenance, and ambiguity fail-closed handling.

Exact SHA-256 comparisons for `service.py`, `tasks.py`, `furas_identity_quarantine.py`, `geography_flags.py`, and `celery_app.py` matched between the original production Worker and candidate. The tested Furas states were also identical. KFU-specific tests passed (36); the broader source/adapter suite passed 104 with 2 optional alias database tests skipped. An expanded combined run had 181 passed, 4 skipped, and these same 2 count-assertion failures. Neither failed pytest case is classified as PASS.

The failures do not demonstrate a KFU-induced Furas regression or a transaction/identity integrity defect. They are invalid source-row count expectations for intentionally quarantined unknown national IDs. A separate review item remains: the quarantine decision is intentionally non-persistent per record, and the checkpoint retains counts and processed IDs rather than a durable per-record review payload. This was not changed; before national enumeration is ever enabled, confirm the approved evidence-capture workflow is sufficient for adjudication.

## Production state and release decision

Read-only production checks found the Worker still on the original image/parser, API healthy, frontend HTTP 200, Worker ping successful, empty active/reserved/ETA-scheduled lists and zero messages in the three worker queues. Migration head remains `0027_opportunity_documents_mvp`; Master count 6,680; SourceOpportunity count 9,470; Furas aliases 75; document rows 0. SourceOpportunity 2774 -> Master 225 and 2928 -> Master 326 remain unchanged. Furas national enumeration, Furas removal reconciliation, and RCU scheduled sync all read `false`. No service was tagged, stopped, recreated, or restarted; no production sync or data write occurred.

**Disposition:** the two baseline tests are formally explained by outdated expectations, not accepted as passing. KFU non-regression evidence supports a conditional release recommendation because the candidate changes only the KFU adapter and its KFU/shared-adapter tests pass. This is not deployment authorization. Any later deployment must retain the explicit test disposition and this open pre-activation evidence-retention review item. The original pytest assertions should be corrected in a separate test-only change before a future broad Furas regression suite is described as passing.

**Final:** `FURAS_BASELINE_FAILURES=FORMALLY_DISPOSITIONED`; `KFU_RELEASE_GATE=CONDITIONAL_NON_REGRESSION_SUPPORTED`; `PRODUCTION_DEPLOYMENT_STATUS=NOT_DEPLOYED`; `PRODUCTION_DATA_MUTATIONS=0`.
