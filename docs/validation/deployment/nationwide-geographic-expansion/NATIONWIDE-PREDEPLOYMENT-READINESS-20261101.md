# Nationwide expansion — predeployment readiness

**Review date:** 2026-11-01 (Asia/Amman)  
**Decision:** Technical predeployment readiness is complete after isolated browser validation and the one required post-change regression run. Official geographic reference data remains unverified, so production national rollout remains blocked. No production migration, reference import, code deployment, or flag change was made.

## Final isolated UI validation

The final browser evidence is recorded in [NATIONAL-UI-BROWSER-VALIDATION-20261101.md](NATIONAL-UI-BROWSER-VALIDATION-20261101.md). Both city-reference variants passed all **56 Playwright checks**: the full Region/Governorate/City case and the Region/Governorate-only case. CSV/XLSX parity passed in all eight filter combinations. Dashboard and Opportunities views passed at all five required viewports with RTL, overflow, control visibility, and overlap checks. There were **0 JavaScript errors** and **0 unexpected HTTP 5xx**. Twenty Playwright screenshots, one additional real-tile map screenshot, and machine-readable result files are in [ui-evidence](ui-evidence/).

The browser uses an isolated clone restored from the verified pre-change backup, migrations 0024 and 0025, and explicit `TEST_*` reference IDs. The clone contains the 566 pre-existing baseline Masters plus 60 synthetic TEST Masters. Browser query cases use `q=TEST` where isolation is required. Test-only coordinates are synthetic and explicitly verified in the disposable DB; no fabricated coordinates were added. The Al-Ahsa quick-view resolver was exercised only through a test-only Arabic alias; this is not a claim that a synthetic ID is the official Al-Ahsa identity.

The Furas Job 666 lifecycle finding is documented separately in [FURAS-JOB-666-READONLY-ANALYSIS.md](FURAS-JOB-666-READONLY-ANALYSIS.md). Its root cause is confirmed as a transient post-sync DQ ordering race, and no recovery or retry was executed. Furas enumeration remains disabled. The unresolved Furas lifecycle gate remains a separate source-expansion blocker.

## 1. Current live state — read only

Final snapshot captured from `alahsa-local-api-1` at **2026-11-01 13:29 UTC**. Every database query used an explicit read-only transaction; flags were read as booleans only. No production write was made by this validation.

| Measure | Observed |
|---|---:|
| Alembic revision | `0023_quant_commercial` |
| Masters total / current | 587 / 566 |
| SourceOpportunity rows | 3,180 |
| Source observations (latest persisted DQ snapshot) | 34,403 |
| Sync jobs / active at final snapshot | 669 / 0 |
| Open duplicate candidates / conflicts | 0 / 0 |
| Qualification reviews / location reviews | 0 / 26 |
| Change history / merge audits | 2,630 / 21 |
| Audit events / system events | 3,764 / 17,998 |
| Enabled sources | 10 |

The latest persisted fast DQ result at the final snapshot was for automatically scheduled Job **669** and still failed only `SYNC_JOB_STATE_CONSISTENCY` (sample 669). Jobs 666–669 show the same transient ordering pattern: DQ persisted the sample while its job row was not yet in terminal state; the jobs subsequently ended `SUCCESS / COMPLETED` with `finished_at`. Job 666 itself completed 5/5 pages with 375 unique records and no error. Historical Furas Jobs 644 and 651 remain deadlock failures; Job 652 completed successfully and exhibited the same transient lifecycle gate. See the read-only analysis for timestamps and safe next steps.

Jobs 666–669 were scheduled automatically, not started by this task. Independent scheduled activity continued during this review, increasing operational job/event/observation counts; Master, current Master, SourceOpportunity, review, and audit counts remained at the reported values. This task initiated **zero manual source syncs or backfills** and made **zero application/database writes**.

