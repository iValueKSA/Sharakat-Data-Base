# Live validation — dedicated 13 Saudi Regions filter

**Date:** 2026-11-02  
**Target:** `alahsa-local`, `http://localhost:8080`  
**Environment:** `ENVIRONMENT=local_user`  
**Result:** `LIVE_13_REGION_FILTER=COMPLETE`

## Acceptance summary

| Requirement | Result | Evidence |
|---|---|---|
| Opportunities screen shows the dedicated `المنطقة` filter | PASS | Visible top-level filter beside the dependent `المحافظة` and `المدينة` controls |
| Data Dashboard shows the same filter | PASS | Visible top-level filter in the dashboard geography panel |
| Exactly 13 canonical Regions, plus `جميع المناطق` | PASS | 13 canonical IDs from the loaded geographic reference; 14 options including all-regions |
| No Governorates/Cities mixed into the Region menu | PASS | Region menu contains only the 13 required Region labels |
| Region → Governorate → City dependency | PASS | Governorates narrow by Region; Al-Ahsa locality remains available under Governorate 501; changing Eastern Province to Riyadh clears Governorate and City on both screens |
| Dashboard propagation and list parity | PASS | Region total, status, source, sector and deadline metrics use the Region-filtered Master set; dashboard and list totals match |
| CSV/XLSX export parity | PASS | All-regions, Eastern, Riyadh and Makkah exports match API totals |
| RTL responsive layout | PASS | Both screens checked at all five required viewport sizes |
| Business data / sync / schema changes | NONE | Read-only acceptance checks; no syncs or migration created |

## Canonical Region choices

`REGION_OPTIONS_COUNT=13` (excluding `جميع المناطق`). Each option was present (`TRUE`) and used its canonical Region ID:

| Required option | Present |
|---|---|
| الرياض | TRUE |
| مكة المكرمة | TRUE |
| المدينة المنورة | TRUE |
| القصيم | TRUE |
| المنطقة الشرقية | TRUE |
| عسير | TRUE |
| تبوك | TRUE |
| حائل | TRUE |
| الحدود الشمالية | TRUE |
| جازان | TRUE |
| نجران | TRUE |
| الباحة | TRUE |
| الجوف | TRUE |

Displayed order: `جميع المناطق` followed by the 13 labels above in canonical reference order. The Region control does not contain Governorate or City choices.

## Live counts and hierarchy

Counts are unique current Master opportunities, not source rows.

| Selection | Live total |
|---|---:|
| `جميع المناطق` | 6,623 |
| `المنطقة الشرقية` (Region ID 5) | 975 |
| `الرياض` (Region ID 1) | 800 |
| `مكة المكرمة` (Region ID 2) | 319 |
| Eastern Province → Al-Ahsa (Governorate ID 501) | 518 |
| Eastern Province → Al-Ahsa → الهفوف (`al_ahsa_locality:hofuf`) | 3 |

`ALAHSA_FALSE_POSITIVES=0` and `ALAHSA_FALSE_NEGATIVES=0`: all 518 returned Al-Ahsa Masters had canonical Governorate ID 501, were unique by Master ID, and matched the Al-Ahsa selector count. Al-Ahsa is included under the Eastern Province Region.

`REGION_GOVERNORATE_DEPENDENCY=PASSED` — Eastern Province options included Al-Ahsa and excluded Riyadh Governorates. Changing Eastern Province to Riyadh reset the selected Governorate and City.

`REGION_CITY_DEPENDENCY=PASSED` — the existing Al-Ahsa City/locality filter remained available beneath Governorate 501. The selected الهفوف UI total matched its API result (3). Changing the Region to Riyadh cleared the City and its URL filter on both Opportunities and Dashboard.

During this validation, the retained locality API predicate was found to roll a locality up to its whole Governorate. It was corrected to match the selected canonical locality; parent Region/Governorate predicates are treated as implied when they match that locality’s canonical ancestry. The live API now returns the three الهفوف Masters for the combined Region + Governorate + City selection, and returns no results if a conflicting parent is chosen.

## Dashboard propagation and composition

`DASHBOARD_REGION_FILTER_PROPAGATION=PASSED` and `DASHBOARD_LIST_REGION_PARITY=PASSED`:

| Region | Dashboard total | Opportunities total |
|---|---:|---:|
| Eastern Province | 975 | 975 |
| Riyadh | 800 | 800 |
| Makkah | 319 | 319 |

