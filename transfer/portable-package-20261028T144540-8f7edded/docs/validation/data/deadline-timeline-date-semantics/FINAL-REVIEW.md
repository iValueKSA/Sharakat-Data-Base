# Deadline / Timeline / Date Semantics — Final Review

**Result: `DEADLINE_TIMELINE_DATE_SEMANTICS_DEEP_REVIEW = COMPLETE`**

Final data snapshot: **2026-10-20 07:15:49 UTC / 10:15:49 Asia/Amman** (local PostgreSQL). Review scope stayed on date semantics, projections, and their downstream deadline use. No manual source sync ran.

## Semantic findings

| Furas field | Official meaning | Evidence | Canonical mapping | Used as submission deadline? |
|---|---|---|---|---|
| `STARTDATE` | **UNVERIFIED**. Official GIS alias is “Start Date”; the source does not identify it as publication metadata or document its exact business event. | Official Furas layer schema; matched public detail pages label other milestones separately. [Layer metadata](https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?https%3A%2F%2FgisOppertunities.momra.gov.sa%2Farcgis%2Frest%2Fservices%2FGISProjects%2FInvestmentView%2FMapServer%2F0%3Ff%3Dpjson) | Raw attributes only. `publication_date = NULL` absent independent evidence. | No. |
| `ENDDATE` | **UNVERIFIED**. GIS alias is the generic “End Date”; its business event is not documented. | It equals `LASTRFPSELLDATE` in all 177 current rows and 406 historical date-attribute observations. Correlation does not prove a bid cutoff. [Layer metadata](https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?https%3A%2F%2FgisOppertunities.momra.gov.sa%2Farcgis%2Frest%2Fservices%2FGISProjects%2FInvestmentView%2FMapServer%2F0%3Ff%3Dpjson) | Raw attributes only. | No. |
| `LASTRFPSELLDATE` | **UNVERIFIED**. The key is not bound by official schema to a particular user-facing date label. | Furas pages and FAQ distinguish booklet purchase, bid submission, and envelope opening, but do not map this GIS key to one of those milestones. [Furas FAQ](https://furas.momah.gov.sa/ar/faq?page=39), [service flow](https://furas.momah.gov.sa/ar/services-popup/117), [example opportunity](https://furas.momah.gov.sa/ar/opportunity/01-25-009705-4002?type=Investment) | Raw attributes only; no separate milestone field was added. | No. |
| `LASTBIDATE` | **UNVERIFIED**. Schema type is string with no descriptive alias; empty in all 177 current records and 406 historical observations reviewed. | Official layer metadata and current/historic payload coverage; no populated sample exists to compare to a visible label. | Raw attributes only. | No. |

Official pages define bid submission as the cutoff stated in each announcement and show booklet purchase as a separate step; that is not evidence of which GIS field supplies either date. No field was assigned semantics based on its English name.

## Field flow and implementation

| Raw field | Adapter / standardized projection | Master / API | UI, dashboard, alert and exports |
|---|---|---|---|
| `STARTDATE` | Preserved in `raw.attributes`; adapter emits no publication date; standardization marks publication `UNVERIFIED`. | No canonical Master publication date from Furas; the detail API does not expose publication date and the list API does not project it. | CSV/XLSX publication column reads only canonical Master `publication_date`; corrected Furas-only cells are blank. |
| `ENDDATE` | Preserved raw; not emitted as `RawOpportunity.deadline`; Furas `raw_dates.deadline` is null. | No canonical deadline projection from Furas. | Table/detail `آخر موعد`, upcoming dashboard, deadline alerts, API `deadline`, CSV/XLSX use only canonical Master `submission_deadline`. Missing values display `غير محدد`. |
| `LASTRFPSELLDATE` | Same raw-only treatment as `ENDDATE`. The adapter also includes this field in an upstream ArcGIS selection predicate for the source fetch window; that selection use does not map it to a business deadline. | No canonical deadline projection. | Not exposed as a deadline or publication date. |
| `LASTBIDATE` | Preserved raw; never projected to canonical deadline. | No canonical deadline projection. | No business-facing use. |

The source-selection predicate remains part of Furas retrieval; it selects the adapter’s announced/current fetch window. It does not establish a semantic mapping for the Master date. Deadline and publication projections are separate from the raw source attributes.

## Representative evidence sample and coverage

The reviewed set contains **177** Furas-linked records: **48 Investment** and **129 TemporaryRental**. In the current set, all 177 have `STARTDATE`, `ENDDATE`, and `LASTRFPSELLDATE`; all 177 `ENDDATE`/`LASTRFPSELLDATE` pairs are equal. `LASTBIDATE` is empty in all 177. `ENVELOPESOPENDATE` is present for 48 and absent for 129. Historical payload review covered 406 date-attribute observations (570 total Furas observations): every available `ENDDATE`/`LASTRFPSELLDATE` pair matched; no pair differed or had only one value.

The matched-page sample includes:

- Master 195 (`01-26-017001-27001`, Investment, currently available) and Master 325 (`06-26-18115-20003`, Investment, published): both official pages separately label envelope opening; the calendar date corresponds to `ENVELOPESOPENDATE`, not proof for `ENDDATE` or `LASTRFPSELLDATE`.
- Master 324 (`02-26-017001-58001`, TemporaryRental, published): temporary-rental workflow does not establish the investment listing date meanings.
- Master 109 (`02-23-017001-14003`, TemporaryRental, removed): current detail URL is not found; removal was not interpreted as expiry or cancellation.

No Furas-linked Master was `منتهية` at the snapshot. Master status distribution among Furas-linked current Masters was 158 `منشورة`, 6 `متاحة` through a mixed-source projection, and 13 `أزيلت من المصدر`. No lifecycle status was changed.

Per-row values are in [furas-date-semantic-review-masters.csv](furas-date-semantic-review-masters.csv); source attributes and corrections are in [furas-date-corrections.csv](furas-date-corrections.csv). The latter documents 171 canonical deadline corrections and 177 canonical publication-date corrections.

## Reconciliation

| Measure | Before | Final |
|---|---:|---:|
| Total Master rows | 297 | 297 |
| Non-merged Masters | 292 | 292 |
| SourceOpportunity rows | 2,899 | 2,899 |
| Observations | 10,947 | 11,124 |
| Populated canonical deadlines | 276 | 105 |
| Populated canonical publication dates | 178 | 1 |
| Furas-only deadlines from unverified fields | 171 | 0 |
| Furas `STARTDATE` publication projections | 177 | 0 |

The final 105 reliable deadlines and 187 Masters without a reliable deadline reconcile to 292. The 187 include 171 withheld Furas-only values and 16 with no source deadline evidence. There are zero deadline conflicts and zero invalid canonical dates. Publication dates reconcile to 1 confirmed NCP date and 291 unspecified, with zero unresolved canonical publication values. Six Furas-linked deadlines had matching evidence from another source and were retained.

A legacy wrapper key `raw_data_json.publication_date` still contains a derived `STARTDATE` value in 13 raw/provenance JSON records. It is not a source attribute and is not used by standardization, the Master, API, UI, dashboard, or exports. Those stored payloads were not edited to avoid altering preserved raw evidence. The authoritative raw attribute remains `attributes.STARTDATE`.

Detailed machine reconciliation: [master-date-reconciliation-summary.json](master-date-reconciliation-summary.json), [master-date-reconciliation.csv](master-date-reconciliation.csv), [export-date-reconciliation.json](export-date-reconciliation.json).

## Dashboard, alerts, API and exports

The final API returns 292 opportunities with 105 canonical deadlines. The upcoming dashboard endpoint returns 8 rows, Masters `[186, 187, 188, 189, 190, 191, 192, 193]`; none is among the corrected Furas-only set. All use reliable non-Furas canonical values. Date buckets at the fixed Saudi date sum to the same 105 reliable deadlines: 2 past, 0 today, 19 in the next 7 days, 60 in days 8–30, and 24 later.

Six older, open `DEADLINE_APPROACHING` alerts had payloads containing Furas-only dates. They were marked resolved as superseded on 2026-10-20 07:11:40 UTC. All six alert records and their payloads remain intact; no alert history was deleted. No open alert currently uses an unverified Furas date. See [stale-deadline-alerts-resolved.json](stale-deadline-alerts-resolved.json). The active alert list was rechecked after repair: no open deadline alert remains for an affected Master.

API, opportunity table, detail, dashboard, CSV and XLSX checks passed. Both exports have 292 rows and match API references/deadlines; each contains 105 deadlines. All 171 corrected Furas deadline references have blank deadline cells, and all 177 unverified publication references have blank publication cells. A corrected Furas detail shows `آخر موعد للتقديم: غير محدد`.

## Data safety, scheduled sync boundary, tests

Master identity fingerprint and SourceOpportunity link fingerprint match the pre-correction snapshot. The correction transaction did not modify raw payloads or existing observations. The final observation count increased by 177 through natural scheduled jobs, not manual sync: job 372 (Al-Ahsa, success, no row changes) and job 373 (Furas, success, 164 updated source wrappers, no new Masters). All 177 earlier Furas payloads were compared with the refreshed rows; none of the five Furas date attributes or canonical source statuses changed. The Furas raw-payload fingerprint differs after job 373 as expected; prior payload versions remain in SourceObservation. Full details: [scheduled-sync-reconciliation.json](scheduled-sync-reconciliation.json).

The full regression suite ran in a disposable container against isolated SQLite, not the live PostgreSQL database: **174 passed / 0 failed**. Playwright verified search, reset, status filter, pagination, detail, CSV/XLSX, RTL, corrected Furas deadline values, and all five viewport sizes without horizontal overflow: 1920×1080, 1440×900, 1366×768, 768×900, 390×844. Results: [playwright-results.json](../playwright-results.json); screenshots: [screenshots](../screenshots/).

Standardization engine version is **20** in workspace, API and worker. Runtime parity: passed. No manual sync was started.

## Final assertions

```ini
FURAS_DATE_SEMANTIC_CLOSEOUT = COMPLETE
DEADLINE_TIMELINE_DATE_SEMANTICS_DEEP_REVIEW = COMPLETE
FURAS_RECORDS_REVIEWED = 177
STARTDATE_SEMANTIC = UNVERIFIED
STARTDATE_SEMANTIC_VERIFIED = FALSE
ENDDATE_SEMANTIC = UNVERIFIED
ENDDATE_SEMANTIC_VERIFIED = FALSE
LASTRFPSELLDATE_SEMANTIC = UNVERIFIED
LASTRFPSELLDATE_SEMANTIC_VERIFIED = FALSE
LASTBIDATE_SEMANTIC = UNVERIFIED
LASTBIDATE_SEMANTIC_VERIFIED = FALSE
FURAS_FIELDS_INCORRECTLY_USED_AS_SUBMISSION_DEADLINE_REMAINING = 0
FURAS_UNVERIFIED_STARTDATE_VALUES_USED_AS_PUBLICATION_DATE_REMAINING = 0
FURAS_DEADLINE_CORRECTIONS = 171
FURAS_PUBLICATION_DATE_CORRECTIONS = 177
FINAL_NON_MERGED_MASTERS = 292
FINAL_MASTERS_WITH_RELIABLE_DEADLINE = 105
FINAL_MASTERS_WITHOUT_RELIABLE_DEADLINE = 187
FINAL_DEADLINE_REVIEW_REQUIRED = 0
FINAL_DEADLINE_CONFLICTS = 0
FINAL_INVALID_DEADLINES = 0
FINAL_DEADLINE_RECONCILIATION_SUM = 292
FINAL_DEADLINE_RECONCILIATION = PASSED
MASTERS_WITH_CONFIRMED_PUBLICATION_DATE = 1
MASTERS_WITHOUT_CONFIRMED_PUBLICATION_DATE = 291
PUBLICATION_DATE_REVIEW_REQUIRED = 0
UPCOMING_DEADLINES_CONTAINS_UNPROVEN_FURAS_DATES = 0
OPEN_DEADLINE_ALERTS_CONTAIN_UNPROVEN_FURAS_DATES = 0
DEADLINE_ALERTS_CONTAIN_UNPROVEN_FURAS_DATES = 0
HISTORICAL_SUPERSEDED_DEADLINE_ALERTS_PRESERVED = 6
OPPORTUNITIES_TABLE_DEADLINE_RECONCILIATION = PASSED
DETAIL_PAGE_DATE_RECONCILIATION = PASSED
CSV_DATE_RECONCILIATION = PASSED
XLSX_DATE_RECONCILIATION = PASSED
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 174 passed / 0 failed
WORKSPACE_STANDARDIZATION_ENGINE_VERSION = 20
RUNNING_API_STANDARDIZATION_ENGINE_VERSION = 20
RUNNING_WORKER_STANDARDIZATION_ENGINE_VERSION = 20
RUNTIME_STANDARDIZATION_PARITY = PASSED
```


