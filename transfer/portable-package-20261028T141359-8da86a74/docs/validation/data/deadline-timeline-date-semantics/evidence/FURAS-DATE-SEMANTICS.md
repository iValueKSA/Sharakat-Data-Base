# FURAS Date Field Semantics

**Pre-correction fixed snapshot:** 2026-10-20 06:54:58 UTC (09:54:58 Asia/Amman). **Final validation snapshot:** 2026-10-20 07:15:49 UTC (10:15:49 Asia/Amman). Database reads and the correction transaction used the local PostgreSQL database; no manual sync was started. A natural scheduled Furas sync (job 373) ran after the corrections; its effects are reconciled in [scheduled-sync-reconciliation.json](scheduled-sync-reconciliation.json).

## Authoritative evidence and semantic decisions

| Furas field | Official meaning | Evidence | Canonical mapping | Used as submission deadline? |
|---|---|---|---|---|
| `STARTDATE` | Official ArcGIS alias is **Start Date**. Its exact competition/publication business event is **UNVERIFIED**. It is not accepted as publication metadata. | Official Furas layer schema exposes `STARTDATE` as `Start Date` (`esriFieldTypeDate`). Current detail page for 01-26-017001-27001 separately labels the opening event `تاريخ فتح المظاريف`; that is a different API field (`ENVELOPESOPENDATE`). No publication label or publication event is linked to `STARTDATE`. [Official Furas opportunity](https://furas.momah.gov.sa/ar/opportunity/01-26-017001-27001?type=Investment); [official layer metadata via Furas public map proxy](https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?https%3A%2F%2FgisOppertunities.momra.gov.sa%2Farcgis%2Frest%2Fservices%2FGISProjects%2FInvestmentView%2FMapServer%2F0%3Ff%3Dpjson). | Raw payload only. `publication_date = NULL` for Furas-only values. | No. |
| `ENDDATE` | Official ArcGIS alias is **End Date**; precise Furas business event is **UNVERIFIED**. | Official layer schema uses generic alias `End Date`, not a submission label. It equaled `LASTRFPSELLDATE` in all 177 current Furas records and all 406 historical observation payloads containing Furas date attributes. This correlation cannot promote it to a bid deadline. It also differs from `ENVELOPESOPENDATE` in 48 current records. [Official layer metadata](https://gisapps.balady.gov.sa/opportunities/proxy/proxy.ashx?https%3A%2F%2FgisOppertunities.momra.gov.sa%2Farcgis%2Frest%2Fservices%2FGISProjects%2FInvestmentView%2FMapServer%2F0%3Ff%3Dpjson). | Raw payload only. | No. |
| `LASTRFPSELLDATE` | **UNVERIFIED.** Public Furas pages distinguish the booklet-purchase cutoff from the bid-submission cutoff, but official GIS metadata and matched same-reference samples do not conclusively bind this key to one visible label. | Official Furas pages explicitly label `آخر موعد لشراء الكراسة` on some opportunities. The official FAQ defines the bid cutoff as the time stated in the competition announcement, and the service flow separately lists booklet purchase and bid submission. Current same-reference pages for Masters 195 and 325 separately display `تاريخ فتح المظاريف`; their UTC calendar dates match the API `ENVELOPESOPENDATE` field. These materials show distinct milestones but do not document which one `LASTRFPSELLDATE` represents. [Official detail example](https://furas.momah.gov.sa/ar/opportunity/01-25-009705-4002?type=Investment); [official FAQ](https://furas.momah.gov.sa/ar/faq?page=39); [official investment service](https://furas.momah.gov.sa/ar/services-popup/117); [Master 195](https://furas.momah.gov.sa/ar/opportunity/01-26-017001-27001?type=Investment); [Master 325](https://furas.momah.gov.sa/ar/opportunity/06-26-18115-20003?type=Investment). | Raw payload only; no dedicated milestone field was introduced. | **No.** `LASTRFPSELLDATE_SEMANTIC_VERIFIED = FALSE`; `LASTRFPSELLDATE_MAY_POPULATE_CANONICAL_DEADLINE = FALSE`. |
| `LASTBIDATE` | **UNVERIFIED.** The official layer schema exposes it as a string with no descriptive alias; it is empty in all 177 current records and all 406 historical date-attribute observations. | Furas official layer metadata + source payload coverage above. There is no field-specific official label or populated value to match to an announcement. The FAQ defines the user-facing bid cutoff, but does not map this API field to it. | Raw payload only; future adapter will not use it as a deadline. | No. |

Official Furas guidance distinguishes buying the booklet, submitting a bid, and opening envelopes. It does not map the GIS field names to those visible labels. No field is mapped by its English name alone.

## Representative source sample

Epoch values below are the exact Furas API `attributes` values preserved in the Master-linked SourceOpportunity. The official Furas detail page is matched by the same reference. UTC conversion is shown only as an API timestamp; the public page may display its own local event time, so these are not promoted to canonical dates.

| Master | Type / state at snapshot | Reference | `STARTDATE` | `ENDDATE` | `LASTRFPSELLDATE` | `LASTBIDATE` | `ENVELOPESOPENDATE` | Official page evidence |
|---:|---|---|---:|---:|---:|---|---:|---|
| 195 | Investment / `متاحة` | `01-26-017001-27001` | `1787270400000` | `1792555200000` | `1792555200000` | empty | `1792540800000` | Live official page separately labels `تاريخ فتح المظاريف: 2026-10-21 10:00:00`. The API's `ENVELOPESOPENDATE` UTC calendar date matches that event; the page does not establish the meanings of `ENDDATE` or `LASTRFPSELLDATE`. [Page](https://furas.momah.gov.sa/ar/opportunity/01-26-017001-27001?type=Investment). |
| 325 | Investment / `منشورة` | `06-26-18115-20003` | `1791936000000` | `1795381140000` | `1795381140000` | empty | `1795392000000` | Live official page separately displays `تاريخ فتح المظاريف: 2026-11-23 08:00:00`. The API's `ENVELOPESOPENDATE` UTC calendar date matches that event; the page does not establish the meanings of `ENDDATE` or `LASTRFPSELLDATE`. [Page](https://furas.momah.gov.sa/ar/opportunity/06-26-18115-20003?type=Investment). |
| 324 | Temporary rental / `منشورة` | `02-26-017001-58001` | `1791849600000` | `1854921600000` | `1854921600000` | empty | empty | Official page is the temporary-rental workflow and does not expose the competition timeline fields shown for Investment listings. No date was mapped. [Page](https://furas.momah.gov.sa/ar/opportunity/02-26-017001-58001?type=TempRental). |
| 109 | Temporary rental / `أزيلت من المصدر` | `02-23-017001-14003` | `1764547200000` | `1827619200000` | `1827619200000` | empty | empty | Historical raw payload retained; the exact official detail URL currently returns the official Furas not-found page. No date was inferred from removal. [URL](https://furas.momah.gov.sa/ar/opportunity/02-23-017001-14003?type=TemporaryRental). |

No Furas-linked Master was `منتهية` at this snapshot; the source rows were 164 `منشورة` and 13 `أزيلت من المصدر`. The merged Master projection had 158 `منشورة`, 6 `متاحة` (mixed-source projection), and 13 removed. There is therefore no expired Furas detail record in the current sample to inspect. Removal remains distinct from expiry and cancellation.

Across the 177 current records: 48 `Investment`, 129 `TemporaryRental`; `STARTDATE`, `ENDDATE`, and `LASTRFPSELLDATE` were present in all; `LASTBIDATE` was empty in all; `ENDDATE == LASTRFPSELLDATE` in all. `ENVELOPESOPENDATE` was present in 48 and missing in 129. Across 406 historical Furas date-attribute observations (570 total source observations), the same presence pattern held: 116 with `ENVELOPESOPENDATE`, 290 without; all 406 pairs of `ENDDATE` and `LASTRFPSELLDATE` were equal. There was no differing or one-missing `ENDDATE`/`LASTRFPSELLDATE` pair in the available historical evidence; none was fabricated for the sample.

## Data flow before correction

| Raw Furas field | Adapter | Standardization / Master | API and UI | Dashboard / alerts | CSV / XLSX |
|---|---|---|---|---|---|
| `LASTRFPSELLDATE` | Kept in `raw.attributes`; after engine 19, not emitted by adapter as `RawOpportunity.deadline`. | Legacy Master values still existed from older ingestion. | Master `submission_deadline` -> API `deadline` -> list cell and detail label `آخر موعد للتقديم`. | API dashboard deadlines and `check_deadlines()` read Master `submission_deadline`. | Exported as Master `submission_deadline` under `آخر موعد للتقديم`. |
| `ENDDATE` | Kept only in raw attributes. | Same legacy values as `LASTRFPSELLDATE`; not a separate Master field. | Same `deadline` path if formerly projected. | Same dashboard/alert path. | Same deadline export path. |
| `STARTDATE` | Kept in raw attributes; `publication_date=None` since engine 19. | 177 legacy Master `publication_date` values remained due update logic not clearing a null. | No publication field in detail JSON; API list did not expose it. | No dashboard or alert use. | CSV/XLSX column `تاريخ النشر`. |
| `LASTBIDATE` | Engine 19 mapped this into `RawOpportunity.deadline`; it was empty in every current Furas row. | Thus no current source payload generated a deadline from this field. | No current effect; future non-empty values would have been exposed as `deadline`. | Same potential future dashboard/alert path. | Same potential future export path. |

The project’s `service.py` only updates a Master date when the incoming standardized value is non-null, so a safe future `None` did **not** clear old values automatically. That is why the existing canonical projections were corrected explicitly. `raw_dates.deadline` is a derived projection, not the raw Furas payload; it is now `None` for Furas so entity matching/status code cannot reuse the invalid projection. Raw API attributes and immutable SourceObservation rows were not edited.

## Corrections and reconciliation

Snapshot pre-correction: **297 Master rows / 292 non-merged / 2,899 SourceOpportunity / 10,947 SourceObservation (max ID 10,947)**. There were 276 non-merged canonical deadlines and 178 publication dates. Six Furas-linked canonical deadlines had matching explicit evidence from another source; those six were preserved. The remaining 171 Furas-only deadlines were removed from `submission_deadline`. All 177 `STARTDATE`-derived publications were removed. The one explicit NCP publication date remains.

| Field | Before | Corrected | Change |
|---|---:|---:|---:|
| Canonical reliable deadlines | 105 | 105 | preserved; includes the six cross-source supported Furas-linked Masters |
| Furas-only canonical deadlines | 171 | 0 | cleared to NULL |
| Other deadline-missing / unverified Masters | 16 | 187 total without a reliable deadline | the 171 cleared values join the 16 truly missing values |
| Canonical publication dates | 178 | 1 | removed 177 unverified Furas `STARTDATE` projections; retained explicit NCP date |

Per-row correction evidence is in [furas-date-corrections.csv](furas-date-corrections.csv). It records Master ID, SourceOpportunity ID, reference, old/new canonical value, raw Furas field and value, finding, and this report as evidence. The existing `FieldProvenance`, ChangeHistory, SourceObservation, and AlertEvent rows were not deleted or edited.

The 177 SourceOpportunity date projections were also corrected: `raw_dates.deadline = NULL`; `standardized_data_json` marks `submission_deadline` and `publication_date` `UNVERIFIED` with rule `furas_dates_raw_only_v1`; `standardization_version = 20`. Original attributes remain in `raw_data_json` and observations. The adapter now preserves all four raw fields and maps none of them to `RawOpportunity.deadline` or `publication_date`.

Thirteen old, derived `raw_data_json.publication_date` wrapper values from `STARTDATE` remain in SourceOpportunity raw/provenance JSON because that payload was preserved. They are not original ArcGIS attributes and are not used by standardization, Master publication dates, API fields, UI, dashboard, or exports. The corresponding `attributes.STARTDATE` remains the authoritative raw source value. All 177 canonical Master publication projections are cleared unless independently supported; the one NCP-confirmed Master date remains.

`FINAL_DEADLINE_REVIEW_REQUIRED = 0` means no unresolved canonical date is still being used or selected: unverified date fields remain available in raw provenance only. The 187 Masters without a reliable deadline includes 171 safely withheld Furas values and 16 with no source date. Conflicts and invalid canonical dates remain zero.

## Timezone and lifecycle boundary

The existing `Asia/Riyadh` date-only policy remains unchanged: offset-aware datetimes normalize to the Riyadh date; unknown timezone-naive datetime inputs are rejected; a date-only deadline remains actionable through that Riyadh local date and expires only after it. Furas raw epoch timestamps remain source evidence and are not converted into canonical business dates by the adapter.

No Furas Master was classified `منتهية` solely by a Furas date at the fixed snapshot, so no lifecycle correction was made. `أزيلت من المصدر` was preserved as source removal; it was not changed to `منتهية` or `ملغاة`.

## Final acceptance snapshot

At the final validation snapshot, 297 Master rows / 292 non-merged Masters / 2,899 SourceOpportunity rows remained. There were 105 reliable canonical deadlines and 187 without one (171 intentionally withheld Furas-only values plus 16 without source deadline evidence), with zero canonical conflicts and zero invalid dates. Publication coverage is 1 source-confirmed date and 291 unspecified, with zero unresolved canonical publication values. The 8 upcoming dashboard rows are Masters `[186, 187, 188, 189, 190, 191, 192, 193]`; none is among the 171 corrected Furas-only deadline Masters.

Six pre-existing open `DEADLINE_APPROACHING` alerts referenced corrected Furas-only dates. They were resolved as superseded on 2026-10-20 07:11:40 UTC, without deleting the alert rows or changing their payloads. The records and prior values remain available in [stale-deadline-alerts-resolved.json](stale-deadline-alerts-resolved.json); there are zero open/current deadline alerts using unverified Furas dates. No lifecycle status was changed.

The full regression suite passed **174 tests / 0 failures** against isolated SQLite. Playwright checked API, table, detail, dashboard, exports, filters/search/reset/pagination, RTL and horizontal overflow at all five viewport sizes. CSV/XLSX each contain 292 rows, match API deadline values, contain 105 canonical deadlines, and have blank deadline/publication cells for all 171/177 corrected Furas reference sets respectively. See [playwright-results.json](../playwright-results.json), [export-date-reconciliation.json](export-date-reconciliation.json), and the screenshots under [screenshots](../screenshots/).

The standardization engine is version **20** in the workspace, API, and worker. Master identity and SourceOpportunity link fingerprints still match the pre-correction snapshot. The correction transaction preserved raw payloads and existing observations. The natural scheduled job 373 later refreshed 164 Furas source wrappers and appended 177 immutable source-status observations; comparing all 177 historical payloads found no change to any of the five Furas date attributes or canonical source statuses. The post-refresh raw payload fingerprint therefore differs from the pre-refresh hash as expected; the earlier payload versions remain in SourceObservation. No manual sync was run.



