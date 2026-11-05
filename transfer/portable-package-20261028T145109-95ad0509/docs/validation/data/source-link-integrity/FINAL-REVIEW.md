# Original Source Link Integrity & Repair Review

**Project:** Al-Ahsa Investment Opportunities Platform  
**Validation date:** 2026-10-19  
**Effective-link audit:** 300 source records, final local HTTP/content-identity pass at 2026-10-19 12:54 UTC.  
**Scope:** SourceOpportunity records linked to the current non-merged Master population. The records were read from the live local database; all requests below were read-only.

## A. Root cause of the reported Furas 404

The reported row is Master **324**, SourceOpportunity **2926**, source `furas` (`فرص – البوابة الموحدة للاستثمار`). Its official reference and external ID are both `02-26-017001-58001`.

The database stores `https://furas.momah.gov.sa/ar/opportunity/02-26-017001-58001?type=TemporaryRental`. A direct request returned HTTP 404. The source payload has no URL/link field; it supplies ArcGIS `OBJECTID=1790074`, `OPPORTUNITYID=02-26-017001-58001`, and `OPPORTUNITYTYPE=TemporaryRental`. The adapter had constructed the URL from those identifiers but passed the source enum unchanged.

The currently working official detail route is `https://furas.momah.gov.sa/index.php/ar/opportunity/02-26-017001-58001?type=TempRental` (HTTP 200). It contains the exact official reference and title, and matches the raw owner/location evidence (Amanah Al-Ahsa; Al-Nasriyah / Al-Ahsa). This is an **INCORRECT_URL**, caused by the stale route form and, decisively, the unsupported `TemporaryRental` query value where the public route requires `TempRental`.

The record remains present in the latest successful scheduled Furas scan (job 352, 164 records); Master and source lifecycle are still `منشورة`, raw status remains `Announced`, and missing checks remain 0. The 404 was not interpreted as removal or cancellation.

**URL patterns**

- `OLD_FURAS_URL_PATTERN`: `https://furas.momah.gov.sa/ar/opportunity/{reference}?type={source OPPORTUNITYTYPE}` (for this record, `TemporaryRental` returns 404).
- `CURRENT_FURAS_URL_PATTERN`: `https://furas.momah.gov.sa/index.php/ar/opportunity/{reference}?type={route type}`, with `TemporaryRental` deterministically normalized to `TempRental`.

## B. URL architecture and provenance

- Furas has no source-provided page URL in the stored raw attributes. The adapter now constructs a detail URL only from the official reference and `OPPORTUNITYTYPE`, including the documented route-type normalization. It does not fall back to the Furas home page.
- Other adapters use source-provided item URLs when a specific opportunity page exists. Invest Saudi now rejects generic listing URLs as opportunity-detail URLs; KFU no longer fabricates a listing-page fragment from a synthetic hash when it has no item-specific detail page.
- API source objects expose `url`, `historical_url`, `checked_url`, `link_health`, `link_checked_at`, and `url_repaired`. Unavailable or uncertain URLs return `url: null` and a non-clickable Arabic status in the detail view.
- The database's original Furas URL was not overwritten. It remains in `SourceOpportunity.source_url`; the existing immutable `source-record-status-snapshot` observation **7661** also retains the prior URL in its `endpoint`. Before any future ingestion replaces a URL, the service records an immutable `source-url-history` observation.
- CSV/XLSX retain their current one-URL schema. If a Master has multiple sources, the export now selects the first usable source link by configured source priority; when no link is usable, it exports an empty URL. Details continue to show every source independently.

## C. Source-by-source audit

Health is based on the effective opportunity-specific URL, HTTP response, final URL, and available content identity—not HTTP 200 alone.

