# AHDA Dashboard Visual Analytics Validation

**Status:** `NEXTADMIN_AHDA_VISUAL_ANALYTICS_COMPLETE`  
**Validated:** 2026-10-14  
**Dashboard:** `http://localhost:8080/?view=data-dashboard`

## A. Before and after

Before this extension, the dashboard used CSS/HTML bar rows, a CSS timeline, KPI cards, deadline lists, and review/source summaries. It had no chart or mapping library, no interactive administrative map, and no geographic heat layer. The API already provided SQL-based canonical summaries and shared dashboard filters.

The actual NextAdmin reference was inspected: its home map uses a Leaflet `MapContainer` with GeoJSON boundaries, custom controls, and popups; its analytics cards use Recharts with gridlines, tooltips, and responsive sizing. This implementation follows that interaction/card treatment while keeping the project's existing FastAPI plus static-JavaScript architecture, using native SVG charts and local Leaflet assets instead of converting the app to React. [NextAdmin reference](https://github.com/NextAdminHQ/nextjs-admin-dashboard).

The existing AHDA layout, navigation, KPI cards, RTL, Ahda Text, filters, exports, authentication, source-health, and review panels remain in place. The existing bar/timeline renderers are upgraded to interactive native SVG visualizations; a Leaflet map and a current-data preview table are added. No opportunity or source rows were edited, no migration was added, and no new npm dependency was introduced.

## B. Charts and interactions

The chart values are calculated by `/api/data-dashboard` from the same filtered set of non-merged Master Opportunities. The API now applies lifecycle filters to the dashboard, retains all canonical sector/type/activity groups, returns the top 10 owners, returns all enabled sources (including zero-count sources), and reports source share as unique Master Opportunities divided by the filtered total.

| Component | Dimension and visualization | Interaction |
|---|---|---|
| `dashBySector` | Canonical sector; ranked horizontal SVG bars | Click or press Enter/Space to open the opportunity list with the canonical sector filter. Tooltip gives Arabic label, count, and share of filtered results. |
| `dashByStatus` | Canonical business status; ranked horizontal SVG bars | Click or keyboard activation applies the canonical status. `DELETED_FROM_SOURCE` remains distinct from `CANCELLED`. |
| `dashByType` | Canonical opportunity type; ranked horizontal SVG bars | Click applies the canonical type. The data is not forced into a donut because the live type cardinality is too high for a legible one. Alias values such as `أخرى` and `اخرى` are grouped by the existing canonicalization layer. |
| `dashBySource` | Ten enabled official sources; ranked horizontal SVG bars; count is unique Masters per source | Click applies the source key. Each tooltip defines the count and filtered-total share; source shares can sum above 100% because a Master may be linked to multiple sources. |
| `dashByOwner` | Canonical owner/entity; top 10 horizontal SVG bars | Click applies the canonical owner. Publication platform is not used as owner. |
| `dashByLocation` | Canonical published city/location; horizontal SVG bars | Click applies the canonical location. This is a published text dimension, not a map coordinate. |
| `dashTimeline` | First-seen month; SVG line chart | Click/keyboard activation filters `created_after` and `created_before` to that month. |
| `dashDeadlineTrend` | Valid upcoming deadline month; SVG line chart | Click/keyboard activation filters the list to that calendar month and the active lifecycle. Invalid dates are ignored. |
| Activity state | No chart while every activity value is missing | Compact Arabic coverage state: `لا تتوفر بيانات نشاط فرعي مصنفة حاليًا`. It will be replaced by the chart when classified data exists. |

Tooltips are Arabic and include counts and shares; SVG marks expose keyboard focus, labels, and titles. The current filtered API totals match across sectors, statuses, and types. A filtered lifecycle option was added to the global dashboard controls.

The dashboard also shows eight recently updated opportunities from the same filtered API result in a compact, detail-linked table. The existing full opportunity list remains the detailed searchable and paginated view.

## C. Geography and precision

