# Automated Document Collection Engine — Phase 2

**Execution date:** 2026-11-18  
**Technical status:** `VALIDATED_READY_FOR_DEPLOYMENT_AUTHORIZATION`  
**Live deployment:** `NONE`  
**Production database writes by this work:** `ZERO`  
**Production service restarts by this work:** `ZERO`

The engine and both release images passed isolated technical validation. Real-source access and candidate yield remain limited: the original 25-opportunity sample still has 17 temporary page timeouts and two actual source-page 404s. One record is ready for a source-page-only approval review; eight candidates remain held for human review. No candidate was approved or published.

## Hardening completed

- Added six independent fail-closed flags for engine, manual collection, scheduled collection, candidate staging, automatic approval, and automatic publication. All default to off. Manual collection also requires engine and staging to be enabled.
- Kept collection tasks out of Celery Beat. Candidate image inspection found five explicitly registered tasks, no document-collection Beat entries, and all flags off.
- Bounded task retries to three, with exponential delay, jitter, a 1,800-second maximum, and `Retry-After` support. Only temporary and processing failures retry. Restricted and confirmed not-found outcomes do not retry as temporary errors.
- Kept source collection mutually exclusive across PostgreSQL worker processes with a source-scoped advisory lock. Added a five-failure, 120-second temporary circuit breaker and a per-host request interval. Failure state and verification history are persisted.
- Added transport phase labels for future timeout evidence (`TCP_CONNECT`, `TLS_HANDSHAKE`, `HTTP_REQUEST`, response headers, and response body). Earlier pilot events predate this instrumentation and cannot be retroactively assigned a network phase.
- Fixed recovery after source outages: a successful unchanged recheck now restores the evidence-derived verification state, clears the failure count, refreshes missing-evidence state, and records a durable `CANDIDATE_RECOVERED` event.
- Corrected source-page fallback evidence so a verified opportunity page does not retain the stale `DOCUMENT_ACCESS_NOT_VERIFIED` marker. The direct-file failure remains recorded.
- Stopped treating a same-host purchase action as a verified purchase destination. Its observed URL remains private evidence; it is not exposed as an actionable purchase URL until separately verified without submitting payment or an application.
- Candidate content fingerprints now include purchase-action verification and missing-evidence state so material evidence changes are not silently treated as unchanged.

## Files changed for this phase and release

- `.env.example`
- `app/main.py`
- `app/models.py`
- `app/celery_app.py`
- `app/document_collection/config.py`
- `app/document_collection/tasks.py`
- `app/document_collection/engine.py`
- `app/document_collection/verifier.py`
- `app/document_collection/adapters/furas.py`
- `migrations/versions/0028_document_collection_engine.py`
- `tests/test_document_collection_api.py`
- `tests/test_document_collection_engine.py`
- `tests/test_document_collection_postgres_concurrency.py`
- `tests/test_document_collection_tasks.py`
- `tests/test_document_collection_verifier.py`
- `tests/test_furas_offline_replay.py`
- `release/document-collection-phase2-20261118/api.Dockerfile`
- `release/document-collection-phase2-20261118/worker.Dockerfile`

The API Dockerfile is based on the exact active API image and copies only the API/model/Celery collection additions, the new collection package, and migration 0028. The Worker Dockerfile is based on the exact active Worker image; it adds the current API Documents MVP model and unchanged `app/documents.py`, then the Phase 2 collection files. It does not copy the worktree frontend, source adapters, or unrelated modifications. The active API `main.py` and `models.py` differ from this worktree by 124 and 97 additive lines, respectively, with no removals. The Worker model overlay supplies its missing Documents MVP fields plus the collection models.

SHA-256 hashes for the release source set and candidate images are in [phase2-release-manifest.sha256](phase2-release-manifest.sha256).

## Fresh regression results

Executed with Python 3.12, pytest, and the existing API runtime image in disposable Docker test containers. The full targeted batch finished **131 passed, 0 skipped, 0 failed** in 32.33 seconds. Eight deprecation warnings came from Starlette/httpx and Alembic configuration; no warning was a test failure.

