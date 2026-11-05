# Final National UI and Map Acceptance

**Date:** 2026-11-04 (Asia/Amman)  
**Environment:** `alahsa-local` (`http://localhost:8080`)  
**Final decision:** `FINAL_NATIONAL_GO_LIVE = UI_ONLY`

## Decision

The authenticated national UI passed its live filter, list, dashboard, export, and responsive checks. The isolated national map preview also passed its data, filter, drilldown, and five-viewport checks. I briefly enabled the map under the task’s conditional authorization. The post-activation browser then received one unexpected HTTP 504 from `/api/data-dashboard/geography-summary?`; the zero-5xx gate failed, so I reverted only `NATIONAL_MAP_ENABLED` to `false`. The national UI and dashboard flags remain enabled.

## Final status

```text
FINAL_NATIONAL_GO_LIVE = UI_ONLY
NATIONAL_UI_ACCEPTANCE = PASSED
NATIONAL_MAP_ACCEPTANCE = FAILED (post-activation HTTP 504; map flag rolled back)
NATIONAL_UI_ENABLED = TRUE
NATIONAL_DASHBOARD_ENABLED = TRUE
NATIONAL_MAP_ENABLED = FALSE
CURRENT_MASTERS = 6657
ALAHSA_CURRENT_MASTERS = 518
VERIFIED_COORDINATE_MASTERS = 5889
CURRENT_MASTER_MAP_PARTITION = PASSED
AUTHENTICATED_BROWSER = PASSED
DASHBOARD_LIST_PARITY = PASSED
API_UI_CSV_XLSX_PARITY = PASSED
MAP_DRILLDOWN = PASSED
MAP_FILTER_PROPAGATION = PASSED
RESPONSIVE_VIEWPORTS = PASSED (national UI and isolated map preview at all five sizes)
FINAL_DQ_FAIL = 0
FINAL_REGRESSION_FAILED = 0
UNEXPECTED_JS_ERRORS = 0
UNEXPECTED_HTTP_5XX = 1 (HTTP 504 during live map activation)
MANUAL_SOURCE_SYNCS = 0
BUSINESS_DATA_CHANGES = 0
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
FURAS_REMOVALS_ENABLED = FALSE
```

The final live API is healthy and ready. Database, Redis, and worker checks are `ok`; the API container is healthy. The live geography catalog reports `reference_ready=true`, status `READY`, national UI and dashboard `true`, and national map `false` after rollback.

## Health, data quality, and regression

| Check | Result |
|---|---|
| API live / ready | HTTP 200 / `ready` |
| Database / Redis / worker | `ok` / `ok` / `ok` |
| Current Masters | 6,657 |
| Final full DQ | 128 pass / 6 warning / 0 fail, 134 gates |
| Final DQ run ID | `2bb0fda03397454b9c2766ce51de9663` |
| Map partition gate | PASS; observed 6,657, expected 6,657 |
| Regression | 693 passed / 1 justified skip / 0 failed |

The final DQ ran after map rollback in a read-only transaction with `persist=false`. Its map partition detail is: 5,889 `inside_exact`, 0 `outside_boundary`, 604 `unverified_coordinates`, and 164 `missing_coordinates`. The map endpoint’s `missing_coordinates=768` is the non-mappable remainder and includes the 604 unverified-coordinate members; the DQ partition detail explicitly distinguishes those categories. Full final evidence is in [stage-final-dq-full-read-only.json](evidence/final-acceptance-20261104/stage-final-dq-full-read-only.json). The earlier Stage 1 full DQ is [stage1-dq-full-read-only.json](evidence/final-acceptance-20261104/stage1-dq-full-read-only.json).

The 693-test regression result is reused from the accepted map-partition remediation report because this acceptance made no application-code or migration changes. Only the map environment flag was toggled and then restored. See [NATIONAL-MAP-PARTITION-ROOT-CAUSE-20261104.md](NATIONAL-MAP-PARTITION-ROOT-CAUSE-20261104.md).

