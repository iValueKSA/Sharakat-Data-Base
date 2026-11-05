# Furas National Promotion — Live Post-Promotion Acceptance and National UI Readiness — 2026-11-02

**Acceptance: FAILED. National UI: BLOCKED. National map: BLOCKED.** The promotion reconciles to the accepted dry run, but current full DQ has four failures and the geography reference/API filters required for national UI are not ready. This was read-only validation. No source sync, Master creation, linking, review resolution, flag change, or business-data write was performed.

The complete 6,546-row reconciliation is in [NATIONAL-UI-DATA-READINESS-20261102.json](NATIONAL-UI-DATA-READINESS-20261102.json). Historical dispositions were joined to live links using the completed promotion manifest and verified live counts/audit events.

## Live baseline

| Measure | Live value |
|---|---:|
| Total Master rows | 6,644 |
| Current Masters | 6,623 |
| Merged/historical Masters | 21 |
| SourceOpportunity rows | 9,290 |
| Furas rows | 6,546 |
| Furas linked / unlinked | 6,493 / 53 |
| Source observations | 49,005 |
| Open reviews/conflicts | 4 |
| Sync jobs | 696 |
| Alembic head | 0025_source_geographic_coverage |

Furas enumeration, national UI, national map, and Furas removal reconciliation flags are all OFF.

## Full Furas reconciliation

| Historical dry-run disposition | Total | Linked | Unlinked | Linked to current Master | Linked to noncurrent Master | Invalid |
|---|---:|---:|---:|---:|---:|---:|
| A_READY_NEW_MASTER | 6,057 | 6,057 | 0 | 6,057 | 0 | 0 |
| B_MATCH_EXISTING_MASTER | 374 | 374 | 0 | 374 | 0 | 0 |
| C_IDENTITY_REVIEW | 46 | 0 | 46 | 0 | 0 | 0 |
| D_NOT_QUALIFYING | 0 | 0 | 0 | 0 | 0 | 0 |
| E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED | 0 | 0 | 0 | 0 | 0 | 0 |
| F_HISTORICAL_OR_NONCURRENT | 62 | 62 | 0 | 62 | 0 | 0 |
| G_SAME_SOURCE_DUPLICATE_REVIEW | 7 | 0 | 7 | 0 | 0 | 0 |
| **Total** | **6,546** | **6,493** | **53** | **6,493** | **0** | **0** |

Every row reconciles exactly once. The 53 unlinked rows are exactly the 46 identity-review plus 7 same-source duplicate-review records; none was resolved.

### Why linked rows exceed 6,431

The 6,493 links comprise 6,057 promoted current-snapshot rows, 374 pre-existing current-snapshot matches, and **62 historical/non-current rows already linked before promotion**. Live inspection confirms all 62 still point to existing current Masters; none points to a promotion-created Master. This is the exact 62-row difference, with no unexpected promotion.

## Promotion integrity and lineage

The promotion created exactly 6,057 current Masters. Live created_at counts in the recorded execution window are 6,057, matching the manifest's created-ID checkpoint and 6,057 promotion audit events. The current count is reconciled by explicit creation evidence: 566 pre-promotion current Masters + 6,057 created = 6,623 current Masters. No unrelated Master change was recorded in the execution window: live updated_at and ChangeHistory counts were both 0 for the window.

All 374 prior matches remain linked to their original Master IDs. The 46 + 7 deferred rows remain unlinked. The 6,057 promotion audit events include the promotion run ID, Master ID, source row IDs, provider keys, timestamp, disposition, confidence, action, and dry-run digest. All promoted Masters have source provenance. Integrity counts: Master without source 0; invalid multi-Master source links 0; duplicate Furas provider IDs 0; current duplicate identities 0; broken/orphan links 0; Al-Ahsa replacement duplicates 0.

## Job 696

Job 696 was a scheduled Furas run under AL_AHSA_SUBSET_V1 while the national enumeration flag was off. Its completed snapshot included 374 local records across 7/7 pages. It inserted 0 rows, updated 374 source rows, removed 0, and created 0 Masters. In the same time window, 374 pre-existing Master rows had updated_at refreshed; there were 0 ChangeHistory, FieldProvenance, or AuditEvent rows indicating canonical field changes. Its checkpoint was complete, but the reconciliation guard correctly withheld removals because the local scope was narrower than Job 694's prior complete SAUDI_NATIONAL_V1 scope (CURRENT_SCOPE_IS_NARROWER_THAN_PRIOR_SCOPE). The job ended coherently as COMPLETED_WITH_WARNINGS / RECONCILIATION_SCOPE_WARNING; it was non-destructive and safe with removals disabled.

