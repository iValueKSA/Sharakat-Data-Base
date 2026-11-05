# Final National Expansion Acceptance — 2026-11-03

**Result: PARTIAL.** Current live data, data-quality, and regression checks pass. National Region/Governorate API behavior, dashboard/list parity, and checked API/CSV/XLSX counts also pass. I did not activate the national UI or map because the configured bootstrap login was rejected; the authenticated live screens, responsive controls, map drilldown, and UI parity therefore could not be accepted. The Al-Ahsa filter also returns 84 of 518 matches with an unresolved display geography, so its zero-false-positive/negative condition is not certified.

## Current live reconciliation

- **6,678** Master rows = **6,657** current nonmerged + **21** merged; reconciliation passed.
- **9,467** SourceOpportunity rows across **14** configured sources; **6,769** are linked and **2,698** are unlinked. Shared source links make per-source current-master counts nonadditive.
- **0** open duplicate reviews and **12** open RCU conflicts (6 status, 6 deadline). All remain open and auditable.
- Ta’adeen: 28 source rows, 0 current Masters, HEALTHY/FRESH, source filter total 0.
- RCJY: 3 source rows and 3 current Masters. RCU: 6 and 6; governorate 302 (Al Ula) filter returns 6. NCP remains one source identity (`ncp`), with 185 source rows, 27 linked rows, and 26 distinct current Masters (25 portal-created Masters plus the prior linked Master). The prior accepted integration record accounts for 59 `Closed Transaction` observations left source-only.

All 14 sources with health, freshness, and link counts are recorded in [the reconciliation JSON](FINAL-NATIONAL-DATA-RECONCILIATION-20261103.json).

## Re-run checks

- Full DQ, run `045e12f1e13e4741962789b172cfcedc`: **127 PASS / 7 WARNING / 0 FAIL**.
- Full repository regression (`tests/`, excluding the nested `tests/tests` archive): **687 passed / 1 skipped / 0 failed**. The first pytest invocation accidentally included archived `tmp/` and `transfer/` copies and was discarded; the correctly scoped rerun passed.
- The 7 DQ warnings remain warnings, not failures. The regression skip remains the existing justified PostgreSQL-lock skip.

## Geographic acceptance

The current official reference is ready: **13 Regions, 149 Governorates, no national City dataset**. Region choices and parent-dependent Governorate options passed via live API; Eastern Province→Al-Ahsa, and Al-Madinah→Yanbu and Al Ula were confirmed. Region totals: Eastern 975, Riyadh 800, Makkah 319, Al-Madinah 458, Al-Ahsa 518. These memberships are nonadditive.

Dashboard/list API totals matched for All Saudi, Eastern, Riyadh, Makkah, Al-Madinah, and Al-Ahsa. Checked API/CSV/XLSX row counts matched for All Saudi (6,657), those geographic filters, and NCP (26), RCJY (3), RCU (6), RCU→Al Ula (6), and Ta’adeen (0; standard workbook empty-state row). The All Saudi XLSX contained 6,657 data rows and took 153 seconds to generate. UI parity was not testable without an authenticated session.

The Al-Ahsa 501 filter returns **518** rows. **84** are represented by the API as `LOCATION_UNSPECIFIED` with no governorate identity in their display geography, although source/reference membership selects them. Consequently the requested `ALAHSA_FALSE_POSITIVES=0` and `ALAHSA_FALSE_NEGATIVES=0` check is **unverified**, not assumed. The existing Hofuf locality filter returns 3 records.

## Map acceptance

A temporary in-process preview with national flags set only for that test read the live DB and returned 5,889 unique marker Master IDs from verified direct source coordinates; outside-boundary count was 0. The 6,657 current Masters classify as 5,889 verified-coordinate, 168 unverified-coordinate specific-location, 9 specific-location without coordinates, 591 location-unspecified/region-wide, 0 nationwide, and 0 Masters with multiple verified map points. Unverified, broad-scope, and unspecified records did not produce markers. Map browser rendering and marker/list drilldown were not validated, so the national map remains disabled.

## Browser and activation decision

Playwright navigated directly to `http://localhost:8080/`. The live shell rendered RTL with no horizontal overflow at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844; screenshots are [1920×1080](/C:/Sharakat%20Data%20Base/tmp/national-acceptance-1920.png) and [390×844](/C:/Sharakat%20Data%20Base/tmp/national-acceptance-390.png). There were 0 runtime page errors, 0 failed resources, and 0 unexpected 5xx; five expected `/api/auth/me` 401 responses appeared while unauthenticated.

The established bootstrap credentials were tried once and rejected. `AUTH_FLOW_VALIDATED=FALSE`; the authenticated dashboard/list filters, five-size control layout, UI/API/export parity, and map drilldown are not accepted. Both national UI and map gates remain blocked. Live `NATIONAL_UI_ENABLED`, `NATIONAL_DASHBOARD_ENABLED`, and `NATIONAL_MAP_ENABLED` remain false. Furas national enumeration and removals remain false. No migration, source sync, Master/link change, business-data edit, or review auto-resolution was made by this task. Scheduled job 763 completed naturally during the acceptance window; it was not started by this task.

## Final fields

| Check | Result |
|---|---|
| Current Master reconciliation | PASSED |
| DQ / full regression | 127/7/0; 687/1/0 |
| Region / Governorate API filters | PASSED |
| Dashboard/list API parity | PASSED |
| API/CSV/XLSX parity | PASSED for all-Saudi and checked filters; UI parity blocked |
| Al-Ahsa false positives / negatives | UNVERIFIED; 84 display-unresolved results |
| Authenticated live Playwright validation | FAILED / incomplete (authentication unavailable) |
| Responsive national UI | FAILED / not validated |
| National UI readiness / enabled | BLOCKED / FALSE |
| National map readiness / enabled | BLOCKED / FALSE |
| RCU conflicts block UI / map | TRUE / FALSE (status and timezone semantics remain unresolved) |
| Reports created | 3 |

Detailed conflict-by-conflict evidence and source reconciliation are in the companion JSON and [activation report](LIVE-NATIONAL-UI-MAP-ACTIVATION-20261103.md).