Live flags read from the API process were `NATIONAL_UI_ENABLED=false`, `NATIONAL_MAP_ENABLED=false`, `NATIONAL_DASHBOARD_ENABLED=false`, and `FURAS_NATIONAL_ENUMERATION_ENABLED=false`. Production remains on 0023; all geographic reference/coverage tables are absent, and `/api/geography/catalog` returns 404. The existing dashboard geography endpoint still returns the legacy local Al-Ahsa map (566 Masters in scope; 435 exact mapped; 433 point groups), not the national map contract. No `TEST_*` Master marker was found in production.

There are 19 existing Invest Saudi SourceOpportunity rows linked to Masters in the live database. This task created/promoted none; `INVEST_SAUDI_PROMOTIONS=0` is task activity, not a claim that pre-existing source links are absent.

## 2. Gap analysis

The capability-by-capability status and exact behavior are in [NATIONWIDE_PREDEPLOYMENT_GAP_ANALYSIS.md](NATIONWIDE_PREDEPLOYMENT_GAP_ANALYSIS.md). The genuine implementation gaps were completed in the workspace: dependent selectors, URL restoration, dashboard search/geography parity, national dashboard summary, verified-coordinate national map payload, source-to-region coverage schema, and controlled validation/import commands. No official geographic data was populated.

## 3. Work completed

- Added fail-closed geographic feature gates for the national UI, dashboard, and map. A flag cannot bypass a missing/invalid current reference. Furas enumeration remains a separate, default-off switch.
- Added dependent Region → Governorate → optional City selectors and quick filters. They remain hidden unless both the reference is ready and the national UI flag is true. Al-Ahsa resolves from a verified reference when present, with the existing local filter as fallback.
- Unified geography and `q` predicates across the opportunity list, pagination, dashboard, map, CSV and XLSX. Added a regression test confirming matching Master counts and exported rows.
- Prepared national dashboard summaries that count unique Masters. Membership counts are explicitly non-additive; national-scope opportunities are not assigned to every region.
- Prepared national map output from verified source coordinate provenance only. `NATIONWIDE`, `REGION_WIDE`, and `UNSPECIFIED` scopes never create markers; a multi-location Master remains one unique Master in dashboard totals.
- Added source-to-region geographic coverage storage in migration 0025. Unrecorded assessments remain `NOT_ASSESSED`; no coverage rows were inserted.
- Added a synthetic fixture using only `TEST_*` identifiers and names, no Saudi administrative names, and no coordinates. Production validation and the production import CLI reject it. Explicit test mode is dry-run-only.
- Added a future official validator and controlled import CLI. Dry-run reports counts and SHA-256 with zero writes. Committing requires `--confirm-production-import`, a verified backup manifest, an explicit confirmation environment value, a passing production validation, migration 0024+, and a new immutable version. The command was not run against an official dataset.
- Added rollback provenance that retains imported versions and does not delete or rewrite business/source records.
- Added the [national rollout runbook](NATIONAL-ROLLOUT-RUNBOOK.md), including the approval boundary for Furas.

## 4. Isolated migration result

The verified PostgreSQL 16 dump was restored into the disposable, networkless `nwx-predeploy-db-20261101` container. Baseline head was `0023_quant_commercial`. Migration 0024 upgraded the isolated application database; migration 0025 was then applied there for source geographic coverage. No production database was used for migration testing.

The post-0025 database is at `0025_source_geographic_coverage`. The restored `before` database remains at 0023. Counts and primary-key digests matched between those databases for:

- opportunities: 587, `fec1601af1de60782cc117f1decdb436`
- SourceOpportunity: 3,180, `3814eefb835b07502fb04b9b44527380`
- observations: 33,377, `9a5715df7af9774b10f729140f7bcea1`
- OpportunityLocation: 29, `56810932563efe89de83bf2e217def02`
- location reviews: 26, `be65a4d6324659481d2880e13e6dcdc6`
- duplicate candidates: 47, `8100cdf2278a2638f75588ad0dfb528d`
- conflicts: 1,116, `21d0d95ab4ff9f23bce8adbcce0c50f7`
- audit events: 3,764, `ad163b6e4573458a8a1fc194c032e4ab`
- change history: 2,628, `142c7c504e5b6306ed50c2353a61b62c`
- merge audits: 21, `d3c5e77d72f660d435b66e657ef928a2`
- system events: 16,122, `b1083c56a069b82bb1c5258381d56b9b`

