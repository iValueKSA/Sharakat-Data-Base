# RCU public investment opportunities integration — 2026-11-03

## Result

**RCU_INTEGRATION: COMPLETE**

The Royal Commission for AlUla (RCU) is registered as the distinct source `rcu-investment-opportunities`. The public catalog was completely enumerated, raw source publications were captured once, and six high-confidence new opportunities were promoted with source-specific provenance and audit records. No existing Master was linked based on title similarity.

## Extraction and identity

- **Method:** `PUBLIC_JSON_XHR` against `https://eservices.rcu.gov.sa/api/investment-opportunities/list`, with public paging parameters.
- **Current public records:** 6 of 6 reported; one page requested; pagination complete.
- **Stable identity:** provider `id` UUID; all six unique. The official `displayOpportunityId` (RCU-OPP-000255 through RCU-OPP-000260) is retained as the human reference.
- Raw JSON fields, descriptions, lifecycle flags and dates, categories, coordinates, attachments, publication metadata, source URLs, and extraction observations are retained in source provenance. Detail links use the verified route `/opportunities/detail/{uuid}`.
- The adapter does not create Masters during raw capture. The first controlled manual sync (job 752) succeeded with 6 inserted, 0 updated during sync, 0 removed, 0 bootstrap removals, and 0 Masters created during capture. There were no other manual source syncs.

## Identity review and promotion

The dry-run compared the six provider identities and opportunity evidence against all 6,626 pre-integration current Masters and 9,293 existing SourceOpportunity records, including Furas, Invest Saudi, PIF, NCP, RCJY, NHC, MODON and MWAN. It found:

| Disposition | Count |
|---|---:|
| A_READY_NEW_MASTER | 6 |
| B_MATCH_EXISTING_MASTER | 0 |
| C_IDENTITY_REVIEW | 0 |
| D_NOT_QUALIFYING | 0 |
| E_HISTORICAL_OR_NONCURRENT | 0 |
| F_SAME_SOURCE_DUPLICATE_REVIEW | 0 |

There were no exact reference matches or high-confidence project identity matches. Title-similarity candidates were retained as evidence only and did not authorize a merge. Six new Masters were created; zero existing Masters linked; zero duplicates prevented; zero duplicate provider keys. All six promotions and sector standardizations have audit events. Every promoted Master has an RCU source row and audit event.

The source's explicit `realEstateCategory.name` was preserved and mapped through the governed classifier: Transport → `الخدمات اللوجستية` (`sector:logistics`); Water & Waste → `البيئة` (`sector:environment`). This resolved the initial missing-sector DQ findings without weakening any gate.

## Geography and coordinates

Each record's own title or description identifies AlUla. Using `saudi_administrative_units` reference version `taadeen-public-gis-20261102-v3`, all six Masters map to **Al-Madinah Region** (`منطقة المدينة المنورة`, external id 3) → **Al Ula Governorate** (`العلا`, external id 302). City remains **UNSPECIFIED** because this reference does not provide verified city coverage for AlUla. The accepted 13-region filter implementation was not changed.

RCU supplied six numeric coordinate pairs in valid ranges. Three pairs repeat across records and the remaining pairs do not establish object-specific precision. They remain raw source evidence; no canonical coordinates were projected and no coordinates were fabricated.

## Backup and validation

The verified pre-RCU logical backup is `C:\Sharakat Data Base\backups\20261103T091708Z-fd5d733d.dump` (SHA-256 `1fe3c0199fedb6dea469df565220adc129714b4bab9292d7139110807e1d14c2`). Restore testing passed in an isolated PostgreSQL 16 container and matched the pre-RCU counts: 6,626 current Masters, 9,293 SourceOpportunity rows, and 12 configured sources. Alembic head was `0025_source_geographic_coverage`.

- Focused RCU adapter tests: **5 passed**.
- Full regression: **678 passed, 1 skipped, 0 failed**. The skip is the existing isolated PostgreSQL advisory-lock test, whose test database environment is not configured.
- Full DQ run `9a126eea2664421a8e0e9f06f57cde6c`: **128 PASS, 6 WARNING, 0 FAIL**. Warnings are the pre-existing general gates `GENERIC_SOURCE_PAGE_AS_OPPORTUNITY`, `HISTORICAL_REVIEW_AUDIT_INCOMPLETE`, `SOURCE_LAST_SUCCESS_TOO_OLD`, `SYNC_RUNTIME_ANOMALY`, `SOURCE_ABSENCE_CLASSIFICATION`, and `UNKNOWN_AREA_STORED_AS_ZERO`; none is RCU-specific.
- RCU source filter returned 6 current Masters. Region + governorate filter returned the same 6. Region options remain 13.
- Source health: technical **HEALTHY**, freshness **FRESH**, public coverage **COMPLETE_FOR_DEFINED_SCOPE**.
- API and readiness returned HTTP 200; PostgreSQL, Redis, worker and Beat were healthy; no active RCU jobs remained.

After the single controlled capture and validation, RCU's existing 24-hour schedule was enabled. No Furas or RCJY manual sync was run; no NCP Investors Portal, Ta’adeen or Tourism integration was started. RCJY remains unchanged at 3 source rows and 3 Masters.

## Final counts

At completion: 13 configured sources / 12 enabled; 6,653 Masters total (6,632 current, 21 merged); 9,299 SourceOpportunity rows. RCU contributes 6 source rows and 6 current Masters. First-run removals: 0.

## Current workspace follow-up verification

The live RCU integration remains healthy: 6/6 RCU source rows are linked to 6/6 current Masters, all six have `RCU_MASTER_CREATED` and `RCU_MASTER_SECTOR_STANDARDIZED` audit events, the source filter returns six, and the Al-Madinah Region → Al Ula Governorate filter returns the same six. City remains unspecified. There are no active RCU jobs.

- Focused RCU tests: **5 passed**.
- A fresh full DQ run `74b9566f82784fe781b8f2e235a7a3f7`: **128 PASS, 6 WARNING, 0 FAIL**. The six warnings are the existing generic-source-page, legacy review audit, source freshness, runtime anomaly, source absence classification, and unknown-area-as-zero gates; no RCU-specific warning was raised.
- The current full workspace regression run: **683 passed, 1 skipped, 1 failed**. The sole failure is `tests/test_wave3_adapters.py::test_ncp_public_archive_scope_is_separate_from_private_pipeline`, whose assertion still expects the NCP adapter docstring to say “private portal API” while the current adapter describes the public unauthenticated Investors Portal feed. NCP is outside this RCU task's permitted scope, so no NCP code or test was changed. This means the current full-regression success gate is **not met**, despite the earlier integration-time run recorded above.

Accordingly, the live RCU deployment is complete and operational, while the overall current validation status is **PARTIAL** until the out-of-scope regression assertion is reconciled in a separately authorized NCP task.

## Artifacts

- `RCU-MASTER-ELIGIBILITY-DRY-RUN-20261103.json` — per-record identity and promotion evidence.
- `RCU-SOURCE-INTEGRATION-MANIFEST-20261103.json` — machine-readable execution and validation manifest.
- `RCU-SOURCE-INTEGRATION-20261103.md` — this report.
