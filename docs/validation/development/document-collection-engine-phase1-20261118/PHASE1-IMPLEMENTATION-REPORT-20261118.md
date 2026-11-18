# Automated Document Collection Engine — Phase 1

**Execution:** 2026-11-18  
**Status:** `ISOLATED_IMPLEMENTATION_VALIDATED`  
**Production deployment:** None  
**Production writes:** Zero  
**Automatic collection schedules:** Off

## Outcome

Implemented an isolated, reusable document collection pipeline and its first complete source adapter for Furas. The pipeline processes only an explicit allowlist of existing `SourceOpportunity` IDs, validates their exact source/Master association, verifies official pages and document URLs, stages evidence in private collection tables, and keeps approval/publication separate. Unsupported sources return `NOT_CONFIGURED`; no synthetic document results are generated.

The real-source pilot completed all 25 explicitly selected existing records, but returned `PARTIAL` because the Furas site was intermittently unreachable and direct attachment routes frequently redirected to a listing page. No pilot candidate was published. The existing published Document 1 was preserved byte-for-byte.

## Implementation and changed files

### New engine and adapter files

- `app/document_collection/__init__.py`
- `app/document_collection/contracts.py`
- `app/document_collection/registry.py`
- `app/document_collection/classification.py`
- `app/document_collection/engine.py`
- `app/document_collection/tasks.py`
- `app/document_collection/verifier.py`
- `app/document_collection/adapters/__init__.py`
- `app/document_collection/adapters/furas.py`

### New persistence, scripts, tests, and fixtures

- `migrations/versions/0028_document_collection_engine.py`
- `scripts/document_collection_pilot.py`
- `scripts/export_document_collection_pilot.py`
- `tests/test_document_collection_engine.py`
- `tests/test_document_collection_verifier.py`
- `tests/test_document_collection_api.py`
- `tests/test_document_collection_tasks.py`
- `tests/fixtures/document_collection/furas_booklet_with_attachment.html`
- `tests/fixtures/document_collection/furas_page_fallback.html`
- `tests/fixtures/document_collection/furas_multiple_documents.html`
- `tests/fixtures/document_collection/furas_empty_documents.html`

### Existing files modified

- `.env.example` — collection feature flag defaults off.
- `app/celery_app.py` — task imports and routing; no Beat schedule was added.
- `app/main.py` — admin collection review and history APIs.
- `app/models.py` — isolated run, candidate, and verification-history models.
- `tests/test_opportunity_documents_migration_postgres.py` — verifies migration 0028 after 0027 and preservation of existing document rows.

Other dirty worktree files predate this task and were not included in the collection-engine change set.

## Architecture and safety behavior

### Adapter contract and source capability

`DocumentAdapter` in `contracts.py` accepts a validated `SourceOpportunityContext` and a bounded `PageCapture`, and returns normalized `DocumentObservation` records. The contract retains provider IDs, original titles, source document IDs, URLs, access/purchase evidence, raw and verified price fields, source payload evidence, and timestamps.

Capability status is explicit for all 14 registered sources:

| Source | Status |
|---|---|
| `furas` | `IMPLEMENTED` |
| `ahda`, `alahsa-opportunities`, `invest-saudi`, `kfu`, `modon`, `mwan`, `ncp`, `nhc`, `pif`, `rcjy-investment-opportunities`, `rcu-investment-opportunities`, `taadeen-mining-bids`, `waha-development` | `NOT_CONFIGURED` |

Furas handles opportunity-specific booklet, draft-contract, application-form, technical/specification, site-plan, drawing, and other attachment evidence. An ambiguous title remains `UNKNOWN_DOCUMENT_TYPE` and requires review. General investor guides are not attached to every opportunity.

### Identity, staging, approval, and deduplication

Collection requires an existing recognized source record, exact provider reference, existing linked non-merged Master, and source-specific adapter. It does not enumerate provider IDs or create/merge Masters or source rows. Source-scoped identity keys, versioning, database uniqueness, and locking protect repeated and concurrent processing. The published booklet ID 1 is checked for duplication and is not rewritten or withdrawn.

Migration 0028 is required for durable collection runs/checkpoints, private candidate staging, evidence hashes/provenance, and verification history. It is a **candidate migration only** in this checkout; it was applied only to the disposable pilot database. The existing `opportunity_documents` model/table and public document API remain the publication surface; collection writes do not insert into that public table.

Candidates default to `PENDING` review and are not returned by the public opportunity-details document route. Admin approval/rejection records a review decision, but this engine does not publish a candidate into `opportunity_documents`; publication remains a separate controlled step. Thus review controls are implemented, while an end-to-end automated publication handoff is intentionally absent.

