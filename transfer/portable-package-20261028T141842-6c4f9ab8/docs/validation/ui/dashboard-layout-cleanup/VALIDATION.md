# Dashboard layout cleanup validation

**Result:** `DASHBOARD_LAYOUT_CLEANUP_COMPLETE`  
**Validated:** 2026-10-19 11:21 UTC  
**Page:** `http://localhost:8080/?view=data-dashboard`

## Changes

Removed the standalone total-opportunities card, owner-completion card, mapped-site percentage card, classified investment-model card, review card, standalone technical-source-health card, unmapped-location card, seven-day deadline card, opportunity-types chart, and additions-over-time chart. The total remains in the overview hero, while source-health context remains inside the enabled-sources card.

The existing upcoming-deadlines card now shares the distribution row with status and sources. Existing Arabic labels, RTL direction, AHDA styling, map behavior, and dashboard API semantics were retained. No backend, API, filter implementation, business-data, or dashboard data semantics were changed.

## Browser verification

Playwright verified the page at `1920×1080`, `1440×900`, `1366×768`, `768×900`, and `390×844`. At every width, the document and body widths matched the viewport, dashboard grid children stayed within their sections, and the map, sector chart, source card, status card, and upcoming-deadlines card remained visible. The RTL direction was retained.

Interactions passed: dashboard status filter and reset, sector chart drilldown, map heat/clusters mode switch, and map-marker drilldown. The browser reported no page errors. A follow-up browser check loaded six OpenStreetMap tiles at 256×256 each.

Full regression: **154 passed, 0 failed** (`pytest -q`; one existing Starlette/httpx deprecation warning). Tests ran against an in-memory SQLite database.

## Local data and service safety

The local database remained available. Post-check counts were 296 Masters, 291 non-merged Masters, 2,898 source links, and 10,514 observations. The current Alembic revision remained `0022_status_lifecycle (head)`. Local bootstrap reported `ALREADY_IMPORTED`; no manual source sync was started. The dashboard changes are limited to frontend presentation and do not alter business data.

## Evidence

- `playwright-dashboard-layout.json` — viewport measurements, removed/retained component assertions, and interaction results.
- `dashboard-1920x1080-full.png` — desktop full-page capture.
- `dashboard-1440x900-medium.png` — medium desktop capture.
- `dashboard-768x900-tablet.png` — tablet capture.
- `dashboard-390x844-mobile.png` — mobile capture.
- `dashboard-lower-status-sources-deadlines.png` — retained lower dashboard cards.
