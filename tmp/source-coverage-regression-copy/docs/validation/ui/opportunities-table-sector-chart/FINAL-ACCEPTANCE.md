# Opportunities table and sector chart acceptance

**Validation timestamp:** `2026-10-19T10:19:11.317Z` (UTC)  
**Result:** `OPPORTUNITIES_TABLE_COLUMN_ALIGNMENT = PASSED`; `SECTOR_CHART_OTHER_AGGREGATION = PASSED`

## Opportunities table

The live page was checked before modification. Its header and every row already had 11 cells, including Activity, Sub-Activity, Asset/Facility Type, and a separate details action. The reported eight-column displacement was not present in the current served page. To make the mapping explicit and guard against a missing or reordered cell, each header and body cell now carries the same semantic `data-column` key. The details header has an accessible name, its action cell has a fixed minimum width, and the button is explicitly keyboard activatable.

At all five viewports, Playwright checked the first 50 rows against the live API fields and asserted exact header/cell key order and count. Activity is read from the Master `activity` field, area from `area`, deadline from `deadline`, status from the current status value, and source count from linked sources. The details button remains in the independent `action` cell.

| Viewport | RTL | Header / row cells | API field alignment | Page overflow | Table scroll |
|---|---|---:|---|---|---|
| 1920×1080 | Pass | 11 / 11 | Pass | None | No |
| 1440×900 | Pass | 11 / 11 | Pass | None | No |
| 1366×768 | Pass | 11 / 11 | Pass | None | No |
| 768×900 | Pass | 11 / 11 | Pass | None | Internal table only |
| 390×844 | Pass | 11 / 11 | Pass | None | Internal table only |

Browser flow checks passed: reference search `44826` returned one Master; the Industrial sector filter returned 59; reset returned 291; next/previous pagination worked; and keyboard Enter on the details action opened the opportunity details dialog. CSV/XLSX endpoints and the grouped sector export filter are covered by the focused API tests.

## Dashboard sector chart

`/api/data-dashboard` continues to return all canonical sector buckets unchanged. The presentation layer keeps the seven leading buckets and adds the current tail count to the canonical `أخرى` display bar. For this snapshot:

| Value | Count |
|---|---:|
| Canonical `أخرى` | 17 |
| Current tail group (`الزراعة`, `السياحة`) | 2 |
| Displayed `أخرى` | 19 |
| Displayed chart total | 291 |
| Eligible Masters | 291 |

`بقية القطاعات` is not rendered as a separate bar. The `أخرى` bar carries the member canonical IDs (`sector:other`, `sector:agriculture`, `sector:tourism`). Its click opens the opportunity list with the explicit member set; the list and CSV/XLSX endpoints apply a read-only OR filter over those canonical values. The live click returned 19 Masters. Live CSV and XLSX exports each returned 19 data rows, and the XLSX report metadata names the included canonical labels. Reset restored all 291. No database sector value or taxonomy mapping was rewritten.

The aggregate is calculated from the current API result each render, including active dashboard filters; `19` is not hardcoded. The dashboard SVG still reconciles its displayed bucket sum to the filtered eligible Master total.

## Regression and data safety

- Focused dashboard/API suite: **3 passed**.
- Full regression suite: **143 passed, 0 failed** (one existing Starlette/httpx deprecation warning).
- Closed taxonomy regression subset (Activity, Asset/Facility Type, Investment Model, Location, canonical filter behavior, and standardization): **27 passed, 0 failed**. Sector and Opportunity Type canonicalization are included in the full suite.
- Application readiness after deployment: API, database, Redis, and worker healthy. Existing scheduler remained running. No manual source sync was started.
- Pre/post fingerprints match for all 291 eligible Masters, 2,898 source links, 7,603 source observations, Master identities, source links, raw source payloads, and raw observation payloads. See [pre-deploy fingerprint](pre-deploy-data-fingerprint.json) and [post-deploy fingerprint](post-deploy-data-fingerprint.json).
- No database migration, business-data update, Master recreation, taxonomy edit, source-link edit, or raw-payload edit was made.

## Screenshots and machine results

- [1920×1080 Opportunities table](screenshots/opportunities-alignment-1920x1080.png)
- [768×900 Opportunities table](screenshots/opportunities-alignment-768x900.png)
- [Dashboard with aggregated `أخرى`](screenshots/dashboard-sector-other-1920x1080.png)
- [19-result list after clicking aggregated `أخرى`](screenshots/dashboard-sector-other-drilldown-1920x1080.png)
- [Playwright machine summary](screenshots/qa-summary.json)

```ini
TABLE_HEADER_COUNT = 11
TABLE_BODY_CELL_COUNT = 11
ACTION_COLUMN_SEPARATE = TRUE
CANONICAL_OTHER_COUNT = 17
TAIL_SECTOR_GROUP_COUNT = 2
DISPLAYED_OTHER_COUNT = 19
OTHER_CLICK_RESULT_COUNT = 19
DASHBOARD_SECTOR_TOTAL = 291
SNAPSHOT_ELIGIBLE_MASTERS = 291
BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
```
