# Final location/geographic eligibility acceptance review

**Gate: `LOCATION_GEOGRAPHIC_ELIGIBILITY_DEEP_REVIEW = COMPLETE`**  
**Fixed API validation snapshot:** `2026-10-19T09:54:54.895Z`. Start/end business-data fingerprints match (`implementation-start-fingerprint.json`, `implementation-final-fingerprint.json`). Scheduled Furas and Al-Ahsa source syncs completed before the start fingerprint; no manual sync ran. This report supersedes the earlier `NOT_COMPLETE` conclusion in the archived [initial review](INITIAL-REVIEW-2026-10-19.md), after closing the documented filter, hierarchy, API projection, export, and review-state blockers. Scope remains geography only; completed taxonomy reviews were not reopened.

## A. Architecture and semantic model

`MasterOpportunity` remains one row per real opportunity. Its existing `city`, `district`, `location_description`, `latitude`, and `longitude` fields are a single-valued projection. Source records remain separate in `SourceOpportunity`, and source raw locations/payloads remain intact. `OpportunityLocation` plus source raw payloads preserve multiple locations. NCP Master 228 still appears once and preserves its five source locations. No schema migration or business-data correction was required.

`app/geography.py` provides a derived `Country → Region → Governorate → Locality` hierarchy: Saudi Arabia, Eastern Province, Al-Ahsa Governorate, and 12 reviewed localities. Exact aliases cover Arabic and English forms of Al-Ahsa/Al-Hasa, Hofuf, Mubarraz, Omran, Jafr, Oyoun, Uqair, Salwa, Jarn, Qarah, Ghawar, Ura'ira, and Jawatha. District remains separate. Unrecognized values stay unnormalized. API details retain the original Master projection under `geography.source_projection` and expose each source's raw location.

Eligibility requires opportunity-level evidence: an official structured Al-Ahsa locality/governorate value, a reviewed locality alias, explicit official project/site location, or verified source-scoped evidence. Publisher/owner location, Eastern Province or Saudi Arabia alone, fuzzy title similarity, and coordinates alone do not establish eligibility. Contradictions stay in review. The local geoBoundaries/OSM polygon is only a map display reference; it is not an official administrative, cadastral, planning, or legal boundary.

The parent option `al_ahsa_governorate` rolls confirmed localities and valid multi-location source evidence into one Master result. Source locations are expanded for filtering without duplicating Masters. Only pending Master-geography reviews carrying recognized geography reason codes exclude a Master from the confirmed parent filter; generic source-candidate reviews do not invalidate independent Master evidence.

## B. Eligibility reconciliation

The fixed universe contains 296 Masters: 291 non-merged and 5 merged. The four non-merged classifications are mutually exclusive and sum to 291:

| Classification | Count |
|---|---:|
| `AL_AHSA_CONFIRMED` | 282 |
| `MULTI_LOCATION_WITH_AL_AHSA` | 1 |
| `LOCATION_UNSPECIFIED` | 6 |
| `LOCATION_REVIEW_REQUIRED` | 2 |
| **Total non-merged Masters** | **291** |

The six unspecified Master IDs are 211, 213, 214, 215, 216, 217; review-required IDs are 70 and 212. The confirmed-plus-multi filter set contains 283. [Exact-set reconciliation](exact-set-reconciliation.json) records all expected and actual IDs: false positives 0, false negatives 0. No record was removed from the general Master list.

## C. Source evidence and national/regional review

| Official source | Records | Linked Master records | Raw location present | Explicit Al-Ahsa location field | Coordinate records | Coverage |
|---|---:|---:|---:|---:|---:|---|
| AHDA | 7 | 7 | 0 | 0 | 0 | Defined scope complete |
| Al-Ahsa Investment Opportunities | 103 | 103 | 103 | 95 | 0 | Public source complete |
| Furas | 177 | 177 | 156 | 156 | 177 | Public source complete |
| Invest Saudi | 2,555 | 8 | 2,022 | 6 | 0 | Public source complete |
| KFU | 6 | 3 | 4 | 4 | 0 | Defined scope complete |
| MODON | 0 | 0 | 0 | 0 | 0 | Public coverage limited |
| MWAN | 5 | 0 | 1 | 0 | 0 | Defined scope complete |
| NCP | 45 | 1 | 18 | 2 | 0 | Defined scope complete |
| NHC | 0 | 0 | 0 | 0 | 0 | Public coverage limited; warning health |
| PIF | 0 | 0 | 0 | 0 | 0 | Public coverage limited |

There are 12 explicit Al-Ahsa Invest Saudi candidate checks and 4 contradictory/multi-region cases still open; none were bulk-promoted. One candidate queue item is linked to Master 230, but the generic candidate identity reason is not a geography blocker: Master 230 has independent explicit Furas location evidence. Incorrectly promoted national records: 0. Supported Al-Ahsa Masters missed by the final eligibility rule: 0. The 12 candidates remain possible source coverage additions pending identity/status/multiplicity review. Zero-record MODON/NHC/PIF feeds have limited public coverage and do not establish that no opportunities exist.

## D. Open review queue

The queue has 25 open cases and 0 resolved in this pass:

- 13 explicit Al-Ahsa candidate identity/status/multiplicity checks.
- 4 contradictory or multi-region evidence cases.
- 8 Master geography reviews: 6 `LOCATION_UNSPECIFIED`, Master 212 `REGION_ONLY`, and Master 70 `COORDINATE_TEXT_CONFLICT`.
- Other: 0.

Uncertain records remain queued. Queue entry 17 remains pending and is classified as a source candidate check; its raw evidence and database status were not changed.

## E. Coordinates and map