Price evidence is retained separately from displayable pricing. For Furas, `RFPPRICE` is treated as a booklet amount only when the same page supports the “سعر الكراسة” label and matching value. Currency is never inferred from the country. Without explicit currency evidence, verified amount/currency and public price stay empty.

### URL verification and access classifications

The verifier accepts HTTPS only, checks exact source-approved hosts, rejects credentials and unsafe URL structures, resolves and rejects private/internal addresses, pins the checked IP for the TLS connection, validates certificates, revalidates every redirect, bounds redirects/timeouts/body sizes, and rate-limits requests. It distinguishes PDF signatures from HTML, source-page fallback, login/authentication, payment, listing redirects, temporary failures, 403, and 404. It does not save, proxy, mirror, or rehost files.

Supported access classifications include `PUBLIC_DIRECT_DOWNLOAD`, `OFFICIAL_DOCUMENT_PAGE`, `VERIFIED_BOOKLET_WITH_SOURCE_PAGE_FALLBACK`, `LOGIN_REQUIRED`, `PAYMENT_REQUIRED_FOR_DOCUMENT`, `PURCHASE_REQUIRED_FOR_PARTICIPATION`, `DIRECT_DOWNLOAD_UNAVAILABLE`, `RESTRICTED`, `ACCESS_UNVERIFIED`, and `TEMPORARILY_UNREACHABLE`. Access, participation purchase, verification, and review states are stored separately.

Temporary failures retain last verified values. Repeated confirmed 404s can create a withdrawal proposal after the configured threshold and age; a single failure never removes a candidate or published document.

### Review APIs and task names

Admin-only routes:

- `GET /api/admin/document-collection/capabilities`
- `GET /api/admin/document-collection/candidates`
- `GET /api/admin/document-collection/candidates/{candidate_id}/history`
- `GET /api/admin/document-collection/runs/{run_id}`
- `POST /api/admin/document-collection/candidates/{candidate_id}/approve`
- `POST /api/admin/document-collection/candidates/{candidate_id}/reject`

Celery tasks (explicit invocation only, all gated by `DOCUMENT_COLLECTION_ENABLED=false` by default):

- `app.document_collection.tasks.collect_source_opportunity`
- `app.document_collection.tasks.collect_allowlisted_batch` — explicit 1–25 ID limit.
- `app.document_collection.tasks.refresh_candidate`
- `app.document_collection.tasks.retry_verification`
- `app.document_collection.tasks.summarize_run`

No collection schedule was added to Celery Beat, and the production Worker/Scheduler were not restarted.

## Tests and validation

- Collection engine/verifier/API/task tests: **38 passed** in the focused run.
- Combined collection plus existing platform regression suites: **123 passed, 3 skipped**.
- A dedicated isolated source-alias integration database run subsequently completed: **13 passed**. That resolved the two DB-dependent source-alias skips from the combined run. One unrelated offline replay concurrency test remains skipped because its isolated replay database is not configured.
- PostgreSQL migration regression exercised migration 0027 → 0028 and down/up cycles, preserving existing published document rows.
- Regression coverage included authentication/security, existing Documents MVP, geography/dashboard, exports, identity aliases, Furas quarantine/capture/offline replay, and KFU attachment isolation.

The combined suite’s skips were environment-dependent: two alias integration cases required the dedicated isolated alias database, and one offline replay concurrency case requires a separate isolated replay database. No failed tests were silently ignored.

## Controlled real Furas pilot

The pilot used a read-only production snapshot imported into the isolated PostgreSQL container `doccollection-pilot-pg16-20261118`, database `sharakat_pilot_final`. The runner enforces the exact dedicated database host, an explicit Furas allowlist, and a maximum of 25 existing source IDs. All writes went to the isolated staging tables.

Allowlisted IDs: `3188, 18, 19, 20, 21, 26–45` (25 records; Al-Ahsa selection; 3188 included as the reference case). The pilot did not run source synchronization or national enumeration.

| Measure | Actual result |
|---|---:|
| Existing opportunities requested / processed | 25 / 25 |
| Run outcome | `PARTIAL` |
| Source records completed / temporary failure / not found | 6 / 17 / 2 |
| Document references discovered | 10 |
| Candidates staged | 9 |
| Duplicate prevented against existing document 1 | 1 |
| Candidate category `DRAFT_CONTRACT` / `UNKNOWN_DOCUMENT_TYPE` | 1 / 8 |
| Ready for approval / needs review | 1 / 8 |
| Confirmed direct PDF/booklet downloads | 0 |
| Draft contracts verified as actual file downloads | 0 |
| Verified amounts / verified currencies / public prices | 0 / 0 / 0 |
| Raw price evidence retained | 9 |
| Direct-link outcomes: temporary failure / listing redirect | 6 / 3 |

