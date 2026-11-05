# Runtime Standardization Parity and Taxonomy Acceptance

Validation timestamp: 2026-10-19 08:42:47 UTC. The scheduler was held behind a temporary database pause flag for the runtime refresh and acceptance checks; the original flag was absent and was restored to absent after checks.

## Runtime parity

| Service | Executes standardization? | Running engine version | Runtime app code matches workspace? |
|---|---:|---:|---:|
| API | Yes; administrative sync endpoint can execute ingestion | 16 | Yes |
| Celery Worker | Yes; executes source ingestion tasks | 16 | Yes |
| Celery Beat | No; schedules/enqueues tasks only | NOT_APPLICABLE (v16 package is present) | Yes |
| Frontend | No | NOT_APPLICABLE | Not applicable |
| Migration / local bootstrap | No ongoing ingestion; one-shot/admin maintenance only | NOT_APPLICABLE | Not applicable |

SHA-256 comparison covered every Python module under `app/`, including standardization, source adapters, service ingestion, Celery tasks, taxonomy helpers, API filters, and exports. API, worker, and the rebuilt scheduler image match the workspace. Runtime engine module reported `16` in all three images. Beat does not itself standardize records.

The current Alembic revision and head are both `0021_asset_facility_type`. No migration was created or run. Existing database, Redis, and persistent volumes were not recreated or reset. Only the existing API, worker, and scheduler application containers were rebuilt/recreated.

## Data safety baseline

| Measure | Before | After |
|---|---:|---:|
| Masters (all) | 296 | 296 |
| Eligible Masters | 291 | 291 |
| Active Masters | 275 | 275 |
| Historical Masters | 16 | 16 |
| SourceOpportunity records | 2,898 | 2,898 |
| Observations | 7,603 | 7,603 |
| Change history | 1,012 | 1,012 |
| Open qualification reviews | 0 | 0 |
| Open taxonomy conflicts | 96 | 96 |

Master identities, Master-to-source links, source raw payloads, observation identities and payloads, change history, open taxonomy conflicts, and qualification-review fingerprints are byte-for-byte equivalent by SHA-256. Review counts by field are unchanged: sector 48, activity 20, sub-activity 1, opportunity type 14, investment model 2, owner 3, location description 4, land area 1, status 1, title 2. Asset/facility-type review conflicts: 0.

No source sync was manually started. The scheduled-source pause was active before refresh. The scheduler's `enqueue_due_sources` check returned `PAUSED`; source queues and active/reserved worker tasks were empty. There were no queued/running/retrying source jobs at the baseline. The pause flag was removed after acceptance, restoring its original absent state. After restoration, source queues were empty and the latest SyncJob remained ID 338.

## Live taxonomy reconciliations

All figures below use the same eligible population of 291 Masters.

- **Investment Model:** `التأجير` 4, `التجهيز والتشغيل والصيانة والنقل` 1, `غير محدد` 286; sum 291. Filter options, API list, Dashboard, CSV and XLSX agreed, including unique Master row counts.
- **Opportunity Type:** `تأجير مؤقت` 129 and `غير محدد` 162. API list and CSV/XLSX agreed.
- **Activity / Sub-Activity:** Activity filters reconciled to query counts; the Activity buckets sum to 291. `أنشطة التجارة العامة` resolves as `sub_activity:general_trade` with 8 Masters across filter, list, CSV and XLSX.
- **Sector:** the live `أخرى` bucket has 17 Masters; its filter, list, CSV/XLSX, details and Dashboard totals agreed.
- **Asset / Facility Type:** multi-valued; 131 assignments across 129 unique Masters, with 162 Masters unspecified. Counts: العربات المتنقلة 69, الحدائق 23, الشواطئ والواجهات 11, أخرى 10, الأراضي 8, الساحات والميادين 5, الطرق والأرصفة 4, المباني 1, غير محدد 162. Each option's filter count matched its API result, CSV and XLSX. `أخرى` (`asset_facility_type:other`) differs from `غير محدد` (`asset_facility_type:missing`).

The two multi-valued Masters (references `02-25-017001-73001` and `02-25-017001-73002`) each have `الساحات الميادين` and `الطرق والارصفة`. Each appears once in the unfiltered list and once under each applicable filter. The unfiltered API list contains 291 rows and 291 unique Master IDs. CSV/XLSX retain both labels in one row joined with ` | `. The RTL UI shows each multi-valued row once with both labels; the screenshot is [asset-facility-type-multivalue.png](../data/asset-facility-type-taxonomy/screenshots/asset-facility-type-multivalue.png).

Asset/facility types remain a Dashboard filter only; no Dashboard chart was added. XLSX remained 24 columns, right-to-left, with its asset-type column and existing model column intact.

## Isolated future-ingestion checks

The running v16 code was exercised with fixture values and read-only access to the live alias registry; no fixture records were inserted into business data and no source sync was run.

