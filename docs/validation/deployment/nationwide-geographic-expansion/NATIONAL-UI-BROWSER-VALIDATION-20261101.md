# Nationwide UI browser validation — 2026-11-01

**Result:** `PASSED` in isolated test environments. Both the City-present and City-absent reference variants passed all 56 Playwright checks. This is technical predeployment evidence only; it does not authorize a production rollout.

## Environment and safeguards

- Disposable Docker network: `nwx-ui-test-20261101`; disposable PostgreSQL 16 and two isolated app instances.
- City-present app: `http://127.0.0.1:18089`; City-absent app: `http://127.0.0.1:18090`.
- Restored from the verified pre-change backup, then migrated through `0024` and `0025_source_geographic_coverage` in the disposable DBs only.
- `NATIONAL_UI_ENABLED=true`, `NATIONAL_MAP_ENABLED=true`, and `NATIONAL_DASHBOARD_ENABLED=true` only in the isolated instances; `FURAS_NATIONAL_ENUMERATION_ENABLED=false`. No source jobs were started in these environments.
- The restored baseline had 566 current Masters. The isolated fixture added 60 unmistakable `TEST_*` Masters and 61 source rows, so UI/API test cases use `q=TEST` to isolate the synthetic data. The fixture has no official Saudi administrative IDs or names.
- City-present reference: 7 test units (country, region, two governorates, three cities). City-absent reference: 4 test units (country, region, two governorates), with no City level in the catalog.
- Two synthetic verified-coordinate points represent two unique mapped Masters and three point memberships; one Master legitimately has two locations. No coordinates were fabricated. Nationwide, region-wide, unspecified, or unverified locations did not create points.
- The Al-Ahsa quick-view check used a test-only resolver alias to the synthetic governorate. It verifies resolver behavior without claiming the test ID is the official Al-Ahsa identity or changing production Al-Ahsa behavior.

## Browser result

The Playwright driver ran 28 checks for each reference variant, **56 passed, 0 failed**. It reported **0 JavaScript errors** and **0 unexpected HTTP 5xx**.

| Capability | Result | Evidence |
|---|---|---|
| National Opportunities selectors and defaults | Passed | Region and Governorate defaults displayed; City displayed and functional only in the City-present reference |
| Dependent filters | Passed | Region constrained Governorates; Governorate constrained Cities; parent changes cleared incompatible children |
| No-City handling | Passed | Region/Governorate work; City hidden/disabled; no invalid City-options request was emitted |
| Al-Ahsa quick-view resolver | Passed, test-only | Test alias resolved from the fixture; no synthetic future ID hardcoded in the UI |
| Combined filters and search | Passed | Region + sector, Governorate + status, Governorate + source, and search + geography returned expected synthetic Master counts |
| Pagination, URL state, and reset | Passed | Filter state persisted through pagination/URL; reset restored geographic defaults |
| Sorting | Passed | Title sort retained Region, Governorate, and Status query filters |
| Duplicate Master semantics | Passed | Dashboard totals counted 60 unique Masters despite 61 source rows |
| Dashboard scope summaries and drilldown | Passed | Mapped, nationwide, and unspecified counts were distinct; Region drilldown navigated with the correct test ID |
| National map semantics | Passed | Map followed the Region filter; broad scopes produced no fake points; popup opened the matching opportunity detail |
| Arabic RTL and layout | Passed | RTL and no text/control overlap at the tested viewports; no horizontal overflow |

Dashboard scope check in each variant: 60 unique TEST Masters, 61 source rows, 2 mapped unique Masters, 1 `NATIONWIDE`, and 1 `UNSPECIFIED` (`LOCATION_UNSPECIFIED` in the requested terminology). The map reported two unique Master IDs across three point memberships, confirming that multiple locations do not inflate the unique Master total. `NATIONWIDE`, `REGION_WIDE`, and `UNSPECIFIED` remained separate from physical map points.

### CSV/XLSX UI/API parity

Each of these downloads was initiated from the filtered Opportunities UI. The saved CSV and XLSX files were parsed to count exported data rows.

| Reference | Filter | UI | API | CSV | XLSX | Result |
|---|---|---:|---:|---:|---:|---|
| City | Region | 57 | 57 | 57 | 57 | Pass |
| City | Governorate | 29 | 29 | 29 | 29 | Pass |
| City | Region + sector | 28 | 28 | 28 | 28 | Pass |
| City | Governorate + status | 20 | 20 | 20 | 20 | Pass |
| No City | Region | 57 | 57 | 57 | 57 | Pass |
| No City | Governorate | 28 | 28 | 28 | 28 | Pass |
| No City | Region + sector | 28 | 28 | 28 | 28 | Pass |
| No City | Governorate + status | 19 | 19 | 19 | 19 | Pass |

Machine-readable row counts are in [export-count-parity.json](ui-evidence/export-count-parity.json).

### Five viewport results

Dashboard and Opportunities controls were exercised in RTL at all required sizes. Both views were checked at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. The national map was rendered and captured at 1920×1080 and 390×844 for each fixture.

The deterministic Playwright matrix stubs OSM tiles while checking map geometry, markers, clusters, filters, popups, and details. A separate isolated browser check against the live tile endpoint loaded **12/12 map tile images** and rendered the basemap with the synthetic marker cluster; its screenshot is [city-reference-map-live-tiles-1920x1080.png](ui-evidence/city-reference-map-live-tiles-1920x1080.png).