The one ready candidate is a draft-contract source-page fallback; the direct asset was temporarily unavailable, so it is not a confirmed downloaded contract. One booklet observation matched the already published Document 1 and was deduplicated. Eight ambiguous references remain pending review. No candidate was approved or published.

Candidate SourceOpportunity IDs: `3188, 41, 42, 43, 44, 45`.  
Linked Master IDs: `597, 41, 42, 43, 44, 45`.

Artifacts:

- `real-furas-allowlist.json`
- `real-furas-reference-3188-allowlist.json`
- `candidate-review-register.csv`
- `source-opportunity-outcomes.csv`
- `real-furas-pilot-summary.json`
- `real-furas-pilot-candidates.json`

The final review database remains in the isolated container with no published host port and no attached Worker/Beat. Two superseded pilot databases and temporary snapshot dump files were removed after the final run.

### Published Document 1 and KFU provenance

The production database was queried read-only. Production and isolated snapshot each contained exactly one `opportunity_documents` row. Document 1’s content hash matched in both:

`2c46ba8597e8179dd956043257beb04799099253959c517b5756fcef5c6f59c2`

For KFU SourceOpportunity 2928, read-only inspection found zero current derived attachments and no `attachment_provenance_review` marker on the current row. Four historical SourceObservation records remain, including the removed guide/booklet references; current source content items still retain source-level listing URLs. A later markerless collection snapshot is consistent with mutable source metadata replacement, but the evidence does not establish a specific sync job as the cause. No KFU data was changed. The new engine retains evidence/history in separate durable candidate and verification-event tables instead of relying on mutable `raw_data` markers.

## Reproducibility and isolated execution

The allowlist runner is `scripts/document_collection_pilot.py`; the exporter is `scripts/export_document_collection_pilot.py`. Both refuse to operate unless `DOCUMENT_COLLECTION_ISOLATED=1` and `DATABASE_URL` points to the dedicated host `doccollection-pilot-pg16-20261118`. They do not accept a production host. Example invocation from the project root, with the isolated database URL supplied only through the local environment:

```powershell
$env:DOCUMENT_COLLECTION_ISOLATED = '1'
$env:DOCUMENT_COLLECTION_ENABLED = 'true'
$env:DATABASE_URL = '<isolated-only database URL for doccollection-pilot-pg16-20261118/sharakat_pilot_final>'
python scripts/document_collection_pilot.py docs/validation/development/document-collection-engine-phase1-20261118/real-furas-allowlist.json
python scripts/export_document_collection_pilot.py 1 docs/validation/development/document-collection-engine-phase1-20261118/real-furas-allowlist.json docs/validation/development/document-collection-engine-phase1-20261118
```

The host’s current `python` command resolves only to the Windows Store execution alias, so the commands above require the configured project Python environment. The implementation and pilot artifacts were produced in the isolated execution environment described above.

## Deployment requirements and remaining blockers

Before any future deployment, review and separately authorize migration 0028, build an isolated release candidate directly from the official project directory recorded in `docs/development/SINGLE-SOURCE-OF-TRUTH.md`, validate it against the supported Python/PostgreSQL production versions, and deploy the API and Worker only under separate authorization. Keep collection feature flags disabled until a controlled runtime review is complete. Do not add a Beat schedule until rate limits, monitoring, retention, and source-specific operational approval are defined. Furas direct-file access reliability and eight ambiguous candidate classifications remain pilot-review blockers. The 13 other sources still require adapters. The former feature worktree referenced when this report was written is retired; see the 2026-11-18 consolidation report.

Production remained at migration 0027; no production deployment, migration, document insertion/publication, service restart, source synchronization, Furas enumeration/removal, or business-data mutation occurred.

## Gate summary

| Gate | Result |
|---|---|
| Core engine, adapter contract, Furas adapter | `PASS` (isolated implementation) |
| Exact identity and classification | `PASS` |
| Safe URL verification and private staging | `PASS` |
| Deduplication, retry/resume, refresh/history | `PASS` |
| Admin review endpoints and publication isolation | `PASS` |
| Focused and platform regression | `PASS` with environment-dependent skips noted above |
| Real-source Furas pilot | `PARTIAL` (actual counts above) |
| Published Document 1 preservation | `PASS` |
| Production data mutations | `ZERO` |
| Production deployment | `NONE` |

**Final decision:** `AUTOMATED_DOCUMENT_ENGINE_PHASE_1 = ISOLATED_IMPLEMENTATION_VALIDATED`. Real-source readiness is `PARTIAL`; keep automatic collection disabled and do not deploy until the isolated candidate is reviewed and the Furas access/review findings are resolved.
