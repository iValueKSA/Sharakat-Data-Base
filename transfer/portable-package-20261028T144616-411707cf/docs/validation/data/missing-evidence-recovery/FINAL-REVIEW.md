# Missing Evidence Recovery & Review Enrichment — Final Review

**Status: COMPLETE**  
Snapshot captured: `2026-10-22T07:42:21Z`  
Manual source sync: **not started**

## Scope and disposition

The fresh read-only snapshot contained 498 open reviews: 151 previously classified as human review and 347 blocked by missing evidence. The 347 blocked cases were examined against current Master and SourceOpportunity fields, raw payloads, observations, linked sources, merge lineage, field provenance, documents, and existing review audit events.

| Disposition | Count | Treatment |
|---|---:|---|
| EVIDENCE_RECOVERED_AND_DETERMINISTIC | 0 | No case met every deterministic and safe-workflow condition. |
| EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED | 337 | Enriched and moved into the human priority dataset; all remain open. |
| SOURCE_RECHECK_REQUIRED | 9 | Remain open with the exact future evidence request recorded. |
| TRULY_UNAVAILABLE_EVIDENCE | 0 | No case was declared unavailable when retained source context or a future recheck path existed. |
| WRONG_BLOCKED_CLASSIFICATION | 1 | Exact Invest Saudi–Furas identity evidence means this was not a missing-location-evidence case; it remains open for safe review. |
| OTHER_EXPLAINED | 0 | — |

The 332 Furas duration records retain values such as `366`, but the source’s duration unit and contract semantics remain unverified. The two Invest Saudi investment records retain literal `investmentSize=0`; no amount, currency, or zero-sentinel meaning was inferred. Five Invest Saudi location cases have description-only Al-Ahsa references below the accepted location confidence threshold. Seven AHDA records establish source scope but not the project site. Review 17 links to an Al-Ahsa-filtered Furas opportunity by exact opportunity number and the Master already has Al-Ahsa location evidence; the current location-acceptance workflow can reproject canonical fields, so no automatic decision was made.

## Evidence and audit

- Cases with attributable evidence/context: **338 / 347 (97.41%)**.
- Observation history was checked across the retained records. **0** values were historical-only; observations corroborated current raw evidence and were not silently promoted to canonical values.
- **17** blocked reviews had linked records from more than one source. One source’s missing field was not treated as a conflict; the exact-reference link for review 17 is recorded separately.
- **14** blocked reviews had merge lineage. No predecessor-only value was inherited; current linked source evidence was sufficient for context.
- **0** additional unmapped raw fields safely resolved a blocked canonical field. Inspected candidates and reasons are recorded in `unused-raw-field-analysis.json`.
- Appended **347** idempotent `REVIEW_EVIDENCE_ENRICHED` audit events with source, SourceOpportunity, observation where applicable, raw field/value, timestamp, evidence role, and reliability. Original review evidence and raw source payloads were not overwritten.
- A second unchanged enrichment run appended **0** events; DQ duplicate and provenance gates both passed.

## Before/after reconciliation

| Measure | Before | After |
|---|---:|---:|
| Open reviews | 498 | 498 |
| Human review required (task disposition) | 151 | 489 |
| Blocked by missing evidence (task disposition) | 347 | 9 |
| Auto-resolved | — | 0 |
| Reclassified from blocked to human review | — | 338 |
| Review reduction | — | 0 (0.00%) |

The remaining open review rows retain their existing OPEN/PENDING status. The human/blocked counts above are the enriched priority-dataset classifications. No opportunity, source, observation, merge, or review row was created, deleted, or rewritten. The only database additions were append-only evidence audit events.

Business counts stayed constant: 526 current Masters, 547 total Masters, 3,138 SourceOpportunity records, 16,298 observations, 21 merged Masters, 498 open reviews, and 428 sync jobs. Latest job remained scheduled job 428; no sync job was started during this task.

## Live full DQ

