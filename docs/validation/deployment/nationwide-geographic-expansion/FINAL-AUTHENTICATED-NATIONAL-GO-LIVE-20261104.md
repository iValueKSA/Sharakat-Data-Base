# Final Authenticated National Go-Live — 2026-11-04

## Decision

**FINAL_NATIONAL_GO_LIVE = PARTIAL. No live activation was performed.** The national UI, dashboard, and map remain disabled. Authenticated isolated-preview checks passed for several core controls, but the Playwright runtime reset before responsive and map-drilldown acceptance finished. More critically, live RCU records changed during the acceptance window: ambiguous deadlines reappeared in four Masters and five RCU conflicts moved to `RESOLVED_SOURCE`. No business-data correction or manual source sync was performed by this acceptance run.

## Authentication

- The authorized administrator signed in through the normal login screen in the first visible Playwright context. `/api/auth/me` returned 200 and the `admin` role; no credentials, cookies, or tokens were captured or printed.
- A later long browser operation reset the Playwright runtime and its temporary context. A fresh visible context then returned 401. The user was asked to sign in again, but no completion was received before the acceptance was closed.
- **AUTHENTICATED_LOGIN = PASSED once. AUTHENTICATED_BROWSER_VALIDATION = PARTIAL.** No auth stub or bypass was used.

## Isolated national UI preview

The preview API ran on a temporary local port with national flags enabled only in that process, `--lifespan off`, and GET-only Playwright routing to current database-backed application endpoints. The live feature flags were never changed. The preview was stopped afterward.

- National list and dashboard totals: **6,657** each.
- Region selector: **13** regions. Region → governorate cascade worked; Eastern Province returned **975**, Riyadh **800**, Makkah **319**, and Al-Madinah **458**. Al-Ahsa Governorate returned **518**; the evidenced Hofuf locality filter returned **3**.
- Source filters: RCJY **3**, RCU **6**, NCP **26** Masters using one NCP option/identity, Ta'adeen **0** current Masters.
- Status `متاحة` and sector filters updated the list and matched API totals. Search returned **35** for the selected query. Pagination reached page 2 with 50 distinct IDs; reset returned to the first page after the UI settled.
- Dashboard region filter updated its total and chart. The national map loaded, and the Eastern Province filter propagated to a map total of **975** with five rendered markers.
- Al-Ahsa API/dashboard/CSV/XLSX parity remains **518 / 518 / 518 / 518** from the post-deploy preview. No current signed-in browser export download was completed.

Desktop preview captures: [national opportunities](ui-evidence/national-opportunities-preview-1920x1080.png), [national dashboard and map](ui-evidence/national-dashboard-preview-1920x1080.png). These were captured before the RCU drift described below and are not evidence of final responsive or drilldown acceptance.

## RCU drift observed during acceptance

At the initial post-remediation check, all six RCU canonical statuses were unknown and all six canonical deadlines were null. During the acceptance window, live change history showed four offset-free deadlines restored to Masters 6678, 6679, 6681, and 6682 at approximately 07:27–07:28 UTC. The corresponding four deadline conflicts changed to `RESOLVED_SOURCE`; the current source-job table showed no RCU job explaining those changes. No write, review resolution, or source sync was initiated by this task.

At the latest read-only snapshot, RCU had six Masters with conservative status `حالة غير معروفة`, four non-null ambiguous Master deadlines, two null deadlines, five open status conflicts, two open deadline conflicts, and five conflicts marked `RESOLVED_SOURCE`. This disagrees with the earlier accepted report of 12 open conflicts and zero incorrect deadlines. Because the current business state changed without an attributable acceptance action, national activation is blocked pending an authorized review of that drift. No attempt was made to restore or alter these rows.

## Map evidence and remaining browser gates

- Recomputed verified-coordinate population before the observed RCU drift: **5,889** unique Masters; outside-boundary markers: **0**. The Eastern Province filtered map rendered five markers.
- Marker-to-details and map-to-list drilldown: **NOT TESTED**.
- Authenticated responsive viewports 1920×1080, 1440×900, 1366×768, 768×900, and 390×844: **NOT COMPLETED**.
- Authenticated unexpected JavaScript errors and unexpected 5xx totals: **NOT VALIDATED**.
- Dashboard/list and API/export parity: Al-Ahsa and listed region/source filters passed in the isolated preview; full authenticated UI/CSV/XLSX parity was not completed.

## DQ, regression, and live flags

- Regression from the accepted deployed code: **688 passed, 1 skipped, 0 failed**. No code change was made during this acceptance turn.
- Final read-only full DQ run `007d279182ff477e8532d3c99abb8272` completed 2026-11-04 07:54:57–08:02:36 UTC against the current live snapshot: **128 pass, 6 warning, 0 fail** across 134 gates. Snapshot: 6,678 Masters (6,657 current, 21 merged), 9,468 source opportunities, 51,747 observations, and 16 open reviews. DQ reported warning gates for source freshness, runtime anomalies, and unknown area stored as zero; no failing gates.
- Live catalog after preview shutdown: `NATIONAL_UI_ENABLED=false`, `NATIONAL_DASHBOARD_ENABLED=false`, `NATIONAL_MAP_ENABLED=false`.
- Live API health/readiness remain 200; readiness reports database, Redis, and worker `ok`.
- Furas enumeration/removal flags remain false. Manual source syncs initiated by this task: **0**. Business-data writes initiated by this acceptance turn: **0**.

## Final status fields

| Field | Result |
|---|---|
| `AUTHENTICATED_LOGIN` | `PASSED` in the first context |
| `AUTHENTICATED_BROWSER_VALIDATION` | `PARTIAL` |
| `NATIONAL_UI_ENABLED` | `FALSE` |
| `NATIONAL_MAP_ENABLED` | `FALSE` |
| `CURRENT_MASTERS` | `6,657` |
| `ALAHSA_MASTERS` | `518` |
| `VERIFIED_MAP_MASTERS` | `5,889` |
| `REGION_FILTER` | `PASSED` for tested regions |
| `DASHBOARD_LIST_PARITY` | `PASSED` for tested totals |
| `API_UI_CSV_XLSX_PARITY` | `PARTIAL` |
| `FINAL_DQ_FAIL` | `0` |
| `FINAL_REGRESSION_FAILED` | `0` |
| `MAP_DRILLDOWN` | `NOT TESTED` |
| `RESPONSIVE_VIEWPORTS` | `NOT COMPLETED` |
| `UNEXPECTED_JS_ERRORS` | `NOT VALIDATED` |
| `UNEXPECTED_5XX` | `NOT VALIDATED` |
| `FURAS_NATIONAL_ENUMERATION_ENABLED` | `FALSE` |
| `FURAS_REMOVALS_ENABLED` | `FALSE` |
| `MANUAL_SOURCE_SYNCS` | `0` |
| `BUSINESS_DATA_CHANGES_BY_THIS_ACCEPTANCE` | `0` |