Qualification review count was 0 in both. The pre-existing Opportunity semantic fingerprint matched through 0024. New nullable geographic fields remained empty; both geographic reference tables had zero rows, and the new source coverage table had zero rows. The separate clean-bootstrap failure at migration 0022 (`canonical_status` already exists) was not changed.

## 5. Reference validation readiness

`GEOGRAPHIC_REFERENCE_READY=false`. Region, Governorate, and City/Center references are all `NOT_VERIFIED`. The test-only fixture validates in explicit test mode (7 units: 1 country, 1 region, 2 governorates, 3 cities; SHA-256 `f4fb94156c80c8bd25aa0b8dd8552d00c7c6c2964abe98741e40e727d56c655e`). Production-mode validation rejects the fixture. The CLI importer dry-run on this fixture returned `imported=false` and `writes_performed=0`; a confirmed-import invocation refused the same fixture before checking any production database or backup.

The production validator will require an ISO effective date, a version, source authority, verified license and evidence URL, stable-ID attestation, verified parent relationships, completeness evidence, explicit expected counts, correct 13-region count for official production coverage, unique identities, valid parents, and a matching content digest. City coverage is optional for Phase 1.

## 6. Filter, dashboard, and map readiness

- **Filters and exports:** Region/Governorate/City and scope contract is consistent across table, deterministic pagination, search, dashboard, map, CSV and XLSX. Specific-region filters do not implicitly include national-scope opportunities.
- **Dashboard:** unique totals count Masters. A Master linked to multiple places is not counted multiple times in the total; regional membership counts are labeled non-additive.
- **Map:** national points require explicitly verified HTTPS source coordinates. Broad scope or unknown location cannot generate a marker. KSA map center/extent is only a viewport.
- **City optionality:** Region and Governorate can be enabled without City/Center; City selector is hidden when that level is absent.
- **Source coverage:** the matrix schema is ready, but absent regional assessments report `NOT_ASSESSED`, not zero coverage.

## 7. Feature flag safety and Al-Ahsa

All three live flags remain false. National UI/map code is not deployed to the live service, and no API catalog or selector was exposed there. The currently running service remains on 0023 and continues its existing Al-Ahsa map experience. Workspace code preserves the local map path whenever the national map gate is false. The existing Al-Ahsa filter path was included in the focused geography tests.

## 8. Tests and limitations

- Pre-existing focused geography/dashboard checkpoint: **28 passed**. Post-change location-geography and nationwide-safety focused tests: **24 passed**.
- Pre-change full-suite checkpoint (`pytest tests`): **620 passed**, 40 warnings. Warnings were existing Starlette/httpx and Alembic configuration deprecations.
- JavaScript syntax checks passed for `national-geography.js`, `app.js`, and `data-dashboard.js`.
- A live Playwright run against both isolated reference variants passed all 52 checks; detailed check names, CSV/XLSX counts, viewport results, and screenshots are in the browser report and evidence directory. Production remains on the older build by design.
- Because workspace application code was changed to resolve the discovered UI/API issues, the complete regression suite was run once at the end: **620 passed, 40 existing deprecation warnings** in 71.54 seconds.
- No production migration, reference import, sync, backfill, promotion, or flag change was executed by this task.

## 9. Remaining blockers and next actions after NCAR/GEOSA responds

The remaining geographic blocker is a licensed, versioned, effective-dated authoritative Region/Governorate file with stable IDs, parent keys, and completeness evidence. Do not substitute Ta’adeen or NCM as the canonical production reference. City is optional for Phase 1.

