# DQ Warning Reconciliation — 2026-10-21

`DQ_FINAL_CLOSEOUT = COMPLETE`

This focused follow-up reconciles the accepted 308-review snapshot and the 2,537-row source-absence warning. It did not repeat the deep review. The live evaluation used PostgreSQL in a read-only transaction with `persist=False`; it created no DQ audit event, review, sync job, or business-data change. The local API, worker, frontend, scheduler, PostgreSQL, Redis, and readiness check are running.

## Open review count

The accepted review snapshot was 308 open cases. The current mutually exclusive queue breakdown is:

| Domain | Current |
|---|---:|
| Duplicate | 10 |
| Location | 15 |
| Taxonomy conflict | 103 |
| Field conflict | 449 |
| Qualification | 0 |
| Other top-level | 0 |
| **Total** | **577** |

The DQ gate had counted only `FIELD_VALUE_CONFLICT` as a field conflict. The review queue also places `STANDARDIZATION_REVIEW` in the field-conflict queue. The corrected DQ grouping follows that interface: 111 `FIELD_VALUE_CONFLICT` plus 338 `STANDARDIZATION_REVIEW` equals 449. The 338 standardization reviews consist of 95 present at the accepted snapshot and 243 new cases since it. The accepted field count of 180 reconciles as 85 field-value conflicts plus those 95 standardization reviews.

The net increase of 269 is fully attributed to scheduled jobs. The source changes that prompted these cases occurred within those syncs, so cases are counted once under the scheduled-sync category.

| Job | Source | Local time (+03) | Cases |
|---|---|---|---:|
| 392 | `alahsa-opportunities` | 09:00:41–09:01:16 | 22 field conflicts, IDs 429–450 |
| 394 | `invest-saudi` | 09:00:44–09:02:32 | 1 field case, ID 451; review event 491 reopened prior case 119 |
| 399 | `furas` | 10:00:41–10:04:54 | 3 field conflicts, IDs 452–454; 243 standardization reviews, IDs 455–697 |

Attribution: scheduled syncs 269; separate source-data changes 0; code migration/backfill 0; DQ framework 0; other explained 0; unexplained 0. The live DQ run read 577 reviews before and after and created zero review cases.

## Source-absence population

The old rule used `SourceOpportunity.missing_successful_checks` and a source threshold without checking endpoint membership, qualification, or whether the record was expected in a comparable complete enumeration. That rule included national source rows, records retained in current datasets, and non-qualified announcements.

The 2,537-row legacy population now reconciles as:

| Exclusive classification | Count |
|---|---:|
| Confirmed current and present | 2,423 |
| Confirmed historical removed | 102 |
| True absence pending confirmation | 0 |
| Outside Al-Ahsa scope | 0 |
| Non-qualified national record | 9 |
| Location review required | 0 |
| Limited or non-comparable enumeration | 0 |
| Other valid non-absence | 3 |
| Unexplained | 0 |
| **Classification sum** | **2,537** |

Of the legacy population, 2,534 Invest Saudi rows have `qualified_location=false`. Within those rows, 2,423 are present in a current endpoint membership, 102 have only confirmed historical memberships, and 9 are non-qualified rows with a sub-threshold miss counter. The other 3 are non-qualified KFU general announcements. None is an expected, qualified Al-Ahsa opportunity absent from a comparable complete enumeration.

The corrected gate therefore reports `true_pending_confirmation=0`, `non_qualified_rows_counted_as_absence=0`, `outside_scope_rows_counted_as_absence=0`, `noncomparable_rows_counted_as_absence=0`, and `unexplained=0`. The legacy warning population fully reconciles and the gate now passes.

## Invest Saudi generic pages

Exactly 782 records have only a generic official Invest Saudi page and no opportunity-specific detail URL in their raw link fields. The link resolver now suppresses those generic URLs as clickable original-opportunity actions and retains them only as historical URL metadata. No opportunity-specific URL was fabricated.

The live gate still reports 782 as a warning because the official source does not provide individual public detail URLs for these records. The exposed-action count is 0, so this remains an accepted source limitation.

## Live validation and warnings

Read-only PostgreSQL evaluation `b35c046e4dfc4d7aa95a94c90551dbc9` completed at `2026-10-21 10:56:45 +03`: **48 gates, 46 PASS, 2 WARNING, 0 FAIL**.

| Gate | Count | Why warning | Why not failure | Action | Accepted limitation |
|---|---:|---|---|---|---|
| `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION` | 782 | Generic official pages remain the only stored public page for these records. | They are hidden from the original-opportunity action; no fake detail URLs are used. | None for data; retain the limitation until official details exist. | TRUE |
| `OPEN_REVIEW_BACKLOG` | 577 | Valid open review cases remain in the human queue. | All domains reconcile, the increase is explained, and DQ created none. | Continue normal human review governance; do not auto-resolve. | TRUE |

The former `SOURCE_ABSENCE_CLASSIFICATION` warning now passes with zero true pending and zero unexplained absences. All remaining warnings are explained.

Business counts before and after the live evaluation were identical: 546 Master rows, 3,137 SourceOpportunity rows, 12,401 observations, 577 open reviews, 400 sync jobs (maximum ID 400), and 2 persisted DQ events. The new live run was not persisted. No manual source sync was started.

## Tests

- Focused DQ and source-link tests: **34 passed / 0 failed**.
- Full suite under `tests/` on a disposable SQLite database: **213 passed / 0 failed** (18 non-blocking warnings).

Detailed machine-readable evidence: [reconciliation-2026-10-21.json](reconciliation-2026-10-21.json).

```ini
OPEN_REVIEW_COUNT_RECONCILIATION = PASSED
CURRENT_OPEN_REVIEWS = 577
OPEN_REVIEW_DELTA_UNEXPLAINED = 0
DQ_RUN_CREATED_REVIEW_CASES = 0
SOURCE_ABSENCE_CLASSIFICATION_RECONCILIATION = PASSED
TRUE_SOURCE_ABSENCE_PENDING_CONFIRMATION = 0
UNEXPLAINED_SOURCE_ABSENCES = 0
INVEST_SAUDI_GENERIC_PAGE_RECORDS = 782
GENERIC_PAGE_EXPOSED_AS_ORIGINAL_OPPORTUNITY_ACTION = 0
LIVE_DQ_PASSING_GATES = 46
LIVE_DQ_WARNING_GATES = 2
LIVE_DQ_FAILING_GATES = 0
LIVE_DQ_WARNINGS_ALL_EXPLAINED = TRUE
DQ_RUN_IS_READ_ONLY_BY_DEFAULT = TRUE
DQ_AUTO_FIXES_BUSINESS_DATA = FALSE
MANUAL_SOURCE_SYNC_STARTED = FALSE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
FOCUSED_TESTS = 34 passed / 0 failed
FULL_REGRESSION_SUITE = 213 passed / 0 failed
DQ_FINAL_CLOSEOUT = COMPLETE
```