## Authenticated live UI

The user authorized Playwright use and signed into the persistent browser. `/api/auth/me` returned HTTP 200 before tests and after the API restart. No credentials, cookies, or tokens were exposed in the report.

| Screen / filter | UI | API or independent result | Result |
|---|---:|---:|---|
| All Saudi opportunity list | 6,657 | 6,657 | PASS |
| Eastern Region | 975 | 975 | PASS |
| Riyadh | 800 | 800 | PASS |
| Makkah | 319 | 319 | PASS |
| Al-Madinah | 458 | 458 | PASS |
| Al-Ahsa governorate | 518 | 518 | PASS |
| Hofuf locality | 3 | 3 | PASS |
| RCJY source | 3 | 3 | PASS |
| RCU source | 6 | 6 | PASS |
| NCP source identity `ncp` | 26 | 26 | PASS |
| Ta’adeen source | 0 | 0 | PASS |
| Available status | 6,517 | 6,517 | PASS |
| Search `MOMAH` | 1 | 1 | PASS |
| Sector `البلديات والإسكان` | 3 | 3 | PASS |

Pagination moved from page 1 to page 2 and back; the reset control cleared filters and restored 6,657. The region, governorate, locality, sector, status, source, and search controls have labels or accessible names and remain keyboard-focusable. Dashboard totals matched the opportunities list for all regions above and Al-Ahsa.

## CSV and Excel parity

Exports were fetched from the authenticated live export endpoints and read from their actual contents. CSV records were counted with PowerShell `Import-Csv`; Excel records were counted from non-empty opportunity rows in the worksheet, excluding the report preamble/header. Ta’adeen’s workbook contains its “no matching opportunities” placeholder but zero opportunity records.

| Filter | UI / API | CSV records | XLSX records | Result |
|---|---:|---:|---:|---|
| All Saudi | 6,657 | 6,657 | 6,657 | PASS |
| Eastern Region | 975 | 975 | 975 | PASS |
| Riyadh | 800 | 800 | 800 | PASS |
| Makkah | 319 | 319 | 319 | PASS |
| Al-Madinah | 458 | 458 | 458 | PASS |
| Al-Ahsa | 518 | 518 | 518 | PASS |
| RCJY | 3 | 3 | 3 | PASS |
| RCU | 6 | 6 | 6 | PASS |
| NCP (`ncp`) | 26 | 26 | 26 | PASS |
| Ta’adeen | 0 | 0 | 0 | PASS |

The captured export files are in [evidence/final-acceptance-20261104/exports](evidence/final-acceptance-20261104/exports).

## Responsive UI evidence

Both the opportunities screen and the dashboard were checked at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. Document/body widths did not exceed the viewport. Filters and pagination remained visible at mobile width, and the dashboard charts and map panel remained within the layout. The isolated map preview was separately rendered at all five sizes without page-level horizontal overflow.

Screenshots are in [evidence/final-acceptance-20261104](evidence/final-acceptance-20261104), including `opportunities-{1920x1080,1440x900,1366x768,768x900,390x844}.png`, `dashboard-{1920x1080,1440x900,1366x768,768x900,390x844}.png`, and `map-preview-{1920x1080,1440x900,1366x768,768x900,390x844}.png`.

## Isolated national map preview

The map-enabled preview API was isolated on `localhost:18001`; the live map flag remained `false` during preview. Preview catalog readiness was `READY`, with all 13 regions and 149 governorates available. The map API returned 6,657 Masters, 5,889 exact verified-coordinate Masters, and 5,847 clustered points. The flattened marker IDs contained 5,889 distinct Master IDs with no duplicates; the DQ partition and source-coordinate verification reported zero outside-boundary points. The map is built from direct source-coordinate evidence; unverified and broad-scope records do not create markers.