- **Map component:** `dashboard-visual-analytics.js`, powered by locally vendored Leaflet 1.9.4, Leaflet.markercluster 1.5.3, and Leaflet.heat 0.2.0. Their upstream licenses are preserved under `app/static/vendor/`.
- **Boundary:** local `app/static/geo/alahsa-governorate.geojson`, the geoBoundaries gbOpen SAU ADM2 `Al Ahsa Governorate` feature (2021; OpenStreetMap-derived; CC BY-SA 2.0 as identified by the pinned feature metadata). It is a sourced administrative reference boundary, not an official cadastral/planning boundary. GEOSA identifies its Official Saudi Map as the approved national reference, but the public layer inspected for this work did not state a reuse license, so it was not republished. [GEOSA Official Saudi Map](https://www.geosa.gov.sa/en/About/Pages/OfficialSaudiMap.aspx) · [geoBoundaries API and boundary metadata](https://www.geoboundaries.org/api.html).
- **Coordinates:** 176 Masters currently have coordinate pairs. All 176 exactly match a linked Furas source row's original ArcGIS `geometry.x/y` within `1e-8` decimal degrees and are valid WGS84 ranges. The point is drawn only after point-in-polygon containment in the bundled local boundary.
- **Represented:** 175 exact source-coordinate opportunities. One Salwa record falls outside the boundary and remains excluded from the map without changing its opportunity record.
- **Locality-level aggregation:** 0. No locality centroid was introduced. The application has city/district/location text but no municipality column or controlled locality-centroid reference. Text alone is not converted into coordinates.
- **Not geographically mappable:** 114 total = 113 with no coordinate pair + 1 coordinate pair outside the boundary. Unverified coordinate count is 0. The API reports total, coordinate-bearing, exact mapped, locality mapped, missing, outside, unverified, and unmapped counts separately.
- **Display precision:** WGS84 source coordinates are validated against their raw source geometry; records at the same coordinate rounded to seven decimal places are grouped for marker display. Decimal representation is not a claim about source survey accuracy.

The map begins fitted to the Al-Ahsa polygon, uses clusters in point mode, and displays point popups with location, opportunity count, active count, and sector. The popup's `عرض الفرص في القائمة` action passes Master IDs through `map_ids`; filters and exports preserve those IDs. A weak locality string or coordinates from another source cannot create a map point.

The map boundary asset and opportunity map API response are local. Basemap tiles use the public OpenStreetMap tile service at runtime with visible attribution and ordinary browser caching. The app requests only the current viewport and has no offline tile prefetch; if tiles fail, the boundary and analytical layers remain and the map displays a notice. [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/).

The static map libraries and licenses are documented in [the local geo assets README](../../../../app/static/geo/README.md): Leaflet BSD-2-Clause, MarkerCluster MIT, and Leaflet.heat BSD-2-Clause. [Leaflet license](https://github.com/Leaflet/Leaflet/blob/v1.9.4/LICENSE) · [MarkerCluster license](https://github.com/Leaflet/Leaflet.markercluster/tree/v1.5.3) · [Leaflet.heat license](https://github.com/Leaflet/Leaflet.heat).

## D. Heat map

The heat layer is Leaflet.heat over the same verified exact points returned by `/api/data-dashboard/geography`. Every opportunity contributes weight 1; records that share an exact display coordinate are grouped and their opportunity count becomes the point weight. The current mapped weight therefore sums to 175. No locality-level weights are present.

The points/heat mode switch shares the full dashboard filter set, including lifecycle. The API filters in SQL before returning the compact map payload; the browser does not download the full opportunity list and aggregate it. Heat and point modes represent the same filtered opportunity population. Marker clusters show aggregated opportunity counts, and marker popups drill down to the selected Master IDs.

## E. Validation

### API and data consistency

- Current dashboard API total: **289** Masters; enabled sources: **10**; source chart rows: **10**; recent table rows: **8**.
- Sector, status, and type aggregate totals each equal **289**; the API/UI total comparison passed.
- Geographic API: **175 exact mapped**, **0 locality mapped**, **113 missing coordinates**, **1 outside boundary**, **0 unverified coordinates**, **114 unmapped**.
- Filter synchronization passed: selecting a sector updated dashboard KPI/chart data and map summary to the same filtered total.
- Chart drill-down by keyboard, deadline-month drill-down, map ID list drill-down, and map ID CSV export passed. Canonical alias aggregation and the distinct removed/cancelled status are covered by the existing canonicalization test suite.
- Full project tests: **122 passed**, one existing Starlette/httpx deprecation warning.
- Live service checks: readiness HTTP 200; dashboard and geography API returned the values above; source endpoint returned 10 sources; CSV HTTP 200 with 289 data rows plus header; XLSX HTTP 200 (212,103 bytes); Alembic `0017_data_standardization (head)`.
- PostgreSQL, Redis, API, frontend, worker, and scheduler were running after deployment. The scheduler was left enabled. `Restart Platform.bat` stopped and restarted the stack successfully while preserving the local database.

### Browser and responsive QA

Playwright checks against the running dashboard verified all five required viewport sizes, no page-level horizontal overflow, all chart SVGs, the intentionally compact activity empty state, marker clustering, heat toggle, filtered chart/map parity, keyboard drill-down, monthly deadline drill-down, map-ID filtering, API/UI count parity, and a forced tile-request failure. Under the forced tile failure, the Arabic notice appeared and local boundary and opportunity layers stayed visible. There were no unexpected JavaScript errors or failed same-origin API requests. Four guest-session HTTP 401 console messages were recorded for unauthenticated session probes; they did not affect public dashboard data or the map.

| Viewport | Result | Map dimensions |
|---|---|---:|
| 1920×1080 | Pass; no horizontal overflow | 1470×440 |
| 1440×900 | Pass; no horizontal overflow | 1052×440 |
| 1366×768 | Pass; no horizontal overflow | 982×440 |
| 768×900 | Pass; no horizontal overflow | 680×400 |
| 390×844 | Pass; no horizontal overflow | 340×360 |

Evidence: [1920×1080](visual-analytics/screenshots/dashboard-1920x1080.png), [1440×900](visual-analytics/screenshots/dashboard-1440x900.png), [1366×768](visual-analytics/screenshots/dashboard-1366x768.png), [768×900](visual-analytics/screenshots/dashboard-768x900.png), [390×844](visual-analytics/screenshots/dashboard-390x844.png), [heat map at 1440×900](visual-analytics/screenshots/map-heat-1440x900.png), and [machine-readable QA summary](visual-analytics/screenshots/qa-summary.json).

The heat-map evidence capture shows the OSM basemap loaded. The local boundary and opportunity overlays remain available independently of tile-service availability.

## Files changed

- `app/main.py` — lifecycle-scoped dashboard aggregates, deadline-month ranges, all enabled source counts/share, recent filtered opportunities, exact geography endpoint, and map ID filters for opportunity list and exports.
- `app/static/index.html`, `app/static/app.js`, `app/static/styles.css` — lifecycle control, map, chart slots, recent opportunities table, and AHDA responsive treatment.
- `app/static/dashboard-visual-analytics.js` — native SVG charts and Leaflet map/heat/cluster behavior.
- `app/static/vendor/` — pinned local map libraries and license texts.
- `app/static/geo/` — local boundary asset and provenance.
- `tests/test_data_dashboard.py` — trend date boundaries, shares, source-exact geography, boundary exclusion, mismatch exclusion, filters, map list drill-down, and export scope.
- `tmp/visual-analytics-qa.cjs` and `docs/validation/ui/nextadmin-ahda-dashboard/visual-analytics/screenshots/` — browser QA harness and screenshots.

## Completion gate

`NEXTADMIN_AHDA_VISUAL_ANALYTICS_COMPLETE`