| Viewport | Result | Notes |
|---|---|---|
| 1920×1080 | Passed | RTL, no horizontal overflow, controls visible, labels do not overlap |
| 1440×900 | Passed | RTL, no horizontal overflow, controls visible, labels do not overlap |
| 1366×768 | Passed | RTL, no horizontal overflow, controls visible, labels do not overlap |
| 768×900 | Passed | RTL, no horizontal overflow, controls visible, labels do not overlap |
| 390×844 | Passed | RTL, no horizontal overflow, controls visible, labels do not overlap |

Screenshots for the City-present and City-absent runs are stored in `ui-evidence/`, including dashboard, Opportunities, and map captures at the sizes above where listed. Example captures:

- [City dashboard, 1920×1080](ui-evidence/city-reference-dashboard-1920x1080.png)
- [City dashboard, 1366×768](ui-evidence/city-reference-dashboard-1366x768.png)
- [City dashboard, 390×844](ui-evidence/city-reference-dashboard-390x844.png)
- [City Opportunities, 1920×1080](ui-evidence/city-reference-opportunities-1920x1080.png)
- [City Opportunities, 1440×900](ui-evidence/city-reference-opportunities-1440x900.png)
- [City Opportunities, 1366×768](ui-evidence/city-reference-opportunities-1366x768.png)
- [City Opportunities, 768×900](ui-evidence/city-reference-opportunities-768x900.png)
- [City Opportunities, 390×844](ui-evidence/city-reference-opportunities-390x844.png)
- [City national map, 1920×1080](ui-evidence/city-reference-map-1920x1080.png)
- [City national map, 390×844](ui-evidence/city-reference-map-390x844.png)
- [No-City dashboard, 390×844](ui-evidence/no-city-reference-dashboard-390x844.png)
- [No-City Opportunities, 390×844](ui-evidence/no-city-reference-opportunities-390x844.png)
- [No-City national map, 1920×1080](ui-evidence/no-city-reference-map-1920x1080.png)

Complete check details are in [browser-results.json](ui-evidence/browser-results.json).

## Changes needed to complete validation

Browser validation found and the workspace implementation corrected these defects:

1. City options were empty because the selector initializer checked the City control's disabled state before enabling it. The dependent selector now enables City when the reference has that level and a Governorate is selected.
2. Table reset now resets geographic filters and sorting. Sortable columns preserve filter state in the URL/API query.
3. The geographic dashboard summary had a request-argument mismatch that returned HTTP 500; it now passes the period separately.
4. National map title/accessibility text and attribution reflect national scope; the national dashboard exposes non-additive Region/Governorate drilldown and separate nationwide/unspecified counts.

The final regression suite was run once after the workspace code changes: **620 passed, 40 existing deprecation warnings, 71.54 seconds**. Post-change focused geography/safety tests had **24 passed**. The project folder does not have Git metadata, so these changes could not be reported as a Git diff.

## Production read-only verification

The post-validation snapshot used explicit read-only DB transactions. Production remained on `0023_quant_commercial`; migrations 0024 and 0025 and all geographic reference/coverage tables were absent. `NATIONAL_UI_ENABLED`, `NATIONAL_MAP_ENABLED`, `NATIONAL_DASHBOARD_ENABLED`, and `FURAS_NATIONAL_ENUMERATION_ENABLED` were all false. The production UI entrypoint returned HTTP 200 with the existing RTL title `رصد | فرص الأحساء الاستثمارية`; its unauthenticated page had no national Region selector. `/api/geography/catalog` returned 404, while the existing geography dashboard route still served the legacy local Al-Ahsa map (566 Masters in scope, 435 exact mapped, 433 point groups). No `TEST_*` Master marker was found in production.

The source scheduler was already active independently of this task: scheduled Jobs 668 and 669 completed during the review. The task initiated zero manual syncs, backfills, promotions, or production writes; those independently scheduled jobs are reported separately in the readiness and Furas reports.

## Final status

```text
ISOLATED_NATIONAL_UI_ENVIRONMENT = PASSED
NATIONAL_OPPORTUNITIES_BROWSER = PASSED
REGION_FILTER_BROWSER = PASSED
GOVERNORATE_FILTER_BROWSER = PASSED
CITY_FILTER_BROWSER = PASSED
REGION_GOVERNORATE_WITHOUT_CITY_BROWSER_TEST = PASSED
ALAHSA_QUICK_VIEW_BROWSER_TEST = PASSED
NATIONAL_DASHBOARD_BROWSER = PASSED
NATIONAL_MAP_BROWSER = PASSED
FILTER_API_EXPORT_BROWSER_PARITY = PASSED
PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
RTL = PASSED
NO_HORIZONTAL_OVERFLOW = TRUE
NO_TEXT_OVERLAP = TRUE
JAVASCRIPT_ERRORS = 0
UNEXPECTED_HTTP_5XX = 0
FAKE_COORDINATES_CREATED = 0
TEST_FIXTURE_IN_PRODUCTION = 0
GEOGRAPHIC_REFERENCE_READY = FALSE
PRODUCTION_ALEMBIC_HEAD = 0023
MIGRATION_0024_PRODUCTION_APPLIED = FALSE
MIGRATION_0025_PRODUCTION_APPLIED = FALSE
NATIONAL_UI_ENABLED_PRODUCTION = FALSE
NATIONAL_MAP_ENABLED_PRODUCTION = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
INVEST_SAUDI_PROMOTIONS = 0
MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
BUSINESS_DATA_CHANGES_BY_THIS_TASK = 0
REVIEW_DATA_CHANGES_BY_THIS_TASK = 0
PRODUCTION_SCHEMA_CHANGES = 0
```

`GEOGRAPHIC_REFERENCE_READY=false` remains the external production blocker. Technical isolated readiness is complete; production expansion is still disabled and not accepted or closed.
