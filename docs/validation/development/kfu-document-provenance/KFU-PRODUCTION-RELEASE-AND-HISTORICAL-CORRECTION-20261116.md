# KFU production release preparation and historical correction plan

**Date:** 2026-11-16 UTC  
**Mode:** isolated release preparation; production reads only  
**Decision:** `KFU_COLLECTOR_RELEASE=VALIDATED_READY_FOR_AUTHORIZATION`; no deployment or production correction was executed.

## Final status

- `KFU_RELEASE_READINESS_STATUS=VALIDATED_READY_FOR_AUTHORIZATION`
- `COLLECTOR_PATCH_FILES=app/adapters.py` in the worker image; parser tests and fixtures in the isolated worktree; release files under `release/kfu-collector-20261116/`
- `PRODUCTION_BASELINE_COMPATIBILITY=PASS_FOR_WORKER_IMAGE_AND_SCHEMA`
- `COLLECTOR_EXECUTION_SERVICES=Celery Worker executes collector; Celery Beat enqueues; API only enqueues manual requests`
- `KFU_SCHEDULE_STATUS=ENABLED; 720_MINUTES; NO_ACTIVE_JOBS_AT_CHECK; NEXT_DUE_APPROX_2026-11-16_18:35_UTC`
- `SIX_RECORD_IMPACT_RECONCILIATION=6 SourceOpportunity rows; 12 inherited raw metadata references; 1 supported, 2 confirmed wrong, 9 unverified/held`
- `SUPPORTED_REFERENCES=1`
- `CONFIRMED_WRONG_REFERENCES=2 (both on SourceOpportunity 2928 / Master 326)`
- `UNVERIFIED_REFERENCES=9 (held; no automatic removal or reassignment)`
- `HISTORICAL_CORRECTION_DRY_RUN=PASS_ROLLBACK_ONLY; 2928 raw_data_json.attachments 2 -> 0 in simulation; exact originals retained in review provenance; rollback verified`
- `SOURCE_IDENTITY_REGRESSION=PASS; 2774 and 2928 remain distinct provider IDs and Masters 225 and 326; no merge/rekey/relink`
- `ISOLATED_TEST_RESULTS=111 passed, 2 skipped across worker suites and Documents MVP gates`
- `DOCUMENTS_PUBLISHED=0; production opportunity_documents=0`
- `PRODUCTION_DATA_MUTATIONS=0`
- `PRODUCTION_DEPLOYMENT_STATUS=NOT_DEPLOYED`
- `FINAL_DECISION=VALIDATED_READY_FOR_AUTHORIZATION; separate authorizations still required for deployment and historical correction`

## Production baseline and candidate scope

Read-only inspection found the active compose project at the canonical local platform root. Production services remain running. The Worker image is `alahsa-local-worker@sha256:d6d5f9d0dbf912a35250b4865337cae89f3f34ece8bc2727ebc3c8d71df341aa` (container `alahsa-local-worker-1`). Production Alembic head is `0027_opportunity_documents_mvp`; the opportunity document table contains zero rows. The patch adds no schema requirement and changes no API, export, frontend, scheduler, or Documents MVP code.

Only the Worker executes `app.tasks.sync_source_task` and imports `service.sync_source` plus the KFU adapter. Beat (`alahsa-local-scheduler-1`) enqueues due-source work every minute. The API can enqueue manual syncs but does not execute collection. A future deploy needs a Worker-only image recreate; Beat and all other services stay unchanged.

The isolated release context copies only `app/adapters.py` into the exact running Worker image. Existing production code was compared before build; the source difference is limited to the KFU parser. Parser version is `2026.11.16-kfu-2`. The KFU parser now scopes files to their exact notice panel, classifies forms separately, leaves shared listing files at listing scope, does not invent notice URLs, fails closed on ambiguous titles/cross-panel files, and retains the established provider ID formula. Historical page provenance is additive; no historical source observation is deleted or rewritten.

Artifacts:

- Candidate build context and release notes: [release/kfu-collector-20261116/README.md](../../../../release/kfu-collector-20261116/README.md)
- Machine-readable hashes and validation: [release/kfu-collector-20261116/manifest.json](../../../../release/kfu-collector-20261116/manifest.json)
- Guarded rollback-only simulation: [dry_run_historical_metadata.py](../../../../release/kfu-collector-20261116/scripts/dry_run_historical_metadata.py)
- Per-reference register: [kfu-reference-decision-register-20261116.csv](kfu-reference-decision-register-20261116.csv)
- Earlier six-record impact report: [KFU-AND-INVESTSAUDI-IDENTITY-REVIEW-20261116.md](KFU-AND-INVESTSAUDI-IDENTITY-REVIEW-20261116.md)

## Snapshot and isolated historical correction dry run