The batch covered document extraction and Furas classification, URL/SSRF controls, identity association, staging/deduplication, task flags and retry/backoff, PostgreSQL concurrency, migration 0028, offline Furas replay, KFU provenance isolation, Documents MVP/publication gates, authentication/security, geography, dashboards, exports, Furas aliases/quarantine, and capture manifests.

Reproducible command from the project root (the env file contains only disposable test database URLs):

```powershell
docker run --rm --network furas-booklet-validate-20261118 `
  --env-file "$env:TEMP\doccollection-phase2-full.env" `
  -v "${PWD}:/app:ro" -w /app `
  --entrypoint python opportunity-documents-mvp-api:furas-booklet-20261118 `
  -m pytest -q -rs -o cache_dir=/tmp/pytest-cache `
  tests/test_document_collection_engine.py `
  tests/test_document_collection_verifier.py `
  tests/test_document_collection_api.py `
  tests/test_document_collection_tasks.py `
  tests/test_document_collection_postgres_concurrency.py `
  tests/test_opportunity_documents_migration_postgres.py `
  tests/test_furas_offline_replay.py `
  tests/test_kfu_document_provenance.py `
  tests/test_opportunity_documents.py `
  tests/test_production_security.py `
  tests/test_location_geography.py `
  tests/test_geography_summary.py `
  tests/test_data_dashboard.py `
  tests/test_export_storage.py `
  tests/test_excel_presentation.py `
  tests/test_source_identity_aliases.py `
  tests/test_furas_identity_quarantine.py `
  tests/test_furas_capture_manifest.py
```

The full run enabled the two alias database integration cases against the separate, synthetic `furas_alias_test` database. It also executed the formerly skipped offline replay concurrency case against an isolated restored snapshot. The test aligns one captured record on that disposable database before measurement; two concurrent replay operations then produced no duplicate SQL writes. No national enumeration or production database was used.

## Concurrency and recovery evidence

Four real PostgreSQL integration tests passed:

1. Two task invocations for one source serialize under the database advisory lock; replay keeps the same candidate identity.
2. A staging transaction interrupted after candidate work rolls back cleanly; a resumed run leaves no partial candidate and retains failure/recovery history.
3. Candidate metadata refresh preserves version history and leaves published Document 1 unchanged.
4. Concurrent approval is row-locked and idempotent; it never creates a public document.

The tests use separate PostgreSQL connections and include concurrency barriers. Task retry scheduling is tested at the Celery boundary; actual data processing, locks, candidate staging, and approval transactions run against PostgreSQL.

The offline replay concurrency test also passed after the initial disposable restore was aligned to the saved capture baseline. The measured pair of concurrent operations returned the same existing `SourceOpportunity` and emitted no writes. A first reconciliation can legitimately write to the isolated snapshot; that setup is outside the measured replay and is documented in the test.

## Migration 0028 and restored production snapshot

Migration 0028 follows `0027_opportunity_documents_mvp`. Its SHA-256 is:

`F4726457B10B8D432D593B029DB23890682A08ED12AF3BCC7ED6CCDF61E7EED0`

It creates three additive tables only:

- `document_collection_runs`: source/scope/status, counts, resumable checkpoint and summary JSON, timestamps, and a status check constraint.
- `document_collection_candidates`: exact source/Master/provider association, document identity and version, titles/types/URLs, access/rights/purchase state, raw and verified price evidence, private JSON provenance, missing evidence, hashes, review/verification state, and uniqueness/check constraints.
- `document_verification_events`: append-only collection, retry, refresh, recovery, and review events with before/after hashes and source/candidate/run foreign keys.

Indexes cover the source, run, candidate, review, status, provider, event type, and created-at access paths. All foreign keys to existing data are restrictive. No existing table is altered and no historical data migration runs. No file content is stored; the tables retain metadata and bounded JSON evidence. Run/event storage grows with collection attempts; retention and monitoring policy must be decided before any scheduled activation.

