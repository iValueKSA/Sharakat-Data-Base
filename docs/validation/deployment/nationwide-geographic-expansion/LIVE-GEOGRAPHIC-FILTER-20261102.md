# Live geographic filter — 2026-11-02

**Status: COMPLETE** for the Opportunities list in `alahsa-local` at `http://localhost:8080`.

## Implementation and deployment

- Added the Arabic filter label **المنطقة** to the existing Opportunities screen. One native dropdown groups canonical Regions under **المناطق** and Governorates under **المحافظات**.
- Options come from the current geographic reference and show unique current-Master counts. The UI includes all 13 Regions and the 79 Governorates that currently have opportunity coverage; zero-coverage Governorates remain in the API payload but are omitted from the UI.
- Selecting a Region sends `region_id`; selecting a Governorate sends `governorate_id` only. Values are canonical reference IDs, never text search. Al-Ahsa’s label uses its Arabic reference alias **الأحساء**; its source name is **الاحساء**, and its canonical level/ID remain Governorate `501`.
- Existing list filters, pagination, URL state, reset, and CSV/XLSX links remain in place. The all-regions default adds no geographic query parameter or active-filter chip.
- Rebuilt and deployed only the API and frontend services in Compose project `alahsa-local`. No migration ran. The nationwide dashboard and map feature flags remain disabled.

## Live acceptance results

| Check | Result |
|---|---:|
| All-regions current Master baseline | 6,623 |
| Region options with coverage | 13 |
| Governorate options with coverage | 79 |
| Al-Ahsa, Governorate `501` | 518 UI / API / canonical option count |
| Al-Ahsa false positives / false negatives | 0 / 0 |
| Riyadh, Region `1` (`منطقة الرياض`) | 800 UI / API |
| Governorate + status composition | 60 UI / API |
| Pagination | Passed; page 1 and page 2 each returned 50 distinct Master IDs, with no overlap |
| Reset | Passed; restored all-regions result of 6,623 and cleared the geography URL state |
| Al-Ahsa CSV / XLSX | 518 / 518 rows; matches UI and API |
| Riyadh Region CSV / XLSX | 800 / 800 rows; matches UI and API |
| Responsive RTL | Passed at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844 |
| Horizontal overflow | 0 at all five viewports |
| JavaScript errors / unexpected HTTP 5xx | 0 / 0 |

Al-Ahsa results were checked through `geography.reference_unit.level == "governorate"` and `geography.reference_unit.external_id == "501"` for every returned Master. API pages 1 and 2 covered all 518 results. The API count also matched the data-driven canonical option count.

## Validation and limitations

- Regression: `tests/test_nationwide_expansion_safety.py` and `tests/test_location_geography.py` — **49 passed, 1 skipped**. JavaScript syntax checks passed for the app, geography module, and browser helper.
- Live browser: **28 checks passed** on the deployed `localhost:8080` frontend with live list/geography/export endpoints. CSV and XLSX downloads were parsed and row-count parity passed for Al-Ahsa and Riyadh.
- The final browser harness stubbed only `/api/auth/me` with a local test identity because saved local-admin credentials were rejected. The earlier rejected sign-in attempts may have updated routine failed-login tracking; no account or password settings were changed. All geography, opportunity, count, and export responses came from the live API. The interactive sign-in flow was not validated in this run.
- No source sync, backfill, promotion, review resolution, opportunity/Master edit, geography reassignment, status/lifecycle edit, removal action, or schema change was performed by this task.

## Evidence

- [Browser results](live-geographic-filter-evidence/browser-results.json)
- [Export row-count parity](live-geographic-filter-evidence/export-count-parity.json)
- [Al-Ahsa CSV](live-geographic-filter-evidence/live-export-alahsa.csv) · [Al-Ahsa XLSX](live-geographic-filter-evidence/live-export-alahsa.xlsx)
- [Riyadh CSV](live-geographic-filter-evidence/live-export-riyadh-region1.csv) · [Riyadh XLSX](live-geographic-filter-evidence/live-export-riyadh-region1.xlsx)
- Viewport captures: [1920×1080](live-geographic-filter-evidence/opportunities-1920x1080.png), [1440×900](live-geographic-filter-evidence/opportunities-1440x900.png), [1366×768](live-geographic-filter-evidence/opportunities-1366x768.png), [768×900](live-geographic-filter-evidence/opportunities-768x900.png), [390×844](live-geographic-filter-evidence/opportunities-390x844.png)

```text
LIVE_GEOGRAPHIC_FILTER = COMPLETE
FILTER_LABEL = المنطقة
ALL_REGIONS_OPTION = TRUE
REGION_OPTIONS_COUNT = 13
GOVERNORATE_OPTIONS_COUNT = 79
ALAHSA_OPTION_AVAILABLE = TRUE
ALAHSA_CANONICAL_GOVERNORATE_ID = 501
ALAHSA_RESULT_COUNT = 518
ALAHSA_FALSE_POSITIVES = 0
ALAHSA_FALSE_NEGATIVES = 0
ALAHSA_UI_FILTER = PASSED
RIYADH_OPTION_AVAILABLE = TRUE
RIYADH_FILTER_LEVEL = REGION
RIYADH_FILTER_ID = 1
RIYADH_RESULT_COUNT = 800
FILTER_COMPOSITION = PASSED
PAGINATION = PASSED
RESET = PASSED
API_UI_PARITY = PASSED
CSV_PARITY = PASSED
XLSX_PARITY = PASSED
RESPONSIVE_VIEWPORTS = PASSED
RTL = PASSED
HORIZONTAL_OVERFLOW = 0
JS_ERRORS = 0
UNEXPECTED_5XX = 0
BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNCS = 0
SCHEMA_CHANGES = 0
NATIONAL_MAP_ENABLED = FALSE
NATIONAL_DASHBOARD_ENABLED = FALSE
```