The Eastern dashboard response also reconciled its status and sector distributions to 975, included source distribution, and applied the Region to deadline metrics (`deadline_distribution_total=914`). The map endpoint accepted Region ID 5 and returned 975 filtered records while retaining `map_scope=AL_AHSA` (`unmapped=475`). National map/dashboard feature flags remained disabled, so the existing local map scope was preserved.

`FILTER_COMPOSITION=PASSED` — live API combinations:

- Eastern Province + commercial sector: 808; dashboard total and sector-chart total both 808.
- Riyadh + Furas source: 800.
- Makkah + status `متاحة`: 319.
- Asir + title search `انشاء و ترمي`: 20.
- Eastern Province + Al-Ahsa + الهفوف: 3, consistent between UI and API.

## Exports, pagination, reset

`REGION_API_CSV_XLSX_PARITY=PASSED`:

| Export filter | CSV data rows | XLSX data rows | API total |
|---|---:|---:|---:|
| All Regions | 6,623 | 6,623 | 6,623 |
| Eastern Province | 975 | 975 | 975 |
| Riyadh | 800 | 800 | 800 |
| Makkah | 319 | 319 | 319 |

The workbook’s six title/metadata rows were excluded from the data-row count. The local Nginx XLSX route allows up to 240 seconds for the existing large export generation; the live 6,623-row workbook completed successfully.

`PAGINATION=PASSED` — the Eastern list returned 50 rows on each of pages 1 and 2 with no duplicate IDs; the filtered total was 975.  
`RESET=PASSED` — clearing filters restored 6,623 and cleared the Region selector.

## Responsive, runtime and deployment checks

Both Opportunities and Dashboard were checked at each viewport. RTL was true, the Region control was visible and contained in the viewport, and `documentWidth == viewportWidth` for every check:

| Viewport | Result |
|---|---|
| 1920 × 1080 | PASS |
| 1440 × 900 | PASS |
| 1366 × 768 | PASS |
| 768 × 900 | PASS |
| 390 × 844 | PASS |

`RTL=PASSED`  
`HORIZONTAL_OVERFLOW=0`  
`JS_ERRORS=0`  
`UNEXPECTED_5XX=0`

The live browser validation used a temporary `/api/auth/me` route stub with a synthetic admin identity solely to open the UI. All geographic, opportunity and dashboard data calls went to the live local API; no account or credential was changed. Full browser results, screenshots and export samples are in [live-13-region-filter-evidence](live-13-region-filter-evidence/).

Deployment pairing: `docker-compose.yml` + `docker-compose.local.yml`, Compose project `alahsa-local`. API, database and Redis reported healthy; frontend, worker and scheduler were running. The readiness endpoint returned `ready`.

`BUSINESS_DATA_CHANGES=0`  
`MANUAL_SOURCE_SYNCS=0`  
`SCHEMA_CHANGES=0`

No Masters, source links, geographic assignments, reviews or statuses were changed. No sync was run. Alembic current and head both reported `0025_source_geographic_coverage`; no upgrade ran. The startup local bootstrap reported `ALREADY_IMPORTED` and referenced its existing 2026-10-13 import report; it did not import rows during this task.

## Changed implementation and verification

- [app/static/index.html](../../../../app/static/index.html): dedicated visible Region / Governorate / City controls in both screens; removed the old combined control and hidden national dashboard geography panel.
- [app/static/national-geography.js](../../../../app/static/national-geography.js): shared canonical Region and dependent Governorate selectors; preserved the Al-Ahsa locality selector and parent-change resets.
- [app/static/app.js](../../../../app/static/app.js): dashboard Region/Governorate filter wiring and reset behavior.
- [app/main.py](../../../../app/main.py): precise locality matching and consistent hierarchy composition for selected parent filters.
- [deploy/nginx.conf](../../../../deploy/nginx.conf): XLSX export timeout route for the verified 6,623-Master export.
- [tests/test_nationwide_expansion_safety.py](../../../../tests/test_nationwide_expansion_safety.py) and [tests/test_location_geography.py](../../../../tests/test_location_geography.py): Region parity and locality-specific regression coverage.

Focused tests: `54 passed, 1 skipped, 1 warning` across `test_nationwide_expansion_safety.py`, `test_location_geography.py`, and `test_data_dashboard.py`. JavaScript syntax checks passed for `national-geography.js` and `app.js`.

**Stop condition reached:** the 13-Region filter task is deployed and validated. National source discovery was not continued.