A read-only production dump was made at 2026-11-18 11:15 UTC, size 68,163,197 bytes, SHA-256 `FC5FFC43AE8E18250F83C74AF2F197370508FD6C55566195771AA0FC500BF739`. `pg_restore --list` succeeded. The dump was restored to isolated PostgreSQL 16 database `phase2_prod_restore_20261118` at head 0027. A separate clone was upgraded 0027 → 0028, downgraded to 0027, and upgraded to 0028 again; a repeated upgrade at head was a no-op. The migration regression also exercised constraints and the additive rollback behavior.

| Snapshot | Head | Masters | Source opportunities | Source observations | Aliases | Published documents |
|---|---|---:|---:|---:|---:|---:|
| Isolated restored backup | 0027 | 6,680 | 9,470 | 62,044 | 75 | 1 |
| Isolated migrated clone | 0028 | 6,680 | 9,470 | 62,044 | 75 | 1 |

Document 1 remained `APPROVED`, linked to SourceOpportunity 3188 and Master 597. Its serialized-row SHA-256 before/after and in the current production read is `2c46ba8597e8179dd956043257beb04799099253959c517b5756fcef5c6f59c2`.

The migration downgrade drops all three new collection tables and their run/candidate/event evidence. It is only safe before collection data exists. After first use, do not downgrade; roll forward or perform an explicitly authorized full restore.

The exact current API and Worker images were also run read-only against the 0028 clone. The old API read Document 1 and the old Worker read Masters, SourceOpportunities, and the published-document table successfully. This validates backward-compatible reads on the additive schema, not old-image write behavior against new tables.

## Pilot metrics — opportunity and document units

### Opportunity-level outcomes

The original cohort contains **25 unique existing SourceOpportunity rows**. Initial mutually exclusive outcomes were 6 completed, 17 temporary page timeouts, and 2 HTTP 404 source-opportunity pages. Only the six original candidate-bearing/reference records (3188 and 41–45) were reprocessed. They required 20 bounded processing attempts across retries; the final page checks for all six succeeded. The other 17 timeouts and two 404s were not retried or reclassified.

Final latest opportunity outcomes therefore remain **6 completed, 17 temporary failures, and 2 not found**, across 25 unique opportunities. The 17 remain temporary rather than missing; the two 404s were the opportunity pages themselves, not confirmed missing attachments. The source-level outcome rows are in [phase2-opportunity-outcomes.csv](phase2-opportunity-outcomes.csv).

### Document-level outcomes

- 10 unique document references in the original discovery: one matched published Document 1 and nine became staged candidates.
- One unique duplicate identity was prevented against Document 1. Re-discovery logged four additional duplicate-prevention hits; no duplicate document or candidate row was created.
- Final candidate set: 9 identities, 1 `DRAFT_CONTRACT`, 8 `UNKNOWN_DOCUMENT_TYPE`; 1 ready for approval, 8 need review, 0 rejected, 0 published.
- Direct attachments: 6 temporary failures, 3 listing-page redirects, 0 confirmed file downloads.
- Nine raw `RFPPRICE` values were retained as evidence; verified amounts, verified currencies, and public prices remain 0.
- Reprocessing added 0 candidate identities and 0 newly ready candidates. The original single ready candidate remains the only ready candidate.

The candidate-grain decisions are in [phase2-candidate-review-register.csv](phase2-candidate-review-register.csv), with machine-readable totals in [phase2-pilot-metrics.json](phase2-pilot-metrics.json).

## Temporary failures and classification

The original 17 opportunity-page failures were recorded as `TimeoutError`, HTTP status 0. Their Phase 1 event rows do not record whether each timeout occurred during DNS, TCP connect, TLS handshake, or HTTP response. The two `NOT_FOUND` records have actual HTTP 404 status on the opportunity page. No captured event shows 403, 429, 5xx, login, or a TLS certificate failure.

