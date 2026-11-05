# Source Coverage & Completeness Deep Review

> **Historical provisional snapshot:** this report records an earlier `NOT_COMPLETE` state. It is superseded by [FINAL-RECONCILIATION.md](FINAL-RECONCILIATION.md), which records the final adjudication and acceptance state. Do not use the counts or gate below as the current result.

**Project:** Al-Ahsa Investment Opportunities Platform  
**Review state:** `SOURCE_COVERAGE_COMPLETENESS_DEEP_REVIEW = NOT_COMPLETE`  
**Fixed snapshot:** 2026-10-20 13:59:35 Asia/Amman  
**Post-scheduled-sync snapshot:** 2026-10-20 14:09:00 Asia/Amman

## Executive result

The source registry, public-scope contracts, major paginated enumerations, current Master APIs, exports, and RTL browser screens were reconciled. The live app remains ready. No manual source sync ran, and no Master or SourceOpportunity business rows were changed by this review. Two naturally scheduled jobs completed during the snapshot window and added 13 observations without adding or updating source listings or Masters.

The review remains **NOT_COMPLETE** because exact authoritative current-set mismatches remain pending, the Furas date/qualification filters could not be independently count-audited, and MODON/MWAN current enumerations were unavailable. The review did find and fix one genuine coverage-mechanics defect: complete successful scans did not count absence for unlinked `SourceOpportunity` rows. The fix is deployed and regression-tested; no sync was run to advance live missing counters.

## Snapshot and safety

| Measure | Fixed snapshot | After natural scheduled jobs |
|---|---:|---:|
| Master rows | 308 | 308 |
| Current non-merged Masters | 287 | 287 |
| Merged Masters | 21 | 21 |
| SourceOpportunity rows | 2,899 | 2,899 |
| Source observations | 11,174 | 11,187 |
| Sync jobs | 379 | 381 |

Jobs **380 (Furas)** and **381 (Al-Ahsa platform)** were scheduled, successful and complete: 164/164 across 3/3 requests and 103/103 across 12/12 pages, respectively; each reported zero new and zero updated records. Observation delta was +13. Master and SourceOpportunity deltas were zero. `MANUAL_SOURCE_SYNC_STARTED = FALSE`.

The source-health reconciliation changed only four operational health fields from HEALTHY to WARNING where the latest job had failed (AHDA job 366, Invest Saudi 367, MODON 368, MWAN 345). It changed no business rows. The API and Worker were rebuilt for the source-removal mechanics fix; database, scheduler, frontend, and local data volumes were kept running.

## Source registry and coverage model

There are **10/10 enabled sources**, all with a configured schedule. Technical health and coverage are separate fields in the accepted model and in the API/admin source-health surface. Current declared coverage states are 7 `COMPLETE_PUBLIC_SOURCE`/`COMPLETE_FOR_DEFINED_SCOPE` and 3 `PUBLIC_COVERAGE_LIMITED`. Current technical health is 5 HEALTHY and 5 WARNING. A declared defined-scope status does not imply the last scan succeeded; the table below calls out stale or unavailable enumerations.

The per-source contract is the discoverable unauthenticated public surface described by the accepted public-completeness ADR. It is not a claim that private/authenticated pipelines are complete. SourceOpportunity rows include national/reference candidates and must not be equated to Al-Ahsa Masters.

See [source-coverage-matrix.csv](source-coverage-matrix.csv) and [official-vs-platform-reconciliation.json](official-vs-platform-reconciliation.json) for the complete source list, methods, schedules, timestamps and counts.