| Source | Links | Valid 200 | Redirected valid | Unavailable confirmed | Temporarily unverifiable | Missing/invalid |
|---|---:|---:|---:|---:|---:|---:|
| فرص – البوابة الموحدة للاستثمار (Furas) | 177 | 170 | 0 | 7 | 0 | 0 |
| منصة الفرص الاستثمارية بالأحساء | 103 | 103 | 0 | 0 | 0 | 0 |
| هيئة تطوير الأحساء (AHDA) | 8 | 0 | 8 | 0 | 0 | 0 |
| استثمر في السعودية | 8 | 6 | 0 | 0 | 2 | 0 |
| جامعة الملك فيصل (KFU) | 3 | 0 | 0 | 0 | 3 | 0 |
| المركز الوطني للتخصيص (NCP) | 1 | 1 | 0 | 0 | 0 | 0 |
| مدن (MODON) | 0 | 0 | 0 | 0 | 0 | 0 |
| NHC الاستثمار | 0 | 0 | 0 | 0 | 0 | 0 |
| بوابة القطاع الخاص لصندوق الاستثمارات العامة (PIF) | 0 | 0 | 0 | 0 | 0 | 0 |
| موان (MWAN) | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **300** | **280** | **8** | **7** | **5** | **0** |

All ten configured sources were checked; the four rows with zero linked records were confirmed in the source configuration. All 300 current effective URLs have an audited health entry. The two Invest Saudi listing pages and three KFU list-page fragments returned HTTP 200 but failed opportunity-detail identity/target checks; they are included in the five temporarily unverifiable records and are not exposed as active links.

Detailed record-level results are in [source-link-audit.csv](source-link-audit.csv). The file includes source/master IDs, stored and effective URLs, both audit classes where applicable, HTTP/final URL, identity checks, and source lifecycle context.

## D. Furas findings and repairs

All **177** current Furas links were checked against canonical routes. The exact stored URLs were separately tested locally: 129 returned 404; of those, **122** have a verified replacement route (exact reference/title plus applicable owner/location evidence). Seven remain 404 even on the current route and are already in the source's removed state after complete successful scans.

The 122 repair rows contain old URL, replacement URL, both response classes, official reference, title identity, source lifecycle, and evidence fields in [furas-repairs.csv](furas-repairs.csv). This is a deterministic URL projection/adapter correction; no row-by-row database patch or source synchronization was run.

The seven currently unavailable Furas source records are SourceOpportunity IDs **15, 23, 25, 26, 69, 109, 122** (Masters with the same IDs). Each source row is `أزيلت من المصدر`; they have 10 or 64 successful missing checks in the current snapshot. These are technical link-health findings alongside existing source-removal evidence, not new lifecycle inferences. Their URLs remain in provenance and are not shown as clickable current announcements. See [unavailable-links.csv](unavailable-links.csv).

## E. Other unavailable/uncertain records

There are no additional HTTP 404/410 detail pages in the current effective-link pass.

- Invest Saudi SourceOpportunity **2357** / Master **102** and **2368** / Master **230** point to the generic `/investment-opportunities` page. The project payloads have numeric IDs but no public item URL or proven detail route; no URL was guessed from the ID. Their current lifecycle values remain `غير محددة`.
- KFU SourceOpportunity **2773** / Master **224**, **2774** / Master **225**, and **2928** / Master **326** resolve to the same announcements listing page with synthetic fragments. The page contains listing text, but no matching HTML fragment target exists for those identifiers. They remain `TEMPORARILY_UNVERIFIABLE` and non-clickable; source lifecycle values are unchanged.

These five cases are catalogued in [unverified-links.csv](unverified-links.csv). A matching title in a listing page or an HTTP 200 response was not treated as a distinct detail page.

## F. UI, API, and exports

- **Reported detail API:** Master 324 returns HTTP 200, `link_health=VALID`, the repaired Furas URL, `url_repaired=true`, and the old URL as `historical_url`. A browser request to the replacement page returned HTTP 200 and contained the exact reference and title.
- **Known unavailable detail:** Master 15 returns `UNAVAILABLE_CONFIRMED`, a null active URL, and its historical URL. The details UI shows `الإعلان غير متاح حاليًا على المصدر` with zero clickable source links.
- **Multi-source behavior:** Master 102 retains the working Furas action while the Invest Saudi listing is shown as temporarily unverifiable. The detail UI has one active URL and one honest non-clickable status.
- **CSV/XLSX:** exports for Master 324 contain the repaired canonical URL. Master 15 exports a blank link rather than a known 404. Multi-source Master 102 exports the working Furas URL. XLSX rows were read back from the generated workbook to verify the same results.
- **Responsive UI:** RTL and no horizontal overflow passed at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. Screenshots are in [screenshots](screenshots/); machine-readable checks are in [playwright-results.json](playwright-results.json).

