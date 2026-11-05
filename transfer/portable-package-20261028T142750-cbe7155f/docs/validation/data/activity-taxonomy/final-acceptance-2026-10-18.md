# Activity taxonomy final acceptance — 2026-10-18

**Result:** `ACTIVITY_TAXONOMY_DEEP_REVIEW_COMPLETE`  
**Live API / browser validation:** `2026-10-18T12:14:05Z`  
**Project:** Al-Ahsa Investment Opportunities Platform (`http://localhost:8080`)

## Required reconciliation

```ini
SPORTS_RECREATION_FILTER_OPTION_ID = activity:sports_recreation
SPORTS_RECREATION_OPTION_QUERY_MATCH = TRUE

ACTIVITY_FILTER_OPTIONS_CANONICAL_IDENTITY_OK = TRUE
SUB_ACTIVITY_FILTER_OPTIONS_CANONICAL_IDENTITY_OK = TRUE

ACTIVITY_OPTION_COUNTS_MATCH_QUERY_COUNTS = TRUE
SUB_ACTIVITY_OPTION_COUNTS_MATCH_QUERY_COUNTS = TRUE

ACTIVITY_MISSING_DISPLAY_LABEL = غير محدد
ACTIVITY_OTHER_AND_UNSPECIFIED_ARE_DISTINCT = TRUE

TOTAL_ELIGIBLE_MASTERS = 291
ACTIVITY_IS_SINGLE_VALUED = TRUE
SUB_ACTIVITY_IS_SINGLE_VALUED = TRUE
MASTERS_WITH_CANONICAL_ACTIVITY = 146
MASTERS_WITH_UNSPECIFIED_ACTIVITY = 145
SUM_OF_CANONICAL_ACTIVITY_BUCKETS = 291
STANDARDIZATION_ENGINE_VERSION = 8

FULL_REGRESSION_SUITE = 128 passed / 0 failed
BROWSER_UI_VERIFICATION = PASSED
```

The live filter API returned 12 Activity and 11 Sub-Activity options. Every displayed count matched `/api/opportunities` queried with that exact option ID; option IDs were unique within each dimension. No displayed canonical filter option used an `unmapped:` ID. `أخرى` remains separate from missing Activity.

## Browser/API checks

Playwright loaded the Investment Opportunities screen directly. It confirmed the Activity selector contains one `غير محدد` option and one `الأنشطة الرياضية والترفيهية` option, with no raw technical IDs in visible labels. Selecting Sports/Recreation returned its expected Master (1), selecting missing Activity returned 145, and selecting `أنشطة التجارة العامة` returned 8. The missing Activity was shown in list rows and Opportunity Details as `غير محدد`; the Dashboard Activity selector and API use `activity:missing` and count 145.

The same browser pass verified reset to all 291 Masters, a Sector filter, search, pagination, opportunity details, CSV/XLSX browser downloads, and Dashboard load. Live filtered export verification parsed both files: CSV had 145 data rows and all Activity cells were `غير محدد`; XLSX had the same 145 rows and values. The full pytest suite included login/RBAC, filter, Dashboard, list/detail, and export tests. Its sole warning was the existing Starlette/httpx deprecation warning.

Machine-readable per-option results and UI checks are in [qa-summary.json](../../../../ui/activity-taxonomy-acceptance/screenshots/qa-summary.json).

## Screenshot evidence

- [Activity selector with Sports/Recreation selected](../../../../ui/activity-taxonomy-acceptance/screenshots/activity-sports-dropdown.png)
- [Sports/Recreation result](../../../../ui/activity-taxonomy-acceptance/screenshots/activity-sports-results.png)
- [Activity selector with `غير محدد` selected](../../../../ui/activity-taxonomy-acceptance/screenshots/activity-unspecified-dropdown.png)
- [Missing Activity results](../../../../ui/activity-taxonomy-acceptance/screenshots/activity-unspecified-results.png)
- [Sub-Activity `أنشطة التجارة العامة` results](../../../../ui/activity-taxonomy-acceptance/screenshots/subactivity-general-trade.png)

## Data safety

This acceptance pass used GET requests and browser downloads only. The full suite used isolated test databases; no sync endpoint, migration, review action, or business-data write was invoked. The latest source `SyncJob` present before the final Playwright capture was scheduled, at `2026-10-18T11:59:23Z`; no source sync was started by this verification.

The read-only integrity snapshot contains 291 eligible Masters and 2,898 SourceOpportunity rows. Master identity hash, source identity/link hash, and sector bucket counts match the accepted post-apply report:

- Master identities: `99ad96bf0f46ab3d7c8dc30c2de07170caf883bccff9270151808323064a5dd4`
- Source identities and links: `62173cf0a76224f4206ac95d04b5668ebedf8174541dcadc72363c1c4bb31744`
- Sector buckets: unchanged from the accepted report

The current raw-payload hash is `96d1b1e15f1ad8581e328986a67774b6dc8ecdd49ecd72848bccdc3fd9a6bdba`, while the earlier post-apply report records `714cf7751c107574758db6119f37061d3c16b232ddd371371520a46aadf331a2`. The source-job history shows scheduled refreshes before this final Playwright capture. This verification did not write payloads; therefore the historical hash difference is recorded as prior/background drift rather than attributed to this acceptance pass.

No Master identity, SourceOpportunity link, Sector classification, or Activity/Sub-Activity semantic classification was changed by this final verification.
