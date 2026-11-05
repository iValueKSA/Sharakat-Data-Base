# RCJY Public Investment Opportunities — Source Integration

**Date:** 2026-11-03  
**Result:** **PARTIAL** — RCJY capture, identity review, promotion, geography, source filter, backup, and source-specific DQ checks completed. The platform-wide full DQ run still has 10 failures in pre-existing review and Furas/scheduler/job state.

## Scope and implementation

- Added the source key `rcjy-investment-opportunities` for the Royal Commission for Jubail and Yanbu public investment catalog.
- Captured the public OutSystems screen-services JSON endpoint using runtime module and API version tokens, cookie/session behavior from the public page, and complete pagination. The live catalog returned **3 of 3** records on one page.
- Provider identity is `InvestmentOpportunity.Id`; live IDs are **265, 266, and 269**. No duplicate provider IDs were found.
- Preserved the complete provider row, Arabic and English titles, city, taxonomy, defaults, application/detail fields, source URL, provider ID, and parser metadata in `SourceOpportunity.raw_data_json`. The source's `first_seen_at`/`last_seen_at` and sync job timestamps record extraction time.
- `OpportunityCode` is blank in the catalog and was not used as a provider key. Default false flags and the `Get Started` label were not interpreted as lifecycle or application availability. Current catalog membership is recorded separately from `source_actionability_status=UNKNOWN`; Master status remains `غير محددة`.
- RCJY remains a publisher, not an inferred opportunity owner. Owner, coordinates, area, plot, deadline, and description remain empty when the source did not provide them.

## Identity review and promotion

The dry run compared every RCJY row with **6,623 current Masters** and **9,290 existing SourceOpportunity rows**. Cross-source comparisons covered Furas (6,546), Invest Saudi (2,555), NCP (45), MWAN (7), MODON (0), NHC (0), and PIF (0). No exact/trusted reference, parcel/site, coordinate, or deterministic cross-source match was found. Generic title-near results were recorded as rejected title-only candidates; they were not merged.

Each record received exactly one disposition: `A_READY_NEW_MASTER` (3). Identity confidence was 0.93 based on the stable provider ID, complete current listing, unique RCJY source row, and the absence of strong candidates across the compared sources and Masters. This confidence is for identity; actionability remains unknown and each Master is marked for manual review.

The current geographic reference matched the source location exactly to Yanbu governorate, reference external ID `301`, under Al-Madinah Region external ID `3`. The operational dataset has no city-level coverage, so city remains unspecified. No centroid coordinates were added.

Three new Masters were created and linked atomically to the three SourceOpportunity rows. Sector values were passed through the governed classifier and stored canonically as `صناعي` (IDs 265, 266) and `تجاري` (ID 269). Three `RCJY_MASTER_CREATED` audit events record provider ID, SourceOpportunity ID, Master ID, action, confidence, identity evidence, and geography evidence. No existing Master was linked or changed.

## Backup and live capture

- Fresh pre-capture logical backup: [20261103T072253Z-aa02f24b.dump](../../../../backups/20261103T072253Z-aa02f24b.dump)
- SHA-256: `fe6f53a25f342c6a892608ca1f3ba24fb10bf9b44930bc237951f040ab93280f`
- Restore test: **PASSED** in a separate ephemeral PostgreSQL 16 container. Restored counts matched the pre-capture baseline: 12 Sources, 6,623 current Masters, 9,290 SourceOpportunity rows, and 0 RCJY rows.
- One manual RCJY sync completed successfully (job 748): 3 received, 3 unique, 3 inserted, 0 updated, 0 removed, 0 bootstrap removals, complete pagination, 100% enumeration. Its legacy Al-Ahsa counter is `ahsa_count=0` and `rejected_count=3` because all three exact locations are outside Al-Ahsa; the full records were still retained in `SourceOpportunity` and later promoted as nationally georeferenced Masters. Source capture itself created no Masters; promotion followed the reconciled dry run.
- No other manual source sync was run. The API, frontend, and worker were updated; the scheduler was left running without a rebuild. The worker image confirms the RCJY adapter and 24-hour freshness policy are available for scheduled work.

## Live validation

- Configured sources: **12**; the 11 pre-existing Sources remain present.
- RCJY SourceOpportunity rows: **3**, all linked; duplicate provider keys: **0**.
- Current Masters: **6,626** (baseline 6,623); all Master rows: **6,647**; merged rows: **21**.
- Masters without a source record: **0**. RCJY Masters without source rows: **0**.
- Fabricated coordinates: **0**. RCJY Master coordinates: all null.
- `/api/filters` includes RCJY and reports 3; `/api/opportunities?source=rcjy-investment-opportunities&region_id=3&governorate_id=301` returns all 3 records.
- Source freshness is `FRESH`; technical status is `HEALTHY`. National UI/map flags remain `false`; the existing 13-region implementation was not changed.

## DQ and regression

The final persisted full DQ run was `9dcbf13c1a144381bc622fbde9a978aa`: **118 pass, 6 warning, 10 fail**. No remaining failing gate is caused by an RCJY record. The 10 platform-wide failures are existing review backlog, Furas missed schedule/freshness, and stale sync-job reconciliation/concurrency state. The six warnings are unrelated limited-source conditions; RCJY's earlier freshness-policy warning was removed by the deployed daily complete-scan policy.

Full regression after the final runtime changes: **669 passed, 1 skipped, 2 failed**. Both failures are existing tests that execute PostgreSQL `to_char` against SQLite (`test_geographic_filter_and_selectors_work_while_national_ui_flag_stays_off` and `test_admin_merge_and_undo_restores_master_and_child_ownership`). Focused RCJY plus freshness tests passed **24/24**; source-logo and video-hero UI contract tests passed **12/12**.

The platform-wide DQ target of zero failures is therefore not met; this is why the integration status is **PARTIAL** despite RCJY-specific validation passing.

## Required counters

| Counter | Result |
|---|---:|
| RCJY public records found | 3 |
| RCJY provider IDs unique | TRUE |
| RCJY source rows inserted / updated / removed | 3 / 0 / 0 |
| RCJY bootstrap removals | 0 |
| Ready new Master / match existing / identity review | 3 / 0 / 0 |
| Noncurrent / not qualifying / duplicate review | 0 / 0 / 0 |
| RCJY Masters created / existing Masters linked | 3 / 0 |
| RCJY duplicates prevented | 0 |
| Duplicate provider keys / Masters without source | 0 / 0 |
| Fabricated coordinates | 0 |
| Pre-capture backup verified / restore test | TRUE / PASSED |
| Platform DQ failures | 10 |
| Configured Sources after | 12 |
| RCJY source filter | PASSED (count 3) |
| Manual RCJY syncs / other manual source syncs | 1 / 0 |

The detailed per-record identity evidence is in [RCJY-MASTER-ELIGIBILITY-DRY-RUN-20261103.json](RCJY-MASTER-ELIGIBILITY-DRY-RUN-20261103.json); machine-readable deployment metrics are in [RCJY-SOURCE-INTEGRATION-MANIFEST-20261103.json](RCJY-SOURCE-INTEGRATION-MANIFEST-20261103.json).

**Stop condition honored:** no RCU, Ta’adeen, NCP Investors Portal, or Tourism integration was started.