The production backup was `/backups/20261116T062832Z-902f6a17.dump`, status `SUCCESS`, size 67,109,149 bytes, SHA-256 `2d1512e6c9db48d7f492921b8bc38d617c7eaea5eb32daabfcd91b74ed068fdc`. It was restored to a private, disposable PostgreSQL container without exposing a host port. The backup was taken before migration 0027; the current production schema remains at 0027. The six allowlisted KFU rows in the restored snapshot matched production exactly at comparison time for source/provider ID, Master ID, lifecycle status, parser version, last-seen timestamp, content hash, and `raw_data_json` MD5. The snapshot contained 9,470 SourceOpportunity rows, 6,680 Masters, 7 KFU SourceContentItem rows, 60,153 SourceObservation rows, 951 sync jobs, and zero opportunity documents.

The simulation was guarded to accept only database host `kfu-snapshot-pg`, database `kfu_snapshot`, and `KFU_CORRECTION_DRY_RUN=YES`. It targeted exactly SourceOpportunity 2928, provider `kfu-announcement:0aac035af08807f4f1755ee5`, Master 326. In one transaction it simulated the single field change `source_opportunities.raw_data_json.attachments: [2 refs] -> []`; it retained the exact two URLs and their reason in `attachment_provenance_review.original_references`. All six source rows, seven historical content items, all source observations, Master identities/links/status, row counts, and document count were compared before and after. No other field/record changed. The transaction was rolled back without commit, and exact original payload equality was verified (`DRY_RUN_PASS_ROLLBACK_ONLY`).

Production `SourceOpportunity.raw_data_json.attachments` is not serialized by public Opportunity responses. Raw source and source-content APIs are admin-gated; production has no normalized `OpportunityDocument` rows. Thus no public normalized attachment association needs a production cleanup. Keep the nine unverified references held: do not clear them merely because they are ambiguous. Preserve their raw captures and observations. For the two confirmed wrong references on 2928, retain their original URLs in source listing provenance and the audit marker if a separately approved historical metadata correction is ever needed.

## Exact six-record reference decisions

Every row currently stores two page-wide URLs with `downloaded=false`, `checksum=null`, and no document publication record. Full per-reference details, including stored field, source evidence, classification, and proposed action, are in the CSV register.

| SourceOpportunity | Master | Reference decisions | Proposed handling |
|---:|---:|---|---|
| 2773 | 224 | Investor guide: `UNVERIFIED_HOLD_FOR_REVIEW`; 2025 tender booklet: `SUPPORTED_KEEP` | Keep the booklet associated with the expired food-services tender. The guide is outside the notice panel; preserve it as listing provenance, without opportunity association. |
| 2774 | 225 | Guide and booklet: `UNVERIFIED_HOLD_FOR_REVIEW` | Removed legacy identity with a different provider ID from current 2928 despite equal stored title. Preserve provider ID and Master 225; no merge, reassignment, or inference from title. |
| 2775 | — | Guide and booklet: `UNVERIFIED_HOLD_FOR_REVIEW` | Removed procurement snippet; no item-level file evidence. Hold both and preserve observation history. |
| 2776 | — | Guide and booklet: `UNVERIFIED_HOLD_FOR_REVIEW` | Removed procurement snippet; no item-level file evidence. Hold both and preserve observation history. |
| 2777 | — | Guide and booklet: `UNVERIFIED_HOLD_FOR_REVIEW` | Removed procurement snippet; no item-level file evidence. Hold both and preserve observation history. |
| 2928 | 326 | Guide and old tender booklet: `CONFIRMED_WRONG_REMOVE_FROM_DERIVED_METADATA` | Current seasonal-rental panel has only an application form. The guide is outside notice panels; the booklet belongs to the separate expired 2025 tender. Preserve exact source URLs as listing evidence. |

