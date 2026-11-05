# Controlled Medium-Confidence Sector Classification — Final Review

**CONTROLLED_MEDIUM_CONFIDENCE_SECTOR_CLASSIFICATION = COMPLETE**  
Completed: 2026-10-21 (UTC)

## Scope and decision model

The task classified only current Masters whose sector was `غير محدد`. The existing strict classifier remains the `HIGH_CONFIDENCE` path. The added `MEDIUM_CONFIDENCE` path accepts a single clear sector-specific title or structured signal, or agreeing independent signals, when no meaningful conflicting evidence exists. The classifier returns only `HIGH_CONFIDENCE`, `MEDIUM_CONFIDENCE`, `REVIEW_REQUIRED`, or `INSUFFICIENT_EVIDENCE`.

Generic purpose words, venue names, and repeated representations of the same evidence do not add sector confidence. Close competition or strong evidence for different sectors remains `غير محدد` and is routed to review. `أخرى` is assigned only for explicit entertainment attractions because the canonical taxonomy has no separate entertainment sector; missing evidence is never converted to `أخرى`. Official source sector evidence takes precedence over inferred values in future processing, and an existing valid canonical sector is preserved.

The implementation is versioned as `ahda-sector-controlled-relaxation-1.0.0`. Provenance records include classification origin, confidence, rule key, positive and negative evidence, evidence fields, engine version, and inference timestamp. The sector change is written to change history and a system event. Reviewed medium-confidence cases use the existing audited inference-resolution workflow.

## Raw-source classification review

The completed deep-analysis artifacts were reused. The seven unmapped source-sector occurrences comprise three distinct values: `خدمي` (five records), `LEASE_OPPORTUNITY` (one), and `PPP_PROJECT` (one). The first is too broad to identify a sector; the latter two describe an opportunity type or procurement model. The eight unused raw classification fields were reviewed; numeric Furas identifiers lack a verified codebook, while opportunity-type and mixed-purpose fields do not establish a sector. Consequently, no raw-source mapping was safe to apply:

`RAW_SOURCE_CLASSIFICATION_MAPPINGS_APPLIED = 0`

Raw payloads were preserved. Exact semantic activity and sub-activity rules remain available when their values clearly identify one sector. See `medium-confidence-rules.json` for the field-level review.

## Benchmark, dry run, and candidate audit

The benchmark hid official sector labels for 125 non-inferred, already-specified Masters. It produced one medium-confidence holdout prediction: Tourism, correct (1/1, 100%). This sample is too small to estimate general precision reliably, so the percentage is reported with that limitation. The sample audit reviewed all 36 medium-confidence candidates, including a randomized sample of 30; all records have an individual evidence note, and no repeated false-positive pattern was found.

The dry run against the fresh live snapshot found:

- 0 high-confidence candidates, 36 medium-confidence candidates, 6 review-required candidates, and 337 with insufficient evidence.
- Projected unspecified count: 343, a reduction of 36 (9.5%). The prior Phase 2 application classified 11 records; this controlled pass proposes 36 more current unspecified records.
- Proposed sector distribution: 31 Commercial, 4 Other, and 1 Healthcare.
- No new Tourism or Agriculture candidates. Existing totals in both canonical sectors remain independent and unchanged.
- All 6 review-required records already had open sector reviews. They remain unspecified; no duplicate reviews were created.

## Live apply and reconciliation

The guarded apply changed the `sector` value for 36 current unspecified Masters. It did not change any preexisting specified sector. Five existing sector reviews attached to medium-confidence records were resolved as `RESOLVED_INFERENCE` with audit provenance. No schema migration was required.

| Measure | Before | After |
|---|---:|---:|
| Current opportunities | 525 | 525 |
| Specified | 146 | 182 |
| Unspecified | 379 | 343 |
| Specified share | 27.81% | 34.67% |
| Unspecified reduction | — | 36 (9.5%) |
| Commercial | 46 | 77 |
| Other | 9 | 13 |
| Healthcare | 3 | 4 |
| Tourism | 1 | 1 |
| Agriculture | 1 | 1 |

The post-apply snapshot and live API agree on all sector buckets (sum 525). Every canonical sector bucket was checked against the backend sector filter and its CSV and XLSX exports. All three reconciliations passed, including Unspecified (343), Tourism (1), Agriculture (1), and Other (13).

Playwright checked the dashboard totals and RTL/no-horizontal-overflow at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. It exercised the Unspecified, Tourism, Agriculture, and Other filters at each viewport (20 filter checks total); all returned rows had the selected canonical sector, and no browser page errors occurred. This was limited to the count and filter verification requested for this task.

## Data safety, jobs, and quality

