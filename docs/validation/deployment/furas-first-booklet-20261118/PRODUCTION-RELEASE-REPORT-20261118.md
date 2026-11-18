# First Real Furas Booklet — Production Release Report

**Execution date:** 2026-11-18 (UTC)  
**Release status:** `PUBLISHED_AND_TECHNICALLY_VERIFIED`  
**Production visual acceptance:** Pending user's live review; no automated browser use was performed.

## Authorized release

- Deployed only the approved API image `sha256:1eab3bfeded9a77af3520051eefdd287bd7a4c10b2bc8261fcdb789b77669825` and frontend image `sha256:e07c53b4d491399396111e76c850a267a00295c8979b654a9cc9c619810a2602`.
- Recreated only `api` and `frontend`, with `--no-deps --no-build`. No migrations or configuration changes were made.
- API readiness returned `ready`; `http://localhost:8080/` returned HTTP 200. API image digest matches the approved digest; frontend digest matches the approved digest.
- The existing Worker, Scheduler, PostgreSQL and Redis containers were not recreated. Worker ping returned `pong`; Scheduler continued emitting routine Beat dispatch logs; PostgreSQL and Redis remained running and healthy.
- Rollback tags verified before deployment: `alahsa-local-api:rollback-furas-booklet-20261118T080535Z` (baseline API digest `sha256:be0e5ac43f9030bbcf441c4a3e96b08fcad3c1ea1bfe1977d5eedd31ab123ba4`) and `alahsa-local-frontend:rollback-furas-booklet-20261118T080535Z` (baseline frontend digest `sha256:defb9fd08a2cedda79ba23d8bbf64a3a4420952dc004b52976e1d634173bdcd5`). Rollback was not executed.

## Backup and recovery gate

- Custom-format PostgreSQL backup: `C:\Users\QusaiAbdElhalim\AppData\Local\Sharakat Data Base\backups\furas-first-booklet-predeploy-20261118T080038Z.dump`
- Size: 68,116,109 bytes. SHA-256: `29868e01183591d1963d25f80b55ddf41182fb11ec588694d110e21b9048f4e7`.
- `pg_restore --list` passed. Restore into an isolated, network-disabled PostgreSQL 16 container passed. Restored state: Alembic `0027_opportunity_documents_mvp`, 6,680 opportunity rows (6,659 current, 21 merged), 9,470 SourceOpportunity rows, 75 aliases, zero document rows before rehearsal; SourceOpportunity 3188 remained linked to Master 597.
- In the disposable clone, the approved seed inserted one DRAFT on its first run, zero on repeat, and the targeted rollback removed exactly the DRAFT. The post-rehearsal document count returned to zero.

## Single document publication

- Published document ID: `1`; SourceOpportunity `3188`; Master `597`; provider reference `01-26-017001-42008`; audit event ID `16554` (`OPPORTUNITY_DOCUMENT_PUBLISHED`).
- Production document counts: before `0`; after `1`; approved `1`. The DRAFT was hidden from the public API before publication. The production seed's repeat inserted zero rows.
- The current API publication validator returned `VALIDATED_NO_WRITE` for the exact, source-bound candidate before the atomic status update and audit insert.
- `GET /api/opportunities/597` returned exactly one approved document: `كراسة الشروط والمواصفات`, category `TERMS_AND_CONDITIONS_BOOKLET`, attributed to `فرص – البوابة الموحدة للاستثمار`.
- The destination is the official opportunity page: `https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment`. It is marked `VERIFIED_SOURCE_PAGE`; download status is `UNAVAILABLE`; participation is `PURCHASE_REQUIRED_FOR_PARTICIPATION`. Published amount and currency are both null. The failed attachment identifier/path does not appear in API output.
- SourceOpportunity 3188 still maps to Master 597; Master canonical ID remains `AH-20261026060233-679af3af` and is non-merged. Counts remained 6,680 total / 6,659 current / 21 merged Masters, 9,470 source rows, 75 aliases. No unrelated opportunity or source identity mutation was observed.
- Unrelated Master 226 still returns an empty document list.

## Source evidence

- Ordinary read-only HTTP revalidation of the official page returned HTTP 200. The configured official GIS evidence reported `OPPORTUNITYACTIVESTATUS=Announced`; the page showed a live countdown and the booklet purchase action.
- The page date is labeled `تاريخ فتح المظاريف` and was not presented as a submission deadline. The page's attachment request redirected to `/list-opportunities` and returned HTML rather than a booklet download. No direct attachment link, purchase URL, price, or currency was published.
- The user's manual preview acceptance and prior desktop screenshot were accepted as UI evidence. No automated browser interaction or new screenshot was used. Final visual review of production and mobile review remain with the user.

## Post-publication checks

- API readiness: `ready`; frontend root: HTTP 200.
- Anonymous `GET /api/auth/me`: 401. Anonymous `GET /api/admin/users`: 401.
- CSV export scoped to Master 597: HTTP 200, 1,631 bytes, target reference present.
- XLSX export scoped to Master 597: HTTP 200, 164,291 bytes, ZIP signature valid.
- National map API: HTTP 200; `NATIONAL`, 6,659 current Masters, 6,309 mapped, 350 unmapped.
- Geography summary: dataset `taadeen-public-gis-20261102-v3`, 6,659 current Masters, 6,309 mapped. Al-Ahsa governorate ID 501 remains at 518 total, 447 mapped and 71 unmapped.
- Unrelated Master 226 remains document-free; export and geography checks passed.
- On API, Worker and Scheduler: `FURAS_NATIONAL_ENUMERATION_ENABLED=false`, `FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED=false`, and `RCU_SCHEDULED_SYNC_ENABLED=false`. No queued or active source jobs were present during checks. No Furas sync was triggered by this release.

## KFU correction evidence note

Read-only verification found SourceOpportunity 2928 still linked to Master 326 and its derived `attachments` array remains empty. However, the previously recorded `attachment_provenance_review` marker is absent from the current `raw_data_json`, contrary to the 2026-11-16 correction report. The latest KFU job before this release was scheduled job 1013 (2026-11-18 06:27–06:29 UTC, success, two unchanged records); job 996 on 2026-11-17 recorded two updates. The current canonical JSON SHA-256 is `0806e23594eac117b76f8ad9492ec39b3fd340c6433e026031c8cf296a55687f`, while the prior correction report recorded `ab53aae739a9c55e5fffeed50d5142b25e44bbb2cdbdd7e19afc8a2a4e08abf0`. The cause of this later raw-payload difference is not established. No KFU data was changed as part of this release; resolving the discrepancy requires separate review.

## Final decision

`FIRST_REAL_BOOKLET_RELEASE = PUBLISHED_AND_TECHNICALLY_VERIFIED`

Production API, export, security, and geography checks passed. The only remaining release acceptance is the user's visual review of the live page. The KFU marker discrepancy is separately documented and was not modified.

**Live platform:** `http://localhost:8080/?view=opportunities&q=01-26-017001-42008`  
**API detail:** `http://localhost:8080/api/opportunities/597`