When the official reference arrives, follow [NATIONAL-ROLLOUT-RUNBOOK.md](NATIONAL-ROLLOUT-RUNBOOK.md): archive authority and license evidence, checksum and validate the original, approve it, restore a backup in isolation, apply 0024/0025 there, import and run DQ/UI/API tests, obtain explicit production approval, then schedule production migration/import with flags still off. Verify production read-only before controlled flag changes. Expand sources one at a time. Furas requires separate approval and lifecycle/DQ work; the recurring `SYNC_JOB_STATE_CONSISTENCY` ordering race must be corrected and a clean DQ-only result observed before any Furas national enumeration.

## Final status

```text
NATIONWIDE_PREDEPLOYMENT_READINESS = COMPLETE
ISOLATED_NATIONAL_UI_ENVIRONMENT = PASSED
NATIONAL_OPPORTUNITIES_BROWSER = PASSED
REGION_FILTER_BROWSER = PASSED
GOVERNORATE_FILTER_BROWSER = PASSED
CITY_FILTER_BROWSER = PASSED
REGION_GOVERNORATE_WITHOUT_CITY_BROWSER_TEST = PASSED
ALAHSA_QUICK_VIEW_BROWSER_TEST = PASSED
NATIONAL_DASHBOARD_BROWSER = PASSED
NATIONAL_MAP_BROWSER = PASSED
FILTER_API_EXPORT_BROWSER_PARITY = PASSED
PLAYWRIGHT_1920x1080 = PASSED
PLAYWRIGHT_1440x900 = PASSED
PLAYWRIGHT_1366x768 = PASSED
PLAYWRIGHT_768x900 = PASSED
PLAYWRIGHT_390x844 = PASSED
RTL = PASSED
NO_HORIZONTAL_OVERFLOW = TRUE
NO_TEXT_OVERLAP = TRUE
JAVASCRIPT_ERRORS = 0
UNEXPECTED_HTTP_5XX = 0
FAKE_COORDINATES_CREATED = 0
TEST_FIXTURE_IN_PRODUCTION = 0
FURAS_JOB_666_ROOT_CAUSE = CONFIRMED
FURAS_JOB_666_RECOVERY_EXECUTED = FALSE
ISOLATED_0023_TO_0024_MIGRATION = PASSED
GEOGRAPHIC_REFERENCE_VALIDATOR = READY
GEOGRAPHIC_REFERENCE_DRY_RUN_IMPORT = READY
REGION_FILTER_CODE = READY
GOVERNORATE_FILTER_CODE = READY
CITY_OPTIONALITY = SUPPORTED
REGION_GOVERNORATE_WITHOUT_CITY_SUPPORTED = TRUE
ALAHSA_QUICK_VIEW = READY
NATIONAL_DASHBOARD_CODE = READY_BEHIND_FLAG
NATIONAL_MAP_CODE = READY_BEHIND_FLAG
FILTER_API_EXPORT_PARITY = PASSED
TEST_FIXTURE_CANNOT_BE_IMPORTED_TO_PRODUCTION = TRUE
GEOGRAPHIC_REFERENCE_READY = FALSE
PRODUCTION_ALEMBIC_HEAD = 0023
MIGRATION_0024_PRODUCTION_APPLIED = FALSE
MIGRATION_0025_PRODUCTION_APPLIED = FALSE
NATIONAL_UI_ENABLED_PRODUCTION = FALSE
NATIONAL_MAP_ENABLED_PRODUCTION = FALSE
NATIONAL_DASHBOARD_ENABLED_PRODUCTION = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
INVEST_SAUDI_PROMOTIONS = 0
MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
BUSINESS_DATA_CHANGES = 0
REVIEW_DATA_CHANGES = 0
PRODUCTION_SCHEMA_CHANGES = 0
FAKE_PRODUCTION_GEOGRAPHIC_RECORDS = 0
```

`COMPLETE` means the technical predeployment implementation and isolated browser validation are complete. It does not approve production rollout: `GEOGRAPHIC_REFERENCE_READY=false`, the live service remains on 0023 with flags off, and the separate Furas source-enumeration gate remains unresolved. No `NATIONWIDE_EXPANSION = ACCEPTED_AND_CLOSED` decision is made.