`scope=full`, read-only transaction, 78 gates: **74 PASS / 4 WARNING / 0 FAIL**. All six review-evidence gates passed:

- `RECOVERED_EVIDENCE_WITHOUT_PROVENANCE = 0`
- `DUPLICATE_REVIEW_EVIDENCE_ATTACHMENT = 0`
- `AUTO_RESOLUTION_WITHOUT_RECOVERED_EVIDENCE = 0`
- `BLOCKED_REVIEW_WITH_EXISTING_SUFFICIENT_EVIDENCE = 0`
- `REVIEW_EVIDENCE_PROVENANCE_BROKEN = 0`
- `EVIDENCE_ENRICHMENT_IDEMPOTENCY = 0`

The four unrelated warnings were retained and explained:

1. `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`: 782 records link only to a generic official page.
2. `OPEN_REVIEW_BACKLOG`: 498 legitimate open reviews remain.
3. `SOURCE_LAST_SUCCESS_TOO_OLD`: source IDs 4, 6, 8, and 10 (Invest Saudi, MODON, NHC, and MWAN).
4. `SYNC_RUNTIME_ANOMALY`: scheduled job 393 is surfaced for inspection.

No source freshness setting or job record was changed.

## Future reevaluation, tests, and UI

Targeted evidence reevaluation now runs for the affected source record/Master after source observations or links, source reappearance, merges/merge undo, and changed source taxonomy mappings. It appends only new evidence and does not scan the full review backlog or change canonical values. Repeated evidence is deduplicated by stable fingerprint.

- Focused evidence-recovery tests: **38 passed / 0 failed**.
- Full isolated regression: **388 passed / 0 failed** (SQLite in-memory).
- Playwright: **NOT_APPLICABLE**; no UI was changed.
- API readiness after rebuilding API and worker: database, Redis, and worker all healthy.

## Required assertions

```text
MISSING_EVIDENCE_RECOVERY_REVIEW_ENRICHMENT = COMPLETE
OPEN_REVIEWS_BEFORE = 498
BLOCKED_BY_MISSING_EVIDENCE_BEFORE = 347
HUMAN_REVIEW_REQUIRED_BEFORE = 151
CASES_WITH_ANY_EVIDENCE_RECOVERED = 338
EVIDENCE_RECOVERY_RATE = 97.41%
EVIDENCE_RECOVERED_AND_DETERMINISTIC = 0
EVIDENCE_RECOVERED_BUT_HUMAN_REVIEW_REQUIRED = 337
SOURCE_RECHECK_REQUIRED = 9
TRULY_UNAVAILABLE_EVIDENCE = 0
WRONG_BLOCKED_CLASSIFICATION = 1
OTHER_EXPLAINED = 0
EVIDENCE_RECOVERED_FROM_OBSERVATION_HISTORY = 0
BLOCKED_REVIEWS_WITH_MULTISOURCE_EVIDENCE = 17
EVIDENCE_RECOVERED_FROM_MERGE_LINEAGE = 0
UNUSED_RAW_FIELDS_DISCOVERED = 0
AUTO_RESOLVED_FROM_RECOVERED_EVIDENCE = 0
BLOCKED_TO_HUMAN_REVIEW = 338
ENRICHED_HUMAN_REVIEWS = 338
OPEN_REVIEWS_AFTER = 498
BLOCKED_BY_MISSING_EVIDENCE_AFTER = 9
HUMAN_REVIEW_REQUIRED_AFTER = 489
OPEN_REVIEW_REDUCTION = 0
OPEN_REVIEW_REDUCTION_PERCENT = 0.00%
RECOVERED_EVIDENCE_WITHOUT_PROVENANCE = 0
AUTO_RESOLUTIONS_WITHOUT_RECOVERED_EVIDENCE = 0
ORIGINAL_REVIEW_EVIDENCE_OVERWRITTEN = 0
FABRICATED_EVIDENCE_ITEMS = 0
RECOVERED_EVIDENCE_WITHOUT_TIMESTAMP_OR_SOURCE = 0
SECOND_RUN_NEW_EVIDENCE_ITEMS = 0
SECOND_RUN_NEW_AUTO_RESOLUTIONS = 0
SECOND_RUN_DUPLICATE_EVIDENCE_ATTACHMENTS = 0
SECOND_RUN_UNEXPECTED_CHANGES = 0
EVIDENCE_ENRICHMENT_IDEMPOTENT = TRUE
TARGETED_EVIDENCE_REEVALUATION = TRUE
DQ_RECOVERED_EVIDENCE_WITHOUT_PROVENANCE = 0
DQ_AUTO_RESOLUTION_WITHOUT_EVIDENCE = 0
DQ_BLOCKED_WITH_SUFFICIENT_EVIDENCE = 0
DQ_DUPLICATE_EVIDENCE_ATTACHMENTS = 0
LIVE_DQ_TOTAL_GATES = 78
LIVE_DQ_PASS = 74
LIVE_DQ_WARNING = 4
LIVE_DQ_FAIL = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_IDENTITIES_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MERGE_LINEAGE_PRESERVED = TRUE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FOCUSED_EVIDENCE_RECOVERY_TESTS = 38 passed / 0 failed
FULL_REGRESSION_SUITE = 388 passed / 0 failed
BROWSER_VERIFICATION = NOT_APPLICABLE
```

