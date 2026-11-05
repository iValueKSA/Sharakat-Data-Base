# Master 577 medium-inference DQ root-cause review

**Result: COMPLETE.** The focused review found a false failure in the contradiction gate. Master 577 is a valid medium-confidence commercial classification from an explicit cafe-concession title rule. Its stored inference has no competing sector evidence. The missing margin was not a contradiction; for a one-candidate rule, a cross-sector margin is not applicable.

## Master 577 snapshot and evidence

Master 577 (`AH-20261021130514-b6c27895`, Furas reference `06-26-183737-46007`) remains in canonical sector **تجاري**. Its linked source row is 3168. The title explicitly identifies a cafe concession at Al-Omran General Hospital. The one classifier-used signal was title phrase `مزايدة تأجير موقع مقهى`, rule `MED_TITLE_CAFE_CONCESSION`, weight 4.0. The description duplicates the title and was deduplicated; activity and sub-activity support commercial food service semantically but had no exact structured rule match; source sector and asset type are null.

The word `مستشفى` is a location/destination in `مقهى مستشفى`, not a healthcare investment purpose. The classifier explicitly suppresses this healthcare phrase in the cafe-location context. There is no source-sector disagreement, negative-evidence record, second-sector candidate, or strong competing-sector evidence. `STRONG_CONTRADICTION_EXISTS = FALSE`.

The Master and source record were read only. The sector is correct and remains unchanged. Classification timestamp is 2026-10-21 13:05:14 UTC; inference event #531 stored origin, engine version, confidence 0.852, rule, positive/negative evidence, evidence fields, and timestamp.

## Root cause and gate correction

The previous condition was:

```text
classification_origin == INFERRED_RULE_MEDIUM
AND (negative_evidence OR float(confidence_margin OR 0) < 3.0)
```

Thus a missing margin became `0.0` and was treated as a contradiction. The gate ignored whether a distinct competing sector existed. It could false-fail a single-signal/deterministic medium result. Master 577 is classified **D — DQ_GATE_NULL_HANDLING_BUG**.

The old event serializer in `app/service.py` also omitted optional scores and margin fields. For this Master the omission is not decision-critical: the controlled-relaxation engine auto-applies a medium result only when a single sector candidate is supported; multiple sector candidates go to `REVIEW_REQUIRED`. The stored margin is therefore not applicable, not lost migration data. At classification time the old implementation emitted a legacy score-minus-zero value for a single candidate, but that value was not a competing-sector margin. No numeric margin was backfilled or fabricated.

The corrected contradiction gate fails only on actual negative/competing-sector evidence or a distinct scored competing sector with an actual margin below 3. Provenance integrity is a separate gate. For legacy v1.0.0 medium records with no runner-up, the documented single-candidate apply contract makes margin `NOT_APPLICABLE`; core provenance remains checked. New v1.0.1 results explicitly return `confidence_margin = null` and `confidence_margin_applicability = NOT_APPLICABLE` for a single candidate, and `app/service.py` persists margin applicability and score fields when applicable.

`CONTRADICTION_GATE_ONLY_TESTS_CONTRADICTION = TRUE`

## Current-medium audit

A read-only scan found 37 current medium-confidence inferred records: the accepted 36-record controlled-relaxation cohort plus Master 577, created later by scheduled Furas Job 416. All 37 have a single supported sector under the applied engine contract, no nonempty negative evidence, and complete core provenance. One event lacks a stored margin; the 36 older cohort rows carry the legacy numeric value 4.0, which represented winner score minus an absent runner-up and is semantically non-applicable. No competing-sector margin was synthesized.

The reviewed 36-record cohort has 0 null stored margins, 36 semantically non-applicable margins, 0 strong contradictions, and 0 incomplete core provenance. The only null margin in the 37-row current population is Master 577.

## Focused live DQ

One focused live evaluation ran against PostgreSQL at 2026-10-22 07:05:06 UTC using a `READ ONLY` transaction and `persist=False`. All 37 fast-cadence gates passed: 37 PASS, 0 WARNING, 0 FAIL. `P2_MEDIUM_INFERENCE_WITH_STRONG_CONTRADICTION` observed 0; `MEDIUM_INFERENCE_PROVENANCE_INTEGRITY` observed 0. Protected counts were identical before and after: 547 opportunities, 3,138 source opportunities, 16,298 observations, 21 merge-audit rows, and 547 system events.

The prior stored post-sync DQ result had also shown an `API_WORKER_STANDARDIZATION_PARITY` failure while the worker heartbeat was unavailable. After the necessary API/worker update, the live read-only evaluation observed worker standardization version 21 and that gate passed. No unrelated DQ rule or business data was modified.

## Tests and deployment

Focused tests passed **45 / 0 failed**. The complete suite passed **343 / 0 failed** in a disposable SQLite container with networking disabled. One stale hardcoded deadline in the lifecycle test was made date-relative after the 2026-10-22 run showed its 2026-10-21 fixture date was already expired.

The API and worker were rebuilt and recreated to activate the code. No source sync was started manually. Scheduler, PostgreSQL, and Redis were not restarted. Master 577, other classifications, source identities, raw records, observation history, merge lineage, statuses, owners, locations, deadlines, quantitative fields, and review queues were not changed.

## Required assertions

```text
MASTER_577_MEDIUM_INFERENCE_DQ_ROOT_CAUSE_REVIEW = COMPLETE
MASTER_577_ROOT_CAUSE = DQ_GATE_NULL_HANDLING_BUG
MASTER_577_CURRENT_SECTOR = تجاري
MASTER_577_FINAL_SECTOR = تجاري
MASTER_577_CLASSIFICATION_VALID = TRUE
MASTER_577_STRONG_CONTRADICTION = FALSE
MASTER_577_PROVENANCE_VALID = TRUE
MASTER_577_CHANGED = FALSE
DQ_GATE_CAN_FALSE_FAIL_ON_MISSING_MARGIN = FALSE
CONTRADICTION_GATE_ONLY_TESTS_CONTRADICTION = TRUE
TOTAL_MEDIUM_CONFIDENCE_RECORDS = 37
MEDIUM_WITH_NULL_MARGIN = 1
MEDIUM_WITH_NON_APPLICABLE_MARGIN = 37
MEDIUM_WITH_ACTUAL_STRONG_CONTRADICTION = 0
MEDIUM_WITH_INCOMPLETE_PROVENANCE = 0
RECENT_MEDIUM_CLASSIFICATIONS_FOUND = 36
RECENT_MEDIUM_NULL_MARGIN = 0
RECENT_MEDIUM_STRONG_CONTRADICTION = 0
RECENT_MEDIUM_PROVENANCE_INCOMPLETE = 0
FABRICATED_CONFIDENCE_MARGINS = 0
P2_MEDIUM_INFERENCE_WITH_STRONG_CONTRADICTION = PASS
MEDIUM_INFERENCE_PROVENANCE_INTEGRITY = PASS
LIVE_DQ_TOTAL_GATES = 37
LIVE_DQ_PASS = 37
LIVE_DQ_WARNING = 0
LIVE_DQ_FAIL = 0
UNRELATED_DQ_FAILURES_MODIFIED = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
FOCUSED_TESTS = 45 passed / 0 failed
FULL_REGRESSION_SUITE = 343 passed / 0 failed
```

See the accompanying JSON files for the snapshot, reconstructed signals, competitor audit, provenance audit, 36-record cohort, gate analysis, live DQ output, test evidence, and change log.