The normal scheduled national mode is not ready: the flag is off and the scheduler used the local scope. No scheduler setting was changed.

## Geography and map evidence

Direct source geography values occur on 5,769 current Masters for region and 3,885 for city; 13 recognizable Saudi region labels and 170 distinct city labels occur. No governorate reference assignments exist. The 6,057 promoted records are SPECIFIC_LOCATION; 566 legacy Masters remain UNSPECIFIED. No geographic reference-unit assignments exist. The previous promotion manifest counted NA as a fourteenth region; live values identify it as an unrecognized label on 7 records, so the deterministic count is 13 recognized regions.

| Direct region label | Current Masters |
|---|---:|
| منطقة الرياض | 772 |
| منطقة القصيم | 695 |
| منطقة عسير | 1,130 |
| منطقة جازان | 352 |
| المنطقة الشرقية | 458 |
| منطقة حائل | 437 |
| منطقة الجوف | 233 |
| منطقة نجران | 447 |
| منطقة تبوك | 114 |
| منطقة مكة المكرمة | 306 |
| منطقة المدينة المنورة | 445 |
| منطقة الباحة | 163 |
| منطقة الحدود الشمالية | 210 |
| Unrecognized NA | 7 |

Raw coordinate pairs exist on 6,493 Masters; 130 have no pair. The 6,057 promoted records have direct Furas point values and source URL provenance; no fabricated coordinates were found. However, the runtime verifier requires verified=true provenance and currently accepts 0 points. The national boundary/reference dataset is absent. There are 20 repeated coordinate groups covering 65 Masters; these remain co-located points, not merged identities. Invalid/partial coordinate pairs: 0. Exact national boundary containment is not assessed. Map readiness is BLOCKED.

## National filters, Al-Ahsa quick view, exports, and UI

The API returns 6,623 current Masters unfiltered. The national geography catalog reports NO_VERIFIED_REFERENCE, reference_ready=false, with no selector levels or datasets. Region/Governorate/City options are rejected with HTTP 422. The location=saudi_arabia filter returns 0, not 6,623. The legacy Al-Ahsa quick view returns 571; the Eastern-region legacy filter returns 636. False-positive/false-negative parity cannot be established without an approved reference. Required API/CSV/XLSX geographic filter parity therefore fails validation. National selector, pagination, search, export, RTL, and responsive browser acceptance was not run because the feature gate remains closed.

## Full DQ

A fresh full DQ evaluation ran with persist=false and a PostgreSQL read-only transaction: **124 PASS, 6 WARNING, 4 FAIL** (run 10e921dd60164c76ae0ebc89ded922c9). The previous persisted post-promotion DQ was 129 PASS, 5 WARNING, 0 FAIL.

All four failures count the same four open status conflicts, not four separate populations. They concern Invest Saudi source rows investsaudi:51536, 51540, 51539, and 55163. Each has selected Master status متاحة and conflicting source status أزيلت من المصدر | متاحة. They were detected at 09:03:31 UTC after Job 696. Timing is adjacent, but this evidence does not establish Job 696 as the cause. No conflict was resolved.

Warnings: generic source-page actions, open review backlog, historical review audit gaps, stale MODON/NHC scope verification, sync runtime anomalies, and unknown areas stored as zero. DQ thresholds were unchanged.

## Decision and stop point

- POST_PROMOTION_ACCEPTANCE = FAILED because current full DQ has 4 failures, although promotion reconciliation passes.
- NATIONAL_UI_READINESS = BLOCKED by DQ failures, missing verified geography reference, rejected geographic selector options, the all-Saudi filter returning zero, and unverified regional export parity.
- NATIONAL_MAP_READINESS = BLOCKED because the runtime accepts zero coordinate points and no verified national reference/boundary is installed.
- FURAS_SCHEDULED_NATIONAL_MODE_READY = FALSE because scheduled capture is still local-scope and the national flag is off.

This validation made no writes: manual syncs 0; new Masters 0; link changes 0; business-data changes 0. National UI/map and removals remain off. Stop here; no reviews were resolved and no scheduler mode was changed.


