# Live National UI / Map Activation — 2026-11-03

## Decision

**No live flags were changed.** National UI activation is blocked; map activation is independently blocked. Acceptance gates require an authenticated live browser run across dashboard and opportunities controls, UI/API/CSV/XLSX parity, responsive national controls, and map drilldown. The configured bootstrap account was rejected by the real login endpoint, and Al-Ahsa filter results include 84 records whose display geography is unresolved. RCU lifecycle/deadline semantics also remain open for review.

## Pre-activation evidence

- Live target: `http://localhost:8080/`; health endpoint ready (database, Redis, worker).
- Live configuration before and after preview: `NATIONAL_UI_ENABLED=false`, `NATIONAL_DASHBOARD_ENABLED=false`, `NATIONAL_MAP_ENABLED=false`; Furas enumeration/removals remain false.
- Read-only national feature preview was executed in an isolated `TestClient` process with temporary per-process feature flags and the existing live database. The live container configuration was not changed. Reference catalog returned READY with selector levels Region/Governorate. Geography summary total and dashboard/list filter totals matched.
- API/CSV/XLSX parity was checked for All Saudi (6,657 rows), five geographic scopes (East, Riyadh, Makkah, Al-Madinah, Al-Ahsa), and NCP, RCJY, RCU, RCU→Al Ula, Ta’adeen. API and CSV/XLSX counts matched. All Saudi XLSX generation took 153 seconds. The Ta’adeen workbook contains the standard empty-state message and no data rows.
- Dashboard/list parity passed for all Saudi (6,657), East (975), Riyadh (800), Makkah (319), Al-Madinah (458), and Al-Ahsa (518).
- National map API preview returned 5,889 unique verified-coordinate Masters, no outside-boundary points, and no broad/unspecified markers. Coordinates were not generated from centroids. The map’s browser presentation and drilldown were not run.

## Browser evidence and limits

Playwright explicitly navigated to the live target at the five requested viewports. The unauthenticated shell was RTL with no horizontal overflow; 0 runtime page exceptions, 0 failed resources, 0 unexpected 5xx, and five expected 401 responses from `/api/auth/me`. Screenshots:

- [1920×1080 live shell](/C:/Sharakat%20Data%20Base/tmp/national-acceptance-1920.png)
- [390×844 live shell](/C:/Sharakat%20Data%20Base/tmp/national-acceptance-390.png)

A normal sign-in attempt using the configured bootstrap credentials was rejected. No alternate or invented credentials were tried. `AUTH_FLOW_VALIDATED=FALSE`. National filters, charts, map interactions, dropdown layout, and responsive behavior remain unverified in the authenticated UI. All Saudi API/CSV/XLSX parity is certified. UI parity remains unverified.

## Al-Ahsa and RCU acceptance risks

The official governorate 501 filter returns 518 records. Of these, 434 display a confirmed Al-Ahsa identity; 84 have `LOCATION_UNSPECIFIED` display geography with no governorate identity even though reference/source membership selects them. This needs reconciliation before asserting zero false positives/negatives or enabling the UI.

Six RCU status conflicts preserve raw `CURRENT` (`isClosed=false`) while canonical status is `حالة غير معروفة`; the lifecycle parser flags the raw status ambiguous. Six deadline conflicts store the exact RCU ISO datetime in the Master, but it has no timezone offset, so the parser flags `INVALID_DEADLINE`; each conflict row also has the unrelated `selected_value=حالة غير معروفة`. No other source value exists for these six Masters. All 12 remain open; none was resolved or edited. The lifecycle and deadline semantics must be reviewed before promotion.

## Activation gate result

| Gate | Result | Evidence |
|---|---|---|
| DQ failures = 0 | PASS | 127 PASS / 7 WARNING / 0 FAIL |
| Regression failures = 0 | PASS | 687 passed / 1 skipped / 0 failed |
| Master reconciliation | PASS | 6,678 = 6,657 + 21 |
| Region / Governorate API filtering | PASS | 13 / 149, parent scoping confirmed |
| Dashboard/list API parity | PASS | Six representative scopes |
| API/CSV/XLSX parity | PASS (export side) | All Saudi and representative geographic/source exports match; live UI parity is blocked |
| Al-Ahsa FP/FN = 0 | BLOCKED | 84 selected records display unresolved geography |
| Authenticated Playwright / responsive national UI | BLOCKED | Configured bootstrap login rejected |
| Verified-coordinate map API policy | PASS | 5,889 unique exact markers; 0 outside boundary |
| Map browser / list drilldown | BLOCKED | Authentication unavailable |
| RCU lifecycle/deadline integrity | BLOCKED | 12 unresolved, including parser ambiguity and malformed conflict metadata |

**Result:** `NATIONAL_UI_ENABLED=false`; `NATIONAL_DASHBOARD_ENABLED=false`; `NATIONAL_MAP_ENABLED=false`. No service restart or deployment was performed. The temporary preview flags were process-local and discarded at process exit. No manual source sync, migration, business-data modification, link change, or review resolution was performed. A scheduled source job ran naturally during the acceptance window; it was not initiated by this task.

