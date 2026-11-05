# Final Source Coverage Reconciliation

**Project:** Al-Ahsa Investment Opportunities Platform  
**Fixed snapshot:** 2026-10-20 14:59:31 +03:00 (`Asia/Amman`)  
**Acceptance:** `SOURCE_COVERAGE_COMPLETENESS_DEEP_REVIEW = COMPLETE`

This final reconciliation supersedes the provisional `NOT_COMPLETE` gate recorded in `FINAL-REVIEW.md`. The older report remains as a historical snapshot; the source-ID adjudication is in [adjudicated-source-absences.json](adjudicated-source-absences.json) and machine-readable totals are in [final-reconciliation.json](final-reconciliation.json).

## Master and source snapshot

- 308 Master rows: 287 non-merged/current and 21 merged.
- 2,899 source identities and 11,205 observations.
- All 10 configured sources are enabled. Seven have complete coverage for their stated public scope; three have limited public coverage. Partial, blocked, and unknown coverage states: zero.
- Qualified source records: 312; linked to a Master: 312; without a Master: 0.
- Dashboard, Data Dashboard, and the opportunities API each reconcile to 287 unique Masters.

The final coverage API separates technical health from coverage state and reports total/current/historical source rows, Master-linked current rows, open reviews, pending absence confirmations, and the last successful scan. `GET /api/source-coverage` returns 10 source rows and passed the API reconciliation.

## The 16 absences

### Invest Saudi — 13 reviewed

The read-only comparison covered all four configured public JSON datasets, with no location, status, date, language, or view filter. It returned 1,771 Opportunities, 347 Investment projects, 184 PIF opportunities, and 138 Regional opportunities: 2,440 unique IDs over 26/26 successful pages, with no API errors, partial pages, or cross-dataset duplicate IDs. No target ID/reference was found in any current dataset, and no target matched a replacement ID or a move between the four datasets.

Nine records had already missed two complete scheduled enumerations (jobs 330 and 350). The current complete official enumeration was the third absence confirmation. They now have source lifecycle `أزيلت من المصدر`, three missing checks, and historical dataset membership. Four records were present in job 350 and absent only from the current direct enumeration; they remain current with one absence confirmation and are held for natural scheduled confirmation. They were not guessed away.

| Classification | Count | IDs |
|---|---:|---|
| `CONFIRMED_REMOVED_FROM_SOURCE` | 9 | `investsaudi:52080`, `investsaudi:51540`, `investsaudi:51539`, `investsaudi:51538`, `investsaudi:51537`, `investsaudi:51536`, `investsaudi:51535`, `investsaudi:51518`, `investsaudi:55057` |
| `REVIEW_REQUIRED` | 4 | `investsaudi:51522`, `investsaudi:51517`, `investsaudi:55062`, `investsaudi:55046` |
| Reissued/replaced, scope mismatch, enumeration defect | 0 | — |

Each row’s database ID, official reference, title, lifecycle, last presence timestamp, latest successful scan, current result, raw-payload hash, preserved URL, and Master link are recorded in the JSON artifact. All 13 are unlinked; no Master lifecycle changed.

The final Invest Saudi count reconciles as `2,444 current = 2,440 direct official current + 4 pending confirmations`, plus 111 historical, for 2,555 total source identities. The four pending rows are the only unresolved current-source absences; there are no unexplained extras or missing official IDs.

### King Faisal University — 3 reviewed

The current itemized public announcement listing returned two listings on its complete 1/1 page. All three absent local IDs are unqualified (`qualified=false`) text fragments from general procurement instructions, not distinct official announcement records or stable listing IDs. They have no Master links or official reference IDs. They are classified `ENUMERATION_SCOPE_MISMATCH`, not removed or archived. The two actual current listings are present; none of the three fragments was promoted to an opportunity.

KFU reconciles as five current source identities = two qualified current listings + three retained non-qualified parser fragments, plus one preserved historical source identity. There are zero missing official listings and zero unexplained extras after the scope mismatch is accounted for.

## Furas filters and pagination

The adapter resolves the configured public GIS layer from the official catalogue config. Its ID query sends `f=json`, `returnIdsOnly=true`, and a `where` expression containing 11 verified Al-Ahsa `CITY_ID` values, `OPPORTUNITYACTIVESTATUS='Announced'`, `LASTRFPSELLDATE >= DATE '2026-10-20'`, and `QualifyingOpportunity=0`. It then retrieves ID batches of up to 100 with `outFields=*`, `returnGeometry=true`, and stable `orderByFields=OBJECTID`. There is no region, municipality, language, or server page-number filter.

| Official query | IDs | Interpretation |
|---|---:|---|
| Al-Ahsa city IDs only | 8,084 | Broad geographic universe, all lifecycle states |
| City IDs + `Announced` | 1,941 | Announced rows, including past deadlines |
| City IDs + `Announced` + deadline today/future | 164 | Adapter result |
| City IDs + deadline today/future, no status filter | 171 | 164 Announced + 7 Deleted rows |
| City IDs + `Announced`, no deadline filter | 1,941 | 1,777 have past deadlines; all 1,941 expose `QualifyingOpportunity=0` |