Official KFU evidence came from the [Investment Administration announcements page](https://www.kfu.edu.sa/ar/Departments/Investment/Documents/Newdesign/%D8%A7%D8%B9%D9%84%D8%A7%D9%86%D8%A7%D8%AA-%D8%A7%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9.html). The old tender panel includes the booklet, states a 2025-01-22 deadline and SAR 300 booklet price. The current seasonal-rental panel exposes a Google Form only. The investor guide appears outside both notice panels. No notice-specific stable official ID or detail URL is available. Public accessibility does not establish download, redistribution, or publication rights.

## Identity, scheduling, release hashes, and tests

SourceOpportunity 2774 remains `kfu-announcement:7e98c5dfb12b0a6d09f4c349` -> Master 225. SourceOpportunity 2928 remains `kfu-announcement:0aac035af08807f4f1755ee5` -> Master 326. The parser regression tests resolve both independently, preserves the existing URL-plus-normalized-title key for current items, and does not match by title alone. It does not create/reassign Masters or classify disappearance as cancellation. Invest Saudi records 218–221 were not investigated or changed.

Current KFU source state, read-only at 2026-11-16 10:26 UTC: enabled, 720-minute interval, healthy, last successful sync `2026-11-16 06:35:30 UTC`, zero queued/running/retrying jobs, no schedule changes. The next normal due time is approximately 18:35 UTC. The old Worker can continue to attach page-wide links if a scheduled sync occurs before the candidate is deployed; this is an active, bounded risk. No collection was triggered.

Release hashes:

- Production Worker base image: `sha256:d6d5f9d0dbf912a35250b4865337cae89f3f34ece8bc2727ebc3c8d71df341aa`
- Candidate Worker tag: `alahsa-local-worker:kfu-provenance-candidate-20261116`
- Candidate image ID/manifest digest: `sha256:b8191dd075d7fe4cc7ec2542cfefe5bdc46f9a634dfe5c5cf338ed4b4d46c08a`
- Copied `app/adapters.py` SHA-256: `e64519ebe36c193a8446a413f8a31137dada6d306924c9003c90e208ef0023bc`

Candidate Worker suites: **104 passed, 2 skipped**; skipped cases are optional PostgreSQL Source Identity Alias integration tests because their dedicated DB was not configured. KFU-specific selection: **36 passed**. Separate Documents MVP API plus migration-gate tests: **7 passed** against a fresh disposable PostgreSQL container. Combined latest count: **111 passed, 2 skipped**. The Worker candidate passed an import smoke check during build. Warnings were limited to upstream pytest cache read-only mount, Starlette/httpx deprecation, and Alembic configuration deprecation; no assertion failures remain.

## Future controlled sequence and recovery

Deployment and historical correction each require separate explicit authorization; neither was granted by this preparation request.

1. Before deployment, take a fresh production backup and verify its metadata/hash. Confirm production Worker still matches the stated base digest, schema head remains 0027, and no KFU job is active. Review the candidate manifest and exact source hash.
2. Recreate only the Worker service from the candidate; do not rebuild/recreate Beat, API, frontend, DB, or Redis. Keep the KFU schedule unchanged and do not call manual sync. The next regular scheduled run uses the corrected Worker.
3. After that run, use read-only checks to confirm parser version, the two current provider identities and Master links, no duplicate source/master creation, listing-page guide provenance, booklet association only to the old tender, and unchanged historic observations. Confirm no document was downloaded or published and `opportunity_documents` remains empty.
4. Reinspect 2928. If the normal corrected collection removed the two false derived associations and retained listing evidence, the separate historical write is unnecessary. If they remain, stop and request separate authorization for the exact one-row, one-field correction simulated here. Never automatically clear the nine held references or alter the supported booklet link.
5. Before any authorized correction, make another fresh backup, capture exact target-row before JSON, and rerun the allowlisted dry run against an isolated restore. In production, apply only the approved field-level change with transaction guards, audit marker and before/after hashes. Verify all six identities/Master links, all raw observation history, other records, geographic fields, lifecycle fields, and document rows unchanged.
6. Before the first corrected collection, runtime rollback is the saved original Worker image. After a sync, image rollback alone will not restore changed data and could let the old parser reintroduce shared links on a later run. Any post-sync runtime or data recovery requires a separately reviewed plan: retain a copy of the exact prior `raw_data_json`, restore only the approved field if necessary, preserve observations/content items, and coordinate any old-worker use with the scheduled collector. Do not restore the full database.

## Remaining blockers and decision

- Collector deployment authorization is pending.
- Historical metadata correction authorization is independently pending; defer it until after the corrected normal collection to avoid a redundant write.
- The old Worker remains active, so a scheduled collection before authorized deployment can reproduce the current cross-notice metadata. Schedule changes were expressly out of scope.
- Nine historical reference associations remain unverified and held; the 2774/2928 legacy identity difference is a separate review item.
- Document access/reuse rights are not established; no document is eligible for publication from this work.

`KFU_COLLECTOR_RELEASE=VALIDATED_READY_FOR_AUTHORIZATION` for the isolated candidate. `PRODUCTION_DEPLOYMENT_STATUS=NOT_DEPLOYED`; `HISTORICAL_CORRECTION=PREPARED_AND_DRY_RUN_VALIDATED_NOT_APPLIED`. Next action: authorize (or decline) the Worker-only deployment separately from any later one-row historical correction.

## Safety record

Production database operations were read-only. Production data mutations: 0. Migrations: 0. Deployments/restarts: 0. Source syncs/replays: 0. Schedule changes: 0. Document publications: 0. Master/identity changes: 0. No Invest Saudi, Furas, RCU, geographic, UI, or Documents MVP infrastructure changes were made as part of this release preparation.