- Known Sector, Activity and Sub-Activity aliases resolve to their approved canonical IDs.
- Furas `TemporaryRental` maps to `تأجير مؤقت`; unknown Opportunity Type remains `REVIEW_REQUIRED` with raw evidence.
- `التأجير` and NCP `EOMT` map to their accepted Investment Model IDs.
- Missing Activity has `activity:missing` / `MISSING` semantics and displays as `غير محدد` through the existing API filter/list contract. Unknown Activity retains raw text and an `UNMAPPED` metadata identity. A technical enum in Activity (`PPP_PROJECT`) is excluded and flagged `REVIEW_REQUIRED`.
- All eight known structured Furas `LOCATIONTYPE` values map using current source/field aliases. Two values in one fixture yield two assignments. Missing input yields no false assignment; unknown and wrong-dimension values stay unresolved; other source fields are not treated as asset types.

`RUNNING_V16_FUTURE_INGESTION_RULES_VERIFIED = TRUE`

## UI and regression

Browser checks were performed at 1920×1080. Activity, Sector, Investment Model, and Asset/Facility Type checks confirmed RTL, no page-level horizontal overflow, functioning filters, details, search, pagination, reset, CSV/XLSX links or downloads, and Dashboard loading. The full regression suite passed **140 tests, 0 failures** (one upstream Starlette/httpx deprecation warning).

Evidence files include the [pre-refresh snapshot](pre-refresh.json), [post-refresh snapshot](post-refresh.json), [future-ingestion fixture results](future-ingestion-rules.json), [live taxonomy reconciliation](live-taxonomy-reconciliation.json), [live API reconciliation](../data/asset-facility-type-taxonomy/live-api-reconciliation.json), Activity QA summary at `docs/validation/ui/activity-taxonomy-acceptance/screenshots/qa-summary.json`, Investment Model UI evidence at `docs/validation/data/investment-model-taxonomy/screenshots/investment-model-ui-verification.json`, and the UI screenshots under the respective taxonomy validation directories.

## Acceptance

```ini
WORKSPACE_STANDARDIZATION_ENGINE_VERSION = 16
RUNNING_API_STANDARDIZATION_ENGINE_VERSION = 16
RUNNING_WORKER_STANDARDIZATION_ENGINE_VERSION = 16
RUNNING_BEAT_STANDARDIZATION_ENGINE_VERSION = NOT_APPLICABLE
API_RUNTIME_CODE_MATCHES_WORKSPACE = TRUE
WORKER_RUNTIME_CODE_MATCHES_WORKSPACE = TRUE
BEAT_RUNTIME_CODE_MATCHES_WORKSPACE = TRUE
RUNNING_V16_FUTURE_INGESTION_RULES_VERIFIED = TRUE
INVESTMENT_MODEL_TAXONOMY_RUNTIME_ACCEPTANCE = PASSED
ASSET_FACILITY_TYPE_TAXONOMY_RUNTIME_ACCEPTANCE = PASSED
ASSET_FACILITY_TYPE_IS_SINGLE_VALUED = FALSE
TOTAL_ASSET_TYPE_ASSIGNMENTS = 131
UNIQUE_MASTERS_WITH_ASSET_TYPE = 129
MASTERS_WITH_UNSPECIFIED_ASSET_TYPE = 162
ASSET_FACILITY_TYPE_FILTER_OPTIONS_CANONICAL_IDENTITY_OK = TRUE
ASSET_FACILITY_TYPE_OPTION_COUNTS_MATCH_QUERY_COUNTS = TRUE
ASSET_FACILITY_TYPE_MISSING_DISPLAY_LABEL = غير محدد
ASSET_FACILITY_TYPE_OTHER_AND_UNSPECIFIED_ARE_DISTINCT = TRUE
ASSET_FACILITY_TYPE_DASHBOARD_VISUAL_JUSTIFIED = FALSE
SECTOR_TAXONOMY_REGRESSION = PASSED
ACTIVITY_TAXONOMY_REGRESSION = PASSED
OPPORTUNITY_TYPE_TAXONOMY_REGRESSION = PASSED
INVESTMENT_MODEL_TAXONOMY_REGRESSION = PASSED
ASSET_FACILITY_TYPE_TAXONOMY_REGRESSION = PASSED
BROWSER_UI_VERIFICATION = PASSED
FULL_REGRESSION_SUITE = 140 passed / 0 failed
MANUAL_SOURCE_SYNC_STARTED = FALSE
UNINTENDED_SOURCE_SYNC_TRIGGERED = FALSE
BUSINESS_DATA_CHANGES_CAUSED_BY_RUNTIME_REFRESH = 0
RAW_PROVENANCE_PRESERVED = TRUE
```

`INVESTMENT_MODEL_TAXONOMY_DEEP_REVIEW_COMPLETE` and `ASSET_FACILITY_TYPE_TAXONOMY_DEEP_REVIEW_COMPLETE` remain accepted operationally.