The qualification filter adds no exclusions in the current Announced population; `QualifyingOpportunity=1` returned zero. Every ID excluded by the deadline variant had a past deadline, and the seven additional IDs in the no-status comparison were explicitly `Deleted`. No valid current Al-Ahsa opportunity was missed.

Pagination completed as three requests: one ID enumeration and two feature batches (100 + 64). The adapter returned 164/164 unique IDs, with zero gaps and zero duplicates.

## MODON and MWAN coverage

**MODON:** No public, itemized, current Al-Ahsa availability enumeration is exposed. The review checked the official Arabic and English investment catalogs, public products/ready-factory and Shareek surfaces, public map/GIS schema and open-data metadata/resource interfaces, and public news/sitemap surfaces. These expose programs, general catalog information, or reference geography—not a complete live inventory with Al-Ahsa availability. The platform stores no inferred MODON opportunities. Coverage remains `PUBLIC_COVERAGE_LIMITED`; the current TLS fetch warning is tracked separately. Recheck if MODON publishes a public item-level availability inventory or changes its public catalog/GIS contract.

**MWAN:** A public itemized enumeration does exist for the defined scope of expressly published investment projects. The latest successful scan (job 199) completed 10/10 pages and recorded five specific projects; a sixth extracted content item was not counted as a specific investable project. Five source identities remain preserved. The latest scheduled attempt (job 382) failed TLS before fetching pages, so freshness is stale and technical health is `WARNING`; it did not remove rows. Coverage remains `COMPLETE_FOR_DEFINED_SCOPE`, not a claim that the current TLS-failed attempt freshly enumerated the source. Recheck on a successful scheduled 10/10 scan.

The English NCP public-news archive remains the defined complete scope. Its separately recorded Arabic-mirror continuation gap is outside that canonical scope and is not hidden by the coverage label.

## API, UI, exports, and safety

- Coverage API: 10 enabled sources; status, totals, current/historical rows, Master linkage, review counts, absence confirmations, and last successful scan were read and reconciled.
- Invest Saudi API row: 2,555 total / 2,444 current / 111 historical / 19 current Master-linked / 4 absence confirmations pending; last complete success job 350, 26/26 pages.
- KFU API row: 6 total / 5 current / 1 historical / 2 current Master-linked / 3 unlinked scope fragments; last complete success job 369, 1/1 page.
- Live source page now reads the coverage API rather than presenting a failed latest-attempt counter as source coverage. The browser showed the Invest Saudi current/history/pending counts and the KFU itemized/scope-fragment split. The app is ready; the API, database, Redis, worker, and frontend remain running.
- CSV: HTTP 200, 287 opportunity rows. XLSX: HTTP 200, 287 opportunity rows, worksheet dimension `A1:AF293`.
- No Master rows or source identities were added, deleted, merged, or relinked. All 16 raw payloads and original source URLs remain present and unchanged. Nine confirmed removals have immutable lifecycle snapshots; the review added 18 status snapshots in total. Prior observations were preserved.
- The only Master-level change from source absence: zero. `أزيلت من المصدر` remains distinct from `ملغاة`.

The following jobs occurred naturally; no manual source sync was triggered:

| Job | Source | Result | Coverage effect |
|---:|---|---|---|
| 380 | Furas | Scheduled success, 3/3, 164 IDs | 0 new/updated source rows |
| 381 | Al-Ahsa platform | Scheduled success, 12/12, 103 IDs | 0 new/updated source rows; the prior review recorded +13 observations across jobs 380/381 |
| 382 | MWAN | Scheduled failure, TLS, 0 pages | 0 source-row or observation changes; no absences reconciled |
| 383 | PIF | Scheduled success, 12/13 public routes, no item rows | 0 source-row or observation changes |

The 18 new status snapshots are review evidence, not scheduler output. Test runs used an isolated temporary SQLite database and did not connect to live PostgreSQL. Final full regression: **187 passed / 0 failed**, with one existing Starlette/httpx deprecation warning. The local platform remains ready.

## Final assertions