## Read-only follow-up after scheduled jobs

A fresh read-only snapshot was captured at **2026-10-22T08:25:48Z** (11:25:48 Asia/Amman). The review population and case membership match the enrichment snapshot: **498 open / 151 human / 347 blocked**, with **0 added** and **0 removed** blocked review IDs. The current breakdown remains 334 standardization and 13 location reviews; no classification or enrichment rerun was performed.

Two natural scheduled jobs completed since the 08:00:44Z business-count baseline. Both reported zero new and zero updated source opportunities:

| Job | Source | Status | Master delta | Source-opportunity delta | Observation delta | Open-review delta |
|---:|---|---|---:|---:|---:|---:|
| 429 | Furas | SUCCESS, scheduled | 0 | 0 | +35 | 0 |
| 430 | Al-Ahsa Opportunities | SUCCESS, scheduled | 0 | 0 | +19 | 0 |

Overall business counts now are 526 current Masters, 547 total Masters, 3,138 SourceOpportunity rows, 16,352 observations, 21 merged Masters, 498 open reviews, and 430 sync jobs. Against the prior live count snapshot, only observations (+54) and scheduled-job rows (+2) changed. The source observations triggered the existing targeted reevaluation hook; it appended 412 provenance-backed review-evidence audit events (759 total) and changed no business or review rows. This was natural scheduled processing; **MANUAL_SOURCE_SYNC_STARTED = FALSE**.

The current read-only full DQ evaluation contains **83 gates: 76 PASS / 4 WARNING / 3 FAIL**. All six evidence-recovery integrity gates still PASS, including provenance, duplicate attachment, auto-resolution-without-evidence, blocked-with-sufficient-evidence, broken provenance, and idempotency. Three broader failures are surfaced without remediation under the instruction not to reopen unrelated closed review-governance work:

- `HUMAN_DECISION_WITHOUT_AUDIT`: 141 legacy resolved duplicate-candidate records (sample IDs 1–5, 28, 7, 20).
- `REVIEW_DECISION_WITH_INVALID_ACTION`: 11 existing audit events (sample event IDs 69–76).
- `CURRENT_LIST_DUPLICATE_MASTER_ROWS`: 1 duplicate list row (sample Master ID 112).

The four warnings remain `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`, `OPEN_REVIEW_BACKLOG`, `SOURCE_LAST_SUCCESS_TOO_OLD`, and `SYNC_RUNTIME_ANOMALY`. These current broader DQ results supersede the earlier 78-gate snapshot for live status; the original task-specific evidence counts and test results remain tied to their recorded run. Full details are in [post-scheduled-sync-refresh.json](post-scheduled-sync-refresh.json).