The before/after snapshots have identical Master identity, SourceOpportunity identity, raw provenance, observation-history, and merge-lineage fingerprints. Counts also remained stable at 3,137 source rows, 12,855 observations, and 21 merge audits. The apply updates only the sector classification, its timestamps/history/provenance, and the five related review states. Unrelated business fields were not written.

Sync job count and maximum job ID remained 410 from the pre-apply snapshot through final verification, with no active sync jobs. No manual source sync was started. Stale job 212 was left untouched. API and worker were rebuilt and updated to deploy the tested classifier and ingestion precedence; DB, Redis, scheduler, and frontend were not restarted. API readiness returned HTTP 200 and all local services were running at final verification.

The post-apply full DQ run evaluated 56 gates: 54 PASS, 2 expected WARNING, and 0 FAIL. The warnings remain the 782 generic source pages and the 578 open-review backlog; the unexplained source-absence count is zero. The low-confidence, missing-evidence, official-sector-override, strong-contradiction, and logical duplicate-review gates all observed zero.

Focused tests passed (32/32). The full suite passed on the rebuilt runtime using isolated temporary SQLite (290/290); no destructive test was run against live PostgreSQL. One preexisting Starlette/httpx deprecation warning appeared in each run.

## Required assertions

```text
CONTROLLED_MEDIUM_CONFIDENCE_SECTOR_CLASSIFICATION = COMPLETE
CURRENT_OPPORTUNITIES = 525
SECTOR_SPECIFIED_BEFORE = 146
SECTOR_UNSPECIFIED_BEFORE = 379
HIGH_CONFIDENCE_CLASSIFIED = 0
MEDIUM_CONFIDENCE_CLASSIFIED = 36
NEW_REVIEW_REQUIRED = 0
REVIEW_REQUIRED_RETAINED_UNSPECIFIED = 6
STILL_UNSPECIFIED = 343
SECTOR_SPECIFIED_AFTER = 182
SECTOR_UNSPECIFIED_AFTER = 343
UNSPECIFIED_REDUCTION = 36
UNSPECIFIED_REDUCTION_PERCENT = 9.5%
SPECIFIED_PERCENT_BEFORE = 27.81%
SPECIFIED_PERCENT_AFTER = 34.67%
MEDIUM_BENCHMARK_PREDICTIONS = 1
MEDIUM_BENCHMARK_CORRECT = 1
MEDIUM_BENCHMARK_INCORRECT = 0
MEDIUM_BENCHMARK_PRECISION = 100% (1 prediction; not statistically stable)
TOURISM_NEW_HIGH = 0
TOURISM_NEW_MEDIUM = 0
TOURISM_TOTAL_AFTER = 1
AGRICULTURE_NEW_HIGH = 0
AGRICULTURE_NEW_MEDIUM = 0
AGRICULTURE_TOTAL_AFTER = 1
RAW_SOURCE_CLASSIFICATION_MAPPINGS_APPLIED = 0
PREEXISTING_SPECIFIED_SECTOR_VALUES_CHANGED = 0
OFFICIAL_SOURCE_SECTOR_OVERRIDDEN_BY_INFERENCE = 0
AUTO_CLASSIFIED_WITH_STRONG_CONTRADICTION = 0
LOW_CONFIDENCE_AUTO_CLASSIFICATIONS = 0
MISSING_EVIDENCE_CONVERTED_TO_OTHER = 0
INFERRED_SECTOR_WITHOUT_TRACEABLE_EVIDENCE = 0
DUPLICATE_SECTOR_REVIEWS_CREATED = 0
SECTOR_CLASSIFIER_IDEMPOTENT = TRUE
SECOND_RUN_NEW_CLASSIFICATIONS = 0
SECOND_RUN_DUPLICATE_REVIEWS = 0
SECOND_RUN_UNEXPECTED_CHANGES = 0
OFFICIAL_SECTOR_CAN_SUPERSEDE_INFERENCE = TRUE
SECTOR_DASHBOARD_RECONCILIATION = PASSED
SECTOR_FILTER_RECONCILIATION = PASSED
CSV_SECTOR_RECONCILIATION = PASSED
XLSX_SECTOR_RECONCILIATION = PASSED
LIVE_DQ_FAILING_GATES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_IDENTITIES_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MERGE_LINEAGE_PRESERVED = TRUE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FOCUSED_TESTS = 32 passed / 0 failed
FULL_REGRESSION_SUITE = 290 passed / 0 failed
BROWSER_VERIFICATION = PASSED
```

## Artifacts

The required JSON artifacts are in this directory: rules, benchmark, dry run, sample audit, applied decisions, unclassified records, review-required records, migration ledger, post-apply DQ results, and Playwright results. Supporting live baseline/after/final snapshots and API/export reconciliation are also saved here.