Filter propagation in preview and again on the live map returned:

| Filter | Dashboard/list total | Verified map Masters |
|---|---:|---:|
| All Saudi | 6,657 | 5,889 |
| Eastern Region | 975 | 377 |
| Al-Ahsa | 518 | 27 |
| RCJY | 3 | 0 |

Clustering was interactive: clicking a cluster expanded the visible cluster/marker set. A verified Al-Ahsa marker opened a popup for Master `5996`; “عرض الفرص في القائمة” opened a one-row filtered list. The resulting API/list record retained ID `5996`, canonical ID `FURAS-NAT-4d56218fe514d8f3d93376b0`, and the same title as the marker popup. Live evidence is [live-map-marker-popup.png](evidence/final-acceptance-20261104/live-map-marker-popup.png) and [live-map-drilldown-master-5996.png](evidence/final-acceptance-20261104/live-map-drilldown-master-5996.png).

## Activation and rollback

After all preview and national UI gates passed, I changed only `NATIONAL_MAP_ENABLED` to `true` in `docker-compose.local.yml` and recreated the API service using the established local Compose configuration. The live authenticated map rendered as “خريطة الفرص الوطنية”; it showed 6,657 total Masters and 5,889 verified Masters. Live Eastern, Al-Ahsa, and RCJY filter propagation and Master 5996 drilldown passed.

The post-activation dashboard request `/api/data-dashboard/geography-summary?` returned HTTP **504** once. This failed the task’s `UNEXPECTED_HTTP_5XX = 0` gate. Following the task’s rollback instruction, I restored only `NATIONAL_MAP_ENABLED=false` and recreated the API. `NATIONAL_UI_ENABLED` and `NATIONAL_DASHBOARD_ENABLED` stayed `true`. The map preview passed; live map acceptance is marked failed because post-activation acceptance did not meet the zero-5xx requirement. The live map screenshot before rollback is [live-map-before-rollback-1920x1080.png](evidence/final-acceptance-20261104/live-map-before-rollback-1920x1080.png).

Runtime monitoring recorded zero JavaScript page errors. It recorded one console resource error corresponding to the HTTP 504 above and one HTTP 5xx total. OpenStreetMap tile requests canceled during viewport changes/navigation reported `net::ERR_ABORTED`; these were canceled requests, not HTTP failures.

## Source activity and change control

No manual source syncs were started. One natural scheduled job ran during the acceptance window: `alahsa-opportunities`, job `780`, trigger `scheduled`, successful from 2026-11-04 11:40:22Z to 11:41:13Z, with 0 new and 0 updated Masters. The final observation snapshot rose from 51,810 to 51,829 during that scheduled activity; current Masters stayed at 6,657. No Master records, source links, RCU decisions, or accepted geography were edited. Furas national enumeration and removals remained disabled.

## Interrupted attempts and reruns

- An early combined Al-Ahsa dashboard/list parity call timed out; separate dashboard and list API checks subsequently returned 518 and passed.
- The first all-Saudi CSV read timed out at its short request limit while the response was streaming. A separate bounded request completed, and the saved CSV contained 6,657 records.
- The first preview source-filter attempt targeted a collapsed advanced-filter panel and timed out. Expanding the panel allowed the RCJY filter to be applied and verified at 3 total / 0 mapped.
- A preview summary read was interrupted when its browser context closed. After reconnecting, the summary completed with 6,657 unique Masters and 5,889 mapped unique Masters.
- The initial live post-activation map-title wait timed out; a follow-up read confirmed that the live map had rendered. The separate HTTP 504 on the geography summary remained and triggered the map-only rollback.
- A final post-rollback browser catalog read reset the browser kernel. The final state was independently confirmed from the live catalog, container environment, and health endpoint: UI/dashboard `true`, map `false`, catalog `READY`, API `ready`.

No interrupted attempt is counted as a pass unless its independent rerun completed.