```ini
SOURCE_COVERAGE_COMPLETENESS_DEEP_REVIEW = COMPLETE
FIXED_VALIDATION_TIMESTAMP = 2026-10-20T14:59:31+03:00
SNAPSHOT_TOTAL_MASTER_ROWS = 308
SNAPSHOT_CURRENT_MASTERS = 287
SNAPSHOT_MERGED_MASTERS = 21
SNAPSHOT_SOURCE_OPPORTUNITIES = 2899
SNAPSHOT_OBSERVATIONS = 11205
CONFIGURED_SOURCES = 10
ENABLED_SOURCES = 10
SOURCES_WITH_COMPLETE_COVERAGE = 7
SOURCES_WITH_PARTIAL_COVERAGE = 0
SOURCES_WITH_LIMITED_PUBLIC_COVERAGE = 3
SOURCES_BLOCKED = 0
SOURCES_UNKNOWN = 0
TECHNICAL_HEALTH_SEPARATE_FROM_COVERAGE = TRUE

CURRENT_SOURCE_ABSENCES_REVIEWED = 16
INVEST_SAUDI_ABSENCES_REVIEWED = 13
INVEST_SAUDI_CONFIRMED_REMOVED = 9
INVEST_SAUDI_REISSUED_OR_REPLACED = 0
INVEST_SAUDI_SCOPE_MISMATCH = 0
INVEST_SAUDI_ENUMERATION_DEFECT = 0
INVEST_SAUDI_REVIEW_REQUIRED = 4
KFU_ABSENCES_REVIEWED = 3
KFU_CONFIRMED_REMOVED = 0
KFU_ARCHIVED_STILL_OFFICIAL = 0
KFU_ENUMERATION_SCOPE_MISMATCH = 3
KFU_ENUMERATION_DEFECT = 0
KFU_REVIEW_REQUIRED = 0
UNRESOLVED_CURRENT_SOURCE_ABSENCES = 4
UNEXPLAINED_CURRENT_SOURCE_ABSENCES = 0
MISSING_OFFICIAL_SOURCE_RECORDS = 0
UNEXPLAINED_EXTRA_SOURCE_RECORDS = 0

INVEST_SAUDI_OFFICIAL_CURRENT = 2440
INVEST_SAUDI_ENUMERATED = 2440
INVEST_SAUDI_PLATFORM_CURRENT = 2444
INVEST_SAUDI_PLATFORM_HISTORICAL = 111
INVEST_SAUDI_PLATFORM_TOTAL = 2555
INVEST_SAUDI_PENDING_ABSENCE_CONFIRMATIONS = 4
KFU_OFFICIAL_ITEMIZED_CURRENT = 2
KFU_PLATFORM_CURRENT = 5
KFU_PLATFORM_HISTORICAL = 1
KFU_PLATFORM_TOTAL = 6

FURAS_FILTERS_AUDITED = TRUE
FURAS_ADAPTER_ENUMERATED_IDS = 164
FURAS_BROADER_OFFICIAL_IDS = 164
FURAS_VALID_AL_AHSA_RECORDS_MISSED_BY_FILTERS = 0
FURAS_PAGES_EXPECTED = 3
FURAS_PAGES_ENUMERATED = 3
FURAS_UNIQUE_IDS_ENUMERATED = 164
FURAS_PAGINATION_GAPS = 0
FURAS_PAGINATION_DUPLICATES = 0
FURAS_COVERAGE_STATUS = COMPLETE_PUBLIC_SOURCE
ALAHSA_PLATFORM_OFFICIAL_VISIBLE = 103
ALAHSA_PLATFORM_ENUMERATED_UNIQUE = 103
ALAHSA_PLATFORM_SOURCE_RECORDS = 103
ALAHSA_PLATFORM_MISSING = 0
MODON_PUBLIC_ITEMIZED_ENUMERATION_AVAILABLE = FALSE
MODON_COVERAGE_STATUS = PUBLIC_COVERAGE_LIMITED
MWAN_PUBLIC_ITEMIZED_ENUMERATION_AVAILABLE = TRUE
MWAN_COVERAGE_STATUS = COMPLETE_FOR_DEFINED_SCOPE

QUALIFIED_SOURCE_RECORDS = 312
QUALIFIED_SOURCE_RECORDS_WITH_MASTER = 312
QUALIFIED_SOURCE_RECORDS_WITHOUT_MASTER = 0
LOCATION_REVIEW_REQUIRED_CURRENT_DB = 15
SOURCE_TECHNICAL_DUPLICATES_REMAINING = 0
ORPHANED_SOURCE_RECORDS = 0
ACTIVE_SOURCE_RECORDS_WITH_ZERO_OBSERVATIONS = 0
ORPHANED_OBSERVATIONS = 0
ENABLED_WITHOUT_EXPECTED_SCHEDULE = 0
REMOVAL_DETECTION_REQUIRES_COMPLETE_SUCCESSFUL_SCAN = TRUE
PARTIAL_SCAN_CAN_TRIGGER_FALSE_REMOVALS = FALSE
MASTER_LIFECYCLE_CHANGES_CAUSED_SOLELY_BY_SOURCE_ABSENCE = 0
REMOVED_SOURCE_HISTORY_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
API_COVERAGE_RECONCILIATION = PASSED
DASHBOARD_MASTER_RECONCILIATION = PASSED
CSV_MASTER_RECONCILIATION = PASSED
XLSX_MASTER_RECONCILIATION = PASSED
BROWSER_COVERAGE_VERIFICATION = PASSED
FULL_REGRESSION_SUITE = 187 passed / 0 failed
```