| Source | Public-scope result | Official/enumerated current | Platform current / historical / total | Finding |
|---|---|---:|---:|---|
| Furas | Complete public catalog claim; technical HEALTHY | 164 / 164 | 164 / 13 / 177 | Current enumeration reconciles; 13 removed IDs preserved. Filter semantics remain unaudited (below). |
| Al-Ahsa platform | Complete public listing | 103 / 103 | 103 / 0 / 103 | Reported total and all 12 pages reconcile exactly. |
| AHDA | Complete for sitemap/page-defined scope; technical WARNING | 8 qualifying from 215 pages | 8 / 0 / 8 | Read-only crawl parsed all 215 pages and found 8 opportunity items; latest scheduled sync failed, so keep WARNING. |
| Invest Saudi | Complete public four-dataset claim; technical WARNING | 2,440 / 2,440 | 2,453 / 102 / 2,555 | 13 current memberships absent from fresh official enumeration; no successful scheduled complete sync since the latest failed job. See exact IDs in `extra-source-records.json`. |
| KFU | Complete for public announcement scope | 2 / 2 | 5 / 1 / 6 | Three unlinked, unknown-status rows were absent from the latest successful 2-item complete scan. Previous removal reconciliation excluded unlinked rows; fix is now deployed, but no post-fix scan was run. |
| NCP | Complete for English News archive defined scope; broader investor pipeline private | 46 articles / 46 | 45 / 0 / 45 | One item qualified in the current read-only crawl. The Arabic mirror's final continuation page returned maintenance; this is outside the canonical English scope and is recorded as one noncanonical gap. A two-row same-URL FoodSafetyLabs alias is intentionally retained, not a duplicate identity. |
| MODON | Limited public catalog | Not itemized / current fetch unavailable | 0 / 0 / 0 | Public catalog does not expose a live Al-Ahsa availability inventory; TLS verification failure blocked this current sweep. |
| NHC | Limited public inventory | Not itemized; 0/6 unauthenticated routes fetched (HTTP 403) | 0 / 0 / 0 | No public itemized inventory; authenticated land/investor services remain out of scope. |
| PIF | Limited public inventory | 0 items in rendered public listings; total population unknown | 0 / 0 / 0 | 12/13 public routes were successfully monitored; current listing pages showed no item cards. This is not evidence the PIF opportunity universe is empty. |
| MWAN | Declared complete for defined published-project scope; current freshness unknown | Current fetch unavailable; last success 2026-10-12 | 5 / 0 / 5 | TLS verification failure blocks current enumeration. Retained records were not removed. |

The public pages and scope limits for NCP, PIF, NHC and MODON are documented in the accepted architecture notes. In particular, no private API, authenticated investor inventory, guessed filter or search-index-only opportunity was used.

## Pagination, totals and filters

Six sources exposed enumerations with conventional pagination: Furas 3/3 requests, Al-Ahsa 12/12 pages, AHDA 215/215 content pages plus sitemap discovery, Invest Saudi 26/26 dataset pages, KFU 1/1, and NCP 82/83 requests (English canonical scope complete; Arabic continuation gap recorded). Invest Saudi dataset totals were 1,771 Opportunities, 347 Investment projects, 184 PIF opportunities and 138 Regional opportunities. Their sum 2,440 reconciled to 2,440 unique official IDs with zero cross-dataset duplicate memberships.

Furas reported and returned 164 unique current IDs in its latest successful scheduled scan. Its configured filters include 11 Al-Ahsa CITY_ID values, `OPPORTUNITYACTIVESTATUS='Announced'`, `LASTRFPSELLDATE >= local today`, and `QualifyingOpportunity=0`. The date/qualification-filter variant counts could not be queried: the configured ArcGIS layer hostname did not resolve during the independent count probe. Therefore the audit cannot rule out an over-restrictive date or enum filter. It did not infer that the filters are safe merely because 164 records were returned. Details and the failed probe are in [filter-audit.json](filter-audit.json) and [furas-filter-audit.json](furas-filter-audit.json).

MODON and MWAN could not be enumerated through their adapters during the read-only pass because of TLS certificate verification failures. NHC public routes were 403. These are coverage limits/failures, not empty inventories. PIF returned no item-bearing current public routes but remains limited rather than complete.

## Exact current-set differences

- **Invest Saudi:** 2,440 official IDs were fully enumerated. All were already represented locally. The DB has 2,453 current dataset memberships plus 102 historical memberships. The 13 local current memberships absent from the fresh official ID set are exact and listed in `extra-source-records.json`; each still has zero missed checks because the latest scheduled complete local sync failed (job 367). Do not classify them as removed until successful scheduled scans establish the configured threshold.
- **KFU:** the latest successful scheduled job 369 fully enumerated 2 IDs. Three local unlinked rows remain current with unknown canonical status and zero missing checks: `kfu-announcement:d20b35b7faa10dadaf813279`, `kfu-announcement:386b36399fd270bfa5c772e0`, and `kfu-announcement:99442b845172484870ec5665`. They have no Master. Their absence needs complete post-fix scans; exact records are in `extra-source-records.json`.
- **Furas:** the 13 additional platform rows are confirmed historical/removed, not unexplained current extras. Their IDs are preserved in the same artifact.
- No official IDs were missing from platform for the authoritative current enumerations of Furas, Al-Ahsa, Invest Saudi or KFU. Unavailable/non-itemized public sources do not have a meaningful official-ID denominator.

The 16 current absent rows (13 Invest Saudi + 3 KFU) remain pending source reconciliation; they were not deleted, relinked, or guessed. Consequently `UNEXPLAINED_EXTRA_SOURCE_RECORDS = 16` for this snapshot and the source-set acceptance gate is not met.

## Coverage/removal mechanics fix