## G. Regression and data safety

The complete suite was run against the final code in an isolated temporary SQLite database, not the live PostgreSQL database: **169 passed / 0 failed**, with one existing Starlette/httpx deprecation warning. See the captured [full regression log](full-regression-results.txt).

A read-only database comparison was captured before and after application deployment. Master identities, source-link identities, raw-payload fingerprints, stored source URL fingerprints, and source/master canonical lifecycle statuses were unchanged by this review. No business status was modified. Thirteen `missing_successful_checks` counters advanced by one during the naturally scheduled Furas job 352; this is source reconciliation metadata, not a canonical status change.

Scheduled sync activity was observed but not initiated manually:

| Job | Source | Outcome | Relevant effect during review |
|---:|---|---|---|
| 349 | AHDA | Success | Added one record (SourceOpportunity 2929, Master 327); this raised the current audit scope from 299 to 300 links. |
| 350 | Invest Saudi | Success | Updated 8 source payloads; their stored URL fingerprints were unchanged. |
| 351 | MODON | Failed | No records received or changed. |
| 352 | Furas | Success | 164 records seen; no new/updated rows; 13 status-snapshot observations created and the 13 corresponding missing-check counters advanced. |
| 353 | Al-Ahsa platform | Success | 103 records unchanged. |

The safety snapshot was captured at **2026-10-19 12:50:32 UTC** with 297 Master rows, 2,899 total SourceOpportunity rows, and 10,528 observations. After job 352, the count was 10,541 observations (+13). The 122 link repairs are projections at the canonical URL layer, not persisted changes to business rows. No manual source sync was started.

## H. Acceptance summary

```ini
ORIGINAL_SOURCE_LINK_INTEGRITY_REVIEW = COMPLETE
REPORTED_FURAS_MASTER_ID = 324
REPORTED_FURAS_SOURCE_ID = 2926
REPORTED_FURAS_REFERENCE = 02-26-017001-58001
REPORTED_LINK_ROOT_CAUSE = INCORRECT_URL
TOTAL_SOURCE_LINKS_AUDITED = 300
VALID_SOURCE_LINKS = 280
REDIRECTED_VALID_SOURCE_LINKS = 8
REPAIRED_SOURCE_LINKS = 122
UNAVAILABLE_CONFIRMED_SOURCE_LINKS = 7
TEMPORARILY_UNVERIFIABLE_SOURCE_LINKS = 5
MISSING_SOURCE_LINKS = 0
INVALID_SOURCE_LINKS_REMAINING = 0
HTTP_404_LINKS = 7
HTTP_200_BUT_CONTENT_MISMATCH = 5
FURAS_LINKS_AUDITED = 177
FURAS_LINKS_REPAIRED = 122
FURAS_CONFIRMED_UNAVAILABLE = 7
KNOWN_UNAVAILABLE_LINKS_EXPOSED_AS_ACTIVE_ACTION = 0
OLD_URL_PROVENANCE_PRESERVED = TRUE
MASTER_STATUS_CHANGES_CAUSED_BY_LINK_REVIEW = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
LIFECYCLE_SEMANTICS_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
DETAIL_PAGE_SOURCE_LINK_VERIFICATION = PASSED
CSV_SOURCE_URL_RECONCILIATION = PASSED
XLSX_SOURCE_URL_RECONCILIATION = PASSED
BROWSER_SOURCE_LINK_VERIFICATION = PASSED
FULL_REGRESSION_SUITE = 169 passed / 0 failed
```

