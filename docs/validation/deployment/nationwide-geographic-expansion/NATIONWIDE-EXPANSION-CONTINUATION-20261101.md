# Nationwide Expansion — Safe Continuation Review

**Project:** Al-Ahsa Investment Opportunities Platform  
**Review date:** 2026-11-01 (Asia/Amman)  
**Scope:** Revalidated live baseline, official geography candidates, safe code foundation, Furas scan/removal safeguards, Invest Saudi read-only eligibility, existing source coverage, tests and live read-only DQ.  
**Outcome:** Safe foundation and dry-run work are complete. Nationwide collection, reference population, production migration, national filters and national map remain disabled.

## Update — live recheck and official acquisition path (2026-11-01 14:25 +03)

This section supersedes earlier statements below wherever they describe the latest live state. Read-only checks confirmed the local services are running and `/health/ready` returns `ready`; no service restart or manual synchronization was performed. A new read-only database snapshot was captured at `2026-11-01T11:24:20Z` and saved to `tmp/nationwide-live-snapshot-current.json`.

- Current counts: **587 Masters (566 current), 3,180 SourceOpportunity rows, 34,011 observations, 662 jobs, 0 active jobs**, and Alembic `0023_quant_commercial`. Against the 10:50 snapshot, Master, current Master and SourceOpportunity totals are unchanged; observations are +634 and jobs are +10. No open duplicate candidates or conflicts were present. The current snapshot reports 0 qualification reviews and 26 location reviews. Automated jobs also increased change-history and system-event counts, so the earlier “no changes after baseline” statement applies only to the 10:50 capture.
- Furas Job 651 remains a historical deadlock failure. The platform later ran automatic retry Job 657 and scheduled Job 662. Job 662 completed with 5/5 pages, 375 unique records and 0 removals. These jobs were observed after the fact; none was started manually for this review. National enumeration was not enabled or verified live.
- The latest persisted post-sync **fast** DQ event for Job 662 had 48 PASS and 1 FAIL (`SYNC_JOB_STATE_CONSISTENCY`, sample 662). A later full read-only evaluation (`run_id=10d06d7db1474849810c5365b32db28f`, completed 14:24:57 +03, `persist=false`) evaluated 133 gates: **129 PASS, 4 WARNING, 0 FAIL**. The warnings were `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION` (782), `HISTORICAL_REVIEW_AUDIT_INCOMPLETE` (120), `SOURCE_LAST_SUCCESS_TOO_OLD` (3), and `SYNC_RUNTIME_ANOMALY` (6). The newer full result removes the earlier Furas freshness failure, but the fast/full job-lifecycle discrepancy remains recorded and was not investigated further. This evaluation was read-only and did not create a DQ event.
- Official-source review found GEOSA identifies the [2026 Official Saudi Map](https://www.geosa.gov.sa/en/About/Pages/OfficialSaudiMap.aspx) as the approved reference for national borders and administrative regions; its [product page](https://geoportal.geosa.gov.sa/Geoportal/GeospatialOpenData/OfficialSaudiMap) describes digital GeoPDF/GeoTIFF delivery on request. GEOSA’s [2026 public notice](https://geosa.gov.sa/ar/mediacenter/news/Pages/Newas30080026.aspx) says the National Geographic Names Database was recommended as the national reference for geographic names. The public [Open Data “Geographical Names” page](https://www.geosa.gov.sa/en/Pages/Open_data.aspx) describes names for regions, governorates, centers and villages, but its linked download remains an aggregate XLSX, not a row-level administrative register. None of these public materials established a complete structured Region → Governorate → City table with stable IDs, parent IDs, effective version, and reuse terms. Therefore **no production reference was adopted**. An authorized acquisition inquiry can be directed through GEOSA’s published `ngc@geosa.gov.sa` / `care@geosa.gov.sa` contacts on the [contact page](https://www.geosa.gov.sa/en/Pages/Contact-us.aspx); no inquiry was sent as part of this review.

**Current decision:** nationwide features remain disabled. DQ has no failing gate in the latest full read-only evaluation, but reference acquisition, live deployment/migration, live verification of the national-scan safeguards, and resolution of the fast/full lifecycle discrepancy remain outstanding. The existing Al-Ahsa experience remains the live default.

## Executive result

No current, complete, authorized, licensed administrative hierarchy suitable for production was established from the reviewed public candidates. No reference rows were imported. The code now supports a versioned, provenance-aware geography dimension and fail-closed API filters, but it has **not** been deployed or migrated on the live service. National Furas enumeration was not enabled or verified live. No manual source synchronization, review mutation or live schema migration was started as part of this continuation; the platform ran scheduled/retry jobs after the initial snapshot, as recorded above.

The initial read-only live snapshot was captured at `2026-11-01T10:50:56+03:00`; the later update above captures the current post-scheduled-job state. All 11 configured sources remain in the registry: 10 enabled and Waha disabled.

The initial full read-only DQ run reported 133 gates: 129 PASS, 3 WARNING, 1 FAIL. The newer full read-only evaluation and its warnings are recorded in the update above; national functionality was not enabled.

## A. Geographic reference findings

| Candidate | Operator and access | Administrative content and IDs | Version, licensing, completeness | Production finding |
|---|---|---|---|---|
| [GEOSA Open Data](https://www.geosa.gov.sa/en/Pages/Open_data.aspx) | General Authority for Survey and Geospatial Information (GEOSA); public catalog page and downloadable item inspected. | The “Geographical Names” download available in this review is an aggregate XLSX of feature types/counts, not a row-level administrative register. It supplies no stable region/governorate/city keys or parent IDs. | GEOSA states open-data reuse is subject to the dataset's license and attribution. The inspected file does not provide a usable administrative hierarchy or a sufficient current hierarchy/version contract. | **Not suitable** for populating administrative units. |
| [Ta’adeen Governorates layer](https://gis.taadeen.sa/server/rest/services/Common/BaseMaps/MapServer/2?f=pjson) | Government mining-platform GIS host; feature query is publicly readable. The layer is described as basemap data, but the service item does not establish the data custodian's reuse authorization. | 149 features; 149 unique `Governorate_Code` values and GlobalIDs; Arabic/English names and an `Emirates_Ar`/`Emirates_En` parent label. The parent is a name, not a parent-region identifier. | Feature source label is `Governorate_المحافظات_2023`; all observed last-edited values are 2024-10-29. Service/item created or modified in 2026 does not establish source currency. No license/attribution terms were found in item metadata. The count conflicts with GASTAT's 150/151 published denominators. | Public query permission is not reuse permission; source version and completeness are unresolved. **Not suitable** for production. |
| [NCM TileServer](https://meteo.ncm.gov.sa/tileserver/) | National Center for Meteorology hosted vector tiles; public TileJSON/catalog access. | Listed region, governorate, centroid and city layers. Region/g governorate tiles expose apparent IDs, but governorate counts are 149; centroid layers are display geometries, not opportunity coordinates. City schema/source and administrative definition are undocumented. | Tile attributes identify source as a GASTAT statistical boundaries map dated 20 June 2019. TileJSON has no current effective date or reuse license. | Historical statistical tiles do not establish current administrative identifiers or licensed reuse. **Not suitable** for production. |
| [GEOSA National Geospatial Platform](https://geoportal.geosa.gov.sa/Geoportal/) and [Official Saudi Map](https://geoportal.geosa.gov.sa/Geoportal/GeospatialOpenData/OfficialSaudiMap) | GEOSA-operated national portal. The public map product is discoverable; its map service describes GeoPDF/GeoTIFF delivery by request. The public FAQ describes submitting a geospatial data request. | Official map product supports national map/boundary viewing or requested map output; this review did not obtain a structured administrative-units table with stable IDs and parent keys. | The portal's public descriptions do not establish a downloadable hierarchy's license, effective date, or exact account/key requirement. A request/approval path is indicated; no access controls were bypassed. | **Potential authorized acquisition path**, but not a currently available structured production reference. Obtain the dataset and its terms through GEOSA's stated request process. |
| GASTAT cross-check | General Authority for Statistics methodological publications. | Publications refer to 150 or 151 governorates while using 13 regions. | The [Health and Safety at Work 2025 methodology](https://stats.gov.sa/en/w/methodology-and-quality-report-for-health-and-safety-at-work-statistics-2025) cites 151; [Volunteer Work methodology](https://stats.gov.sa/en/w/methodology-and-quality-report-for-volunteer-work-statistics) cites 150. A recent household-energy methodology uses the 2022 Census sample frame and 150 governorates as statistical strata ([PDF](https://www.stats.gov.sa/documents/20117/2435133/Methodology%2Band%2BQuality%2BReport%2Bfor%2BHousehold%2BEnergy%2BStatistics_EN.pdf/230beeeb-f6eb-80bf-adc8-525356db672c?t=1764132442851)). | These figures are statistical frames/denominators, not a versioned administrative-unit roster. No primary evidence found in the inspected material proves a boundary change explaining the 150/151 difference. | Keep the discrepancy unresolved; do not hand-build or guess a roster. |

**Conclusion:** No production reference was adopted. An independently complete and licensed region/governorate dataset could be adopted without claiming complete city coverage; the implemented coverage contract allows levels to remain explicitly incomplete. City-level selection and national boundaries remain unavailable until their own provenance, completeness and reuse terms are verified.

## B. Furas safety

### Job 651 finding

Job 651 failed before fetching a page: zero requested/successful pages, zero records and zero removals. Its PostgreSQL error was `DeadlockDetected` while updating `opportunities.last_seen_at` for Master 249. Job 644 shows a similar earlier failure. Job 652 (Al-Ahsa source 2) started in the same second as 651 and succeeded; workers were distinct, but the available job metadata does not map PostgreSQL process IDs to individual job tasks, so the exact opposing transaction cannot be proven. Concurrent updates to shared Masters are consistent with the observed deadlock, not a proven single blocking job.

The later live snapshot shows Job 657 (`retry`) and Job 662 (`scheduled`) both succeeded. Job 662 returned 375 unique rows in five successful pages with no removals. This is an observed scheduled recovery of source freshness; it is not live validation of the local Furas nationwide-scan safeguards.

### Implemented safeguards (not live deployed)

- Source enumeration and Master geographic eligibility are separate. National enumeration is controlled by `FURAS_NATIONAL_ENUMERATION_ENABLED`, default `false`; existing exact reviewed Al-Ahsa `CITY_ID`s alone remain eligible for local Master treatment.
- Furas presence/removal identity is based on the full enumerated scan population, not only locally eligible Masters.
- Count query, unique ID enumeration and every requested ObjectID page must agree. Partial or failed pages fail closed.
- Missing-record reconciliation requires a complete, verified scan whose scope is equal to or broader than the preceding successful scope. A national scan can widen a local scope; a partial, unknown, zero-page, or narrower scan cannot remove records.
- A PostgreSQL transaction-scoped advisory lock serializes ingestion write transactions across workers after network collection and before shared writes. This prevents the app's concurrent ingestion write ordering from interleaving. A database deadlock still aborts its transaction atomically; the scheduled retry remains the recovery path. No manual retry was made.

**FURAS_NATIONAL_SCAN_SAFETY:** implemented and tested in isolation, flag off, not live verified. Therefore national Furas enumeration is **not yet safe to run in the live platform**. Deployment, live lock/transaction verification, DQ recovery and a separate approved source-specific run are still required.

## C. Invest Saudi read-only reevaluation

The live read-only dry-run assessed all 2,536 unlinked rows among 2,555 retained source rows. It did not promote or link records.

| Bucket | Count | Meaning |
|---|---:|---|
| A — evidenced legitimate candidates | 0 | No row met the strict active/open/announced + official detail URL + specific offering evidence contract. |
| B — potential, more evidence needed | 2,168 | Retained candidates requiring lifecycle, offering and/or geography evidence; not auto-promoted. |
| C — generic/promotional | 157 | Public material without sufficient current specific-offer evidence. |
| D — exact existing Master match | 0 | No exact source identity match justified a new link in this pass. |
| E — absent from current endpoint membership | 211 | Historic/absent snapshot members retained; not deleted or reclassified as invalid. |

Additional evidence: 532 rows lack raw geographic evidence; zero had explicit source coordinates; zero exact official-URL duplicates and zero exact source-reference matches were found; 27 repeated-title groups were flagged as risks only, not deduplicated. There were zero promotions. Safe next action is source-specific evidence enrichment or a separately approved review batch after geography and eligibility evidence becomes available.

## D. Implemented foundation

- Added nullable scope/provenance fields for opportunity geography and opportunity-location evidence. Existing Al-Ahsa fields and Master identifiers remain unchanged.
- Added versioned reference-dataset and reference-unit models plus migration `0024_national_geography`. No reference records were seeded.
- Added validation/dry-run and transactional versioned import/rollback with required dataset metadata, license attestation, stable-ID attestation, duplicate checks, parent-chain validation, content digest and immutable dataset versions.
- Added API query contract support for country/region/governorate/city IDs and scopes: `SPECIFIC_LOCATION`, `MULTIPLE_VERIFIED_LOCATIONS`, `REGION_WIDE`, `NATIONWIDE`, `UNSPECIFIED`. Default queries remain backward compatible; incomplete/unverified selectors fail closed; map coordinates are not synthesized.
- Geography catalog reports only levels covered by a current, license-verified reference. With no imported reference it advertises no active selectors and no national map.
- The existing frontend and Al-Ahsa default were not changed. No nationwide selectors or map were enabled.

**Migration validation:** migration 0024 upgraded successfully on an isolated PostgreSQL 16 database stamped at the live pre-change revision 0023. The live database remains at 0023; no live migration was applied. A separate empty-database full-chain attempt hit a pre-existing error at revision 0022 (`canonical_status` already exists); that older migration/bootstrap issue is outside this geography change and remains a fresh-install concern.

## E. Existing source coverage and expansion decision

| Source | Present scope / national eligibility | What changed |
|---|---|---|
| Furas | Public GIS endpoint appears nationally enumerable; live installed adapter is Al-Ahsa `CITY_ID` scoped. National data cannot become local Masters without exact reviewed location IDs. | Safety code only; flag remains off; no run. |
| Al-Ahsa Opportunities | Dedicated Municipality of Al-Ahsa listings. | Remains local by source definition. |
| AHDA | Defined AHDA institutional/campus scope. | Remains source-defined. |
| Invest Saudi | Four public paginated datasets already collected nationally; current Master qualification is more restrictive. | Read-only dry-run only; no promotions. |
| KFU | University investment announcements. | Remains publisher-defined; no nationwide inference from publisher location. |
| MODON | Public reference/catalog/GIS material; no verified itemized current public opportunity inventory. | No expansion. |
| NCP | Public English news archive; national programs exist, but news is not automatically a live project offer. | No national promotion; specific public solicitations require evidence review. |
| NHC | Public categories and application/qualification routes; no itemized public current inventory verified. | No expansion into private/authenticated listings. |
| PIF | Public ecosystem/company route monitoring, no deterministic itemized live opportunity population. | Remains limited public coverage. |
| MWAN | Specific public project routes; potentially multi-region, but published projects are not a complete private pipeline. | No source-wide backfill; no promotions. |
| Waha Development | Disabled catalog entry; no supported opportunity adapter; public GIS is portfolio/location evidence. | Remains disabled. |

No source-specific nationwide backfill was started. Source freshness and public coverage were not changed by this work.

## F. Integrity and validation

| Measure | Pre-change baseline | Latest live read-only snapshot | Result |
|---|---:|---:|---|
| Masters total | 587 | 587 | unchanged |
| Current Masters | 566 | 566 | unchanged |
| SourceOpportunity | 3,180 | 3,180 | unchanged |
| Source observations | 33,377 | 33,377 | unchanged |
| Source jobs | 652 | 652 | unchanged |
| Active jobs | 0 | 0 | unchanged |
| Open duplicate reviews | 0 | 0 | unchanged |
| Open conflicts / qualification reviews | 0 / 0 | 0 / 0 | unchanged |
| Alembic live head | 0023 | 0023 | unchanged |

Furas Job 651 remains failed and unchanged; it has zero pages and zero removals. The previous successful Furas scan is Job 639 (375 records, complete, zero removals); prior Phase-A text naming Job 643 as the last complete success was inaccurate and is superseded by this job-history recheck. No rows or IDs were deleted or rewritten by this continuation.

### DQ warning/failure reconciliation — initial capture

Initial captured live DQ: **133 gates; 129 PASS, 3 WARNING, 1 FAIL**. The newer full read-only result is in the update section above.

- `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY_ACTION`: 782 generic source/listing pages are attached as opportunity actions; accepted source-link limitation.
- `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`: 120 pre-versioned historical review records lack complete actor/audit detail; identities were not invented.
- `SYNC_RUNTIME_ANOMALY`: 6 historical job runtime anomalies (samples 496, 645, 500, 561, 649, 563).
- `SOURCE_LAST_SUCCESS_TOO_OLD`: **FAIL in the initial run**, Furas source ID 1 after Job 651. The subsequent scheduled Job 662 completed successfully; the latest full read-only run reports this gate as WARNING with three sources and no DQ failures overall.

MODON (ID 6) and NHC (ID 8) were warning sources in the initial snapshot. The latest full result reports three warning sources in the freshness gate; their identities are not inferred here. Keep nationwide functionality disabled until the authoritative reference and live deployment requirements are met; also reconcile the fast/full `SYNC_JOB_STATE_CONSISTENCY` difference before treating lifecycle validation as settled.

### Tests

- Focused nationwide, Furas, ingestion/geography/API regression: **46 passed, 0 failed** in the first focused run.
- Follow-up focused contract/safety tests after updating legacy Furas mocks: **17 passed, 0 failed**.
- Full isolated regression (`pytest -q tests/`, excluding archived transfer snapshots): **614 passed, 0 failed** (40 deprecation warnings).
- Target migration 0024 upgrade: passed on disposable PostgreSQL at 0023.
- Live DQ: 129 PASS, 3 WARNING, **1 FAIL**; no DQ gate was weakened.

## G. Remaining blockers and separate statuses

```ini
PHASE_A_PREFLIGHT = COMPLETE_REVALIDATED
GEOGRAPHIC_REFERENCE = NOT_AVAILABLE_FOR_PRODUCTION
GEOGRAPHIC_FOUNDATION = IMPLEMENTED_AND_TESTED_NOT_LIVE_DEPLOYED
FURAS_NATIONAL_SCAN_SAFETY = IMPLEMENTED_AND_TESTED_FLAG_OFF_NOT_LIVE_VERIFIED
INVEST_SAUDI_NATIONAL_REEVALUATION = READ_ONLY_DRY_RUN_COMPLETE_NO_PROMOTIONS
NATIONAL_API = IMPLEMENTED_AND_TESTED_NOT_LIVE_DEPLOYED
NATIONAL_FILTERS = FAIL_CLOSED_NO_VERIFIED_REFERENCE
NATIONAL_MAP = NOT_ENABLED_NO_VERIFIED_BOUNDARIES
EXISTING_SOURCE_EXPANSION = REVIEWED_NO_BACKFILL
NATIONWIDE_EXPANSION = PARTIAL_SAFE_FOUNDATION_NOT_COMPLETE

LIVE_MASTERS_BEFORE_AFTER = 587 / 587
LIVE_CURRENT_MASTERS_BEFORE_AFTER = 566 / 566
LIVE_SOURCE_OPPORTUNITIES_BEFORE_AFTER = 3180 / 3180
LIVE_SOURCE_OBSERVATIONS_BEFORE_AFTER = 33377 / 33377
LIVE_SOURCE_JOBS_BEFORE_AFTER = 652 / 652
LIVE_ACTIVE_JOBS = 0
LIVE_ALEMBIC_HEAD = 0023
LIVE_SCHEMA_MIGRATION_APPLIED = FALSE
GEOGRAPHY_REFERENCE_ROWS_IMPORTED = 0
INVEST_SAUDI_RECORDS_PROMOTED = 0
FURAS_NATIONAL_FLAG_ENABLED = FALSE
MANUAL_SOURCE_SYNC_STARTED = FALSE
BUSINESS_DATA_CHANGES = 0
REVIEW_DATA_CHANGES = 0
SOURCE_ROWS_DELETED = 0
```

Remaining blockers: (1) acquisition of an authorized, versioned and licensed administrative reference; (2) live deployment and migration of the tested foundation; (3) live verification of the national Furas scan safeguards and reconciliation of the fast/full job-lifecycle DQ discrepancy before any national run; (4) the existing empty-database migration-chain issue at 0022 for fresh-install validation. The prior Furas freshness failure is resolved by a scheduled complete scan, but the full DQ run still has four warnings. The Al-Ahsa experience remains the live default and was not modified.