Before this review, `reconcile_missing_records` selected only SourceOpportunity rows with a Master link. Thus an unlinked national or unqualified source identity could never accrue successful-scan misses or become source-level historical after confirmed disappearance. This was directly visible in the KFU rows and was a genuine source-coverage defect.

The fix now counts absence for every source identity after a complete successful scan. Once the configured threshold is reached, the source row receives the existing canonical `أزيلت من المصدر` state and an immutable status observation. Master projection still runs only when a Master link exists. Partial, failed, warning, or unsafe scans still do not call removal reconciliation. No lifecycle meaning or Master status rule changed.

A regression test verifies misses 1 and 2 leave the unlinked source row unchanged, miss 3 marks it removed, the raw status/payload remain intact, a status observation is added, and no Master is created. `tests/test_ingestion.py` and `tests/test_adapters.py` also cover complete pagination, overlapping-page deduplication, complete-scan thresholds, reappearance, and partial-scan removal safety.

## API, dashboard, exports and browser

Post-deploy runtime check: API readiness, DB, Redis, Worker and Scheduler all report ready/ok. API registry contains 10 sources. The general dashboard total and Data Dashboard `global_total` are both 287; the opportunity list returned 287 unique Master IDs; the `source_listings_collected` value remains 2,899 and is not used as the dashboard opportunity count.

CSV export returned HTTP 200 with 287 opportunity data rows. XLSX returned HTTP 200; the opportunity worksheet's range is `A1:AF293`, with its header at row 6 and 287 opportunity data rows at 7–293; the second report-metadata sheet is present. Master 325 detail returned its linked Furas source and the browser detail modal opened successfully.

Playwright used the local app at `/?view=opportunities` and also inspected the data dashboard and official sources view. At **1920×1080, 1440×900, 1366×768, 768×900 and 390×844**, the document stayed within viewport width, RTL was present, and every filter/reset control remained inside the toolbar. Search, status filter, reset, pagination, detail request/modal passed; browser page errors and failed requests were zero. Screenshots and exact viewport measurements are in [playwright-results.json](playwright-results.json) and `screenshots/`.

## Regression and runtime

Full project suite: **186 passed / 0 failed**, with one existing Starlette/httpx deprecation warning. It ran against an isolated project copy with a temporary SQLite DB and `REDIS_URL` unset; the live PostgreSQL DB was not used by tests. The API/Worker were rebuilt from the tested workspace and the live local app passed readiness afterward. Standardization Engine remains version 21; the only source logic change is missing-scan reconciliation for unlinked source rows.

## Safety assertions

```ini
TECHNICAL_HEALTH_SEPARATE_FROM_COVERAGE = TRUE
REMOVAL_DETECTION_REQUIRES_COMPLETE_SUCCESSFUL_SCAN = TRUE
PARTIAL_SCAN_CAN_TRIGGER_FALSE_REMOVALS = FALSE
QUALIFIED_SOURCE_RECORDS = 312
QUALIFIED_SOURCE_RECORDS_WITH_MASTER = 312
QUALIFIED_SOURCE_RECORDS_WITHOUT_MASTER = 0
LOCATION_REVIEW_REQUIRED_CURRENT_DB = 15
INVEST_SAUDI_DESCRIPTION_CANDIDATES_REQUIRING_REVIEW = 18
SOURCE_TECHNICAL_DUPLICATE_EXTERNAL_IDS = 0
ORPHANED_SOURCE_RECORDS = 0
ACTIVE_SOURCE_RECORDS_WITH_ZERO_OBSERVATIONS = 0
ORPHANED_OBSERVATIONS = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_IDENTITIES_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 186 passed / 0 failed
```

## Completion gate

`SOURCE_COVERAGE_COMPLETENESS_DEEP_REVIEW = NOT_COMPLETE`

Remaining blockers:

1. 13 exact Invest Saudi memberships and 3 exact KFU source rows remain absent from their latest official complete enumerations. No post-fix scheduled complete scan was run, as manual sync is prohibited; the 16 records remain safely preserved while confirmation counters accrue naturally.
2. Furas's date-window and `QualifyingOpportunity` filter variants could not be independently counted because the configured ArcGIS layer hostname failed DNS resolution. Potential over-restriction is not ruled out.
3. MODON and MWAN current inventories could not be freshly enumerated because of TLS verification failures; MWAN's last successful scan is 2026-10-12.
4. One Arabic NCP mirror continuation page was unavailable; it is outside the complete English canonical archive contract but remains an explicit mirror limitation.

A later final acceptance should compare the next naturally scheduled full scans to the preserved IDs and rerun the Furas filter-count probe when its official host is reachable. It must not start a manual source sync.