During Phase 2, six first rechecks timed out; five failures opened the 120-second host circuit and the next attempt was short-circuited. After recovery, five rechecks completed, and the remaining page later completed as well. A narrow diagnostic confirmed `furas.momah.gov.sa` resolved, TCP/443 connected, and the exact 3188 page returned HTTP 200. This supports intermittent HTTPS transport/source availability rather than a persistent DNS or policy block; the historical events are insufficient to identify the exact phase for every timeout.

For the nine candidate attachment routes, six remained temporary and three redirected to the general listing. A listing redirect is not a document download. Candidate 45’s opportunity page later returned successfully, but its generic attachment labels remain unclassifiable; it is now held for review instead of marked unreachable.

Future timeouts now record the specific verifier phase. No TLS verification, access restriction, or provider policy was bypassed.

## Nine candidate decisions and proposed record

Candidate IDs 2–9 remain `PENDING` and `NEEDS_REVIEW`: the Furas display title is only “تحميل” and does not establish whether the item is a booklet, contract, form, drawing, or other attachment. Three of their direct routes redirect to a listing; the other five candidate routes timed out. Keep all eight private until exact item/category evidence is available.

Candidate 1 is the single `READY_FOR_APPROVAL` source-page-only proposal:

```json
{
  "candidate_id": 1,
  "source_opportunity_id": 3188,
  "provider_opportunity_id": "01-26-017001-42008",
  "master_opportunity_id": 597,
  "source_document_id": "270741922",
  "title": "تحميل",
  "document_type": "DRAFT_CONTRACT",
  "document_scope": "OPPORTUNITY",
  "official_opportunity_page": "https://furas.momah.gov.sa/index.php/ar/opportunity/01-26-017001-42008?type=Investment",
  "proposed_link": "official opportunity page only",
  "access_status": "PUBLIC_SOURCE_PAGE",
  "rights_status": "SOURCE_PAGE_LINK_ONLY",
  "link_verification_status": "VERIFIED_SOURCE_PAGE",
  "direct_attachment_outcome": "TEMPORARY_FAILURE",
  "participation_requirement": "PURCHASE_REQUIRED_FOR_PARTICIPATION",
  "authentication_required": false,
  "payment_required_for_document": null,
  "raw_price": {"field": "RFPPRICE", "value": "1500", "result": "PAGE_LABEL_AMOUNT_MISMATCH"},
  "verified_amount": null,
  "verified_currency": null,
  "public_price": false,
  "actionable_purchase_url": null,
  "review_status": "PENDING",
  "published": false
}
```

The exact provider opportunity and SourceOpportunity/Master association were verified. The source page includes lifecycle evidence (`Announced` and a captured “39 days 13 hours” countdown excerpt). The direct attachment was not confirmed, so the proposal is page-only and must never be rendered as a download action. `RFPPRICE=1500` is not a document price: the nearby page evidence mismatched the booklet-price label/value, and no currency was independently evidenced. A purchase action was observed, but its route was not opened or executed and is not exposed as verified. This proposal is not approved or published.

The published booklet Document 1 was rediscovered at every successful 3188 recheck and deduplicated. It remains published at the same identity with no price/currency and no false direct-download URL.

## Review security and provenance

- Anonymous requests are rejected; Viewer cannot approve. Admin/analyst review writes use the existing role checks. Candidate/history/run endpoints remain private admin APIs.
- Invalid state transitions are rejected; exact source/Master association and non-merged Master are rechecked before approval.
- Concurrent repeated approval is idempotent, audited, and does not publish. Publication remains a separate explicit gate.
- Restricted, rejected, or unverified candidates remain absent from the public Documents API.
- Collection run/checkpoint, candidate evidence, and verification/recovery/review events are separate durable records. Normal source metadata replacement does not overwrite this event history. KFU attachment isolation/provenance regression passed; no KFU production row was changed.

## Production baseline and release candidates

Production remains on `0027_opportunity_documents_mvp` and its active images remain unchanged:

- API base: `opportunity-documents-mvp-api:furas-booklet-20261118`, `sha256:1eab3bfeded9a77af3520051eefdd287bd7a4c10b2bc8261fcdb789b77669825`.
- Worker base: `alahsa-local-worker`, `sha256:b8191dd075d7fe4cc7ec2542cfefe5bdc46f9a634dfe5c5cf338ed4b4d46c08a`.
- API candidate: `opportunity-documents-mvp-api:phase2-20261118-candidate`, `sha256:3d34d678c6082c04f5de650202441191e6738caae6771d388bc7bd6667968418`.
- Worker candidate: `opportunity-documents-mvp-worker:phase2-20261118-candidate`, `sha256:ab2070b8ab955ddaba98fdacc2615f5da803c9abe66366102289788c3e301613`.

Candidate API smoke validation loaded all six private routes, read Document 1 from the migrated clone, and showed all flags false. Candidate Worker loaded all five collection tasks, read the migrated schema, showed all flags false, and showed no collection task in Beat. No Frontend or Scheduler candidate image is needed. Required production changes, if separately authorized, are the API image, Worker image, and migration 0028.

## Deployment and rollback plan — not executed

1. Before deployment, take a fresh production PostgreSQL backup and restore it into isolated PostgreSQL 16. Recheck counts and Document 1 hash against the live baseline.
2. Keep all six document flags false and do not add a Beat schedule. Confirm existing Worker active tasks and queue state before recreating the Worker.
3. Apply migration 0028 once, verify head and table constraints, then recreate only API and Worker with the exact candidate image digests above. Do not recreate Frontend or Scheduler.
4. Verify health, 6,680/9,470 business row counts, 75 aliases, one published document, Document 1 identity/hash, private route authorization, all flags off, and no collection Beat entries.
5. First controlled use, only after separate authorization: explicit allowlist of at most 25 existing SourceOpportunity IDs, manual task invocation, review the private candidate batch, and separately authorize any approval/publication. No national enumeration.
6. Image rollback: restore the current API and Worker base image digests. Database rollback via migration downgrade is safe only before any collection run/candidate/event rows exist; afterward, do not drop evidence tables—roll forward or use a separately authorized full backup restore.

No step above was performed against production.

## Production safety and observed background activity

Read-only final production inspection found head 0027, 6,680 Masters, 9,470 SourceOpportunities, 75 aliases, and one published document. Document 1’s hash matches the isolated backup and final pilot. This Phase 2 work issued no production write, migration, source sync, approval, publication, restart, or deployment.

The production snapshot taken at 11:15 UTC had 62,044 SourceObservations; a later read showed 62,123. Read-only `source_sync_jobs` evidence records pre-existing scheduled job 1027 for source 2 succeeding at 11:30 UTC, consistent with that +79 observation change. That scheduled job was not invoked or changed by this work. Production remained live and its existing source schedule was preserved.

## Gate summary

| Gate | Result |
|---|---|
| Reproducible test environment | PASS |
| PostgreSQL concurrency and replay | PASS |
| Deduplication under concurrency | PASS |
| Migration 0028 isolated upgrade/downgrade/up | PASS |
| Pilot metrics reconciled by unit | PASS |
| Retry, recovery, and backoff | PASS |
| Nine candidate decisions recorded | PASS |
| Review API security and RBAC | PASS |
| Publication gates preserved | PASS |
| Document 1 preserved | PASS |
| Durable collection provenance | PASS |
| Exact production baseline integration | PASS |
| Automatic scheduling disabled | PASS |
| Automatic approval/publication disabled | PASS |
| Fresh targeted regression | PASS — 131 passed, 0 skipped |
| API and Worker release candidates validated | PASS |
| Agent-originated production data mutations | ZERO |
| Production deployment | NONE |
| Real-source availability and candidate yield | PARTIAL — 17 un-retried timeouts, 2 source-page 404s, 8 human-review holds, 1 page-only approval candidate |

**Final decision:** `AUTOMATED_DOCUMENT_ENGINE_PHASE_2 = VALIDATED_READY_FOR_DEPLOYMENT_AUTHORIZATION`. This is technical readiness for a separately authorized, disabled-by-default deployment; it does not approve or publish candidate 1, resolve the eight review cases, guarantee Furas availability, activate automation, or authorize production deployment.