There are 177 coordinate pairs, each matching the exact Furas source geometry. 176 are inside the local reference polygon, 1 (Master 70, Salwa) is outside, 114 are missing, 0 are partial, and 0 are invalid WGS84 pairs. The outside point/title conflict remains under review. For the unfiltered dashboard, 176 points are mapped and 115 are unmapped (114 missing plus 1 outside). For the Al-Ahsa filter set, the same 176 points are mapped and every map point Master ID belongs to the 283 filtered Masters. Map clusters do not create duplicate Master identities.

## F. API, filter, details, map, and exports

At the fixed snapshot the governorate option, opportunities API, dashboard, and geography API each return 283 for the Al-Ahsa filter. The list IDs exactly match confirmed-plus-multi Masters. CSV returns HTTP 200 and 283 records. XLSX returns HTTP 200 and 283 data rows (289 worksheet rows, including six title/header rows). Both exports use the same filter and include country, region, governorate, locality, district, and geography status.

Details show canonical hierarchy, status/reason, preserved source projection, and raw source locations. Unspecified/review cases have no fabricated canonical location and show their review state in the general list/details. Master 228 remains one row and preserves Al-Ahsa, Tabuk, Qassim, Hafr Al Batin, and Northern Borders. A map popup transitions to its matching one-Master filtered list.

Playwright verified RTL, Western digits, filter count, search `44826` (1 row), details/provenance, pagination (page 2 of 6), reset (291), CSV/XLSX, map/list navigation, and all 14 controls inside the toolbar with no page horizontal scrolling at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. Evidence: [Playwright results](screenshots/playwright-geographic-hierarchy.json), [filter screenshot](screenshots/opportunities-location-filter-1920x1080.png), [detail screenshot](screenshots/opportunity-geography-detail-1920x1080.png), [map screenshot](screenshots/dashboard-geographic-map-1920x1080.png).

## G. Data safety and regression

No Master identities, SourceOpportunity links, source raw locations/payloads, observation payloads, or business fields changed. Start/end hashes match: Master identities `33141808…10a1`, source links `297b…f867`, source raw payloads `85e9…aca4d`, observation raw payloads `b62b…9214`. Counts stayed 296 Masters / 291 non-merged / 2,898 source opportunities / 7,603 observations / 1,012 history records / 25 pending location reviews. Queue entry 17's derived report classification was corrected without resolving or changing it in the database.

Full isolated SQLite regression: **143 passed, 0 failed**, one existing Starlette/httpx deprecation warning. Three new geography tests cover hierarchy/aliases, parent filter and pending review behavior, and dashboard/map/export consistency. Sector, Activity, Opportunity Type, Investment Model, and Asset/Facility Type regression tests passed. Workspace, API, and worker standardization engine version: **16**.

Evidence files: [Master reconciliation](master-reconciliation.csv), [exact IDs](exact-set-reconciliation.json), [API/export reconciliation](api-export-reconciliation.json), [map reconciliation](map-reconciliation.json), [open reviews](open-location-reviews.csv), [source coverage](source-coverage.csv), [queue/source evidence](source-and-queue-evidence.json), [start fingerprint](implementation-start-fingerprint.json), [final fingerprint](implementation-final-fingerprint.json), and [regression summary](regression-summary.json).

```ini
LOCATION_GEOGRAPHIC_ELIGIBILITY_DEEP_REVIEW = COMPLETE
SNAPSHOT_TOTAL_MASTERS = 296
SNAPSHOT_ELIGIBLE_MASTERS = 291
AL_AHSA_CONFIRMED_MASTERS = 282
MULTI_LOCATION_WITH_AL_AHSA_MASTERS = 1
LOCATION_REVIEW_REQUIRED_MASTERS = 2
LOCATION_UNSPECIFIED_MASTERS = 6
LOCATION_REVIEW_QUEUE_OPEN = 25
LOCATION_REVIEWS_RESOLVED_WITH_EVIDENCE = 0
COORDINATES_INSIDE_AL_AHSA = 176
COORDINATES_OUTSIDE_AL_AHSA = 1
COORDINATES_MISSING = 114
COORDINATES_INVALID = 0
COORDINATE_LOCATION_CONFLICTS = 1
NATIONAL_RECORDS_INCORRECTLY_PROMOTED_TO_AL_AHSA = 0
AL_AHSA_RECORDS_MISSED_BY_CURRENT_ELIGIBILITY_RULES = 0
UNRESOLVED_EXPLICIT_AL_AHSA_SOURCE_CANDIDATES = 12
UNRESOLVED_CONTRADICTORY_OR_MULTIREGION_SOURCE_CASES = 4
MULTI_LOCATION_MODEL_REQUIRED = FALSE
LOCATION_DIMENSION_SINGLE_VALUED = TRUE
SOURCE_LOCATION_MULTIVALUED = TRUE
INTENTIONAL_LOCATION_DATA_CORRECTIONS = 0
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
LOCATION_API_RECONCILIATION = PASSED
LOCATION_FILTER_RECONCILIATION = PASSED
MAP_RECONCILIATION = PASSED
CSV_LOCATION_RECONCILIATION = PASSED
XLSX_LOCATION_RECONCILIATION = PASSED
BROWSER_LOCATION_VERIFICATION = PASSED
SECTOR_TAXONOMY_REGRESSION = PASSED
ACTIVITY_TAXONOMY_REGRESSION = PASSED
OPPORTUNITY_TYPE_TAXONOMY_REGRESSION = PASSED
INVESTMENT_MODEL_REGRESSION = PASSED
ASSET_FACILITY_TYPE_REGRESSION = PASSED
FULL_REGRESSION_SUITE = 143 passed / 0 failed
STANDARDIZATION_ENGINE_VERSION = 16
```

