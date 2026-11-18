# Opportunity Documents MVP — Isolated Implementation Report

> Historical implementation record. The source-reconciliation instructions below were superseded on 2026-11-18: accepted implementation is already consolidated in the official project directory. Use `docs/development/SINGLE-SOURCE-OF-TRUTH.md` for all future work; do not transplant files from the retired worktree.

**Date:** 2026-11-15  
**Status:** `OPPORTUNITY_DOCUMENTS_MVP = ISOLATED_IMPLEMENTATION_VALIDATED`  
**Deployment:** Not performed

## Workspace and production baseline

- Isolated worktree: `C:\Users\QusaiAbdElhalim\.codex\worktrees\opportunity-documents-mvp\Sharakat-Data-Base`
- Branch: `feature/opportunity-documents-mvp-20261115`
- Starting commit: `4c4515ee0e1bb78a6649c134e6dea7f29afa51b9`
- Running API image ID: `sha256:0063b9161c8529d882e8bec878b17fee78c73d63a70a207f24c915c47eb036ca`
- API `app/main.py` SHA-256 before feature changes: `0fd75cc67b6d5a96f9f88c2b51016f380cd21ad93a2360f416d4895930843ef6`
- Running frontend dashboard asset `data-dashboard.js` SHA-256: `bbc7845b4d66de2096b5b00981a60b661a9642324110b4553d3fb246abd7cb06`; the isolated checkout retains the matching file.
- Read-only production migration head: `0026_source_identity_aliases`. Candidate head is `0027_opportunity_documents_mvp`.

The implementation worktree did not touch the OneDrive runtime checkout or running containers. It began from the running API asset and deployed frontend dashboard asset. The dirty local XLSX write-only/export-storage implementation was not carried into this branch because it is absent from the running API image. For later integration, transplant the document-specific additions into the current approved API candidate; do not replace the current `app/main.py` wholesale. Preserve the existing geographic metrics, dashboard, governorate selector, map and any separately reviewed local changes.

## Implementation

### Database model and migration

The existing `opportunity_documents` table is extended rather than replaced. Migration `0027_opportunity_documents_mvp` adds SourceOpportunity provenance, official document and source-page identifiers, document category, separate access and rights statuses, authentication and document-payment flags, participation purchase status, purchase URL verification, price/currency, link verification timestamp, provenance JSON, version/deduplication identity, publication approval state and created/updated timestamps.

The migration adds a composite source-namespace foreign key, supersedes-document foreign key, lookup indexes, source-scoped version uniqueness and publication/access/price constraints. Existing legacy rows receive conservative defaults (`DRAFT`, `UNKNOWN`, `UNVERIFIED`) and remain stored. A direct public download cannot be approved without a verified exact source association, verified public link, confirmed no-login/no-document-payment state and direct-link rights approval. Unknown, restricted and unverified records cannot pass the public gate.

### API and identity behavior

Documents are returned with the existing read-only `GET /api/opportunities/{opportunity_id}` detail response as `documents` and safe `document_source_pages`. The API joins documents to the exact SourceOpportunity and source namespace, then checks that the linked SourceOpportunity still points to the requested Master. No title matching or direct Master reassignment is used. The API suppresses unapproved, unknown-access, restricted, rights-unverified, cross-Master, wrong-source-page and unsafe-link rows. It emits only the latest approved version per source-scoped document identity. With no approved records it returns an empty document array and safe official source-page fallbacks.

No document-write, download-proxy, payment or source-sync endpoint was added. Existing API authentication and RBAC code was not changed.

### Frontend

The opportunity details modal now includes **مستندات الفرصة الاستثمارية**. It shows source, category, verification date, verified price and access/participation conditions separately. A public booklet that must be purchased for bidding displays both **تحميل الكراسة** and **يلزم شراء الكراسة للتقديم على المنافسة**. A purchase action appears only with a verified official purchase destination; no in-platform payment is implied. Login- and payment-gated items link to their approved official source page, never a direct private document URL. Unknown prices are omitted. No approved document produces the requested Arabic empty state and an official opportunity-page fallback when safe.

All document text is HTML-escaped. External links are limited to HTTP(S), reject private/local hosts, non-default ports, user credentials and credential-like query or fragment parameters, and use `noopener noreferrer` with `no-referrer`. CSS follows the existing dark RTL detail modal; Ahda Text and the rest of the frontend are retained.

### Synthetic fixtures

`tests/fixtures/opportunity_documents/scenarios.json` contains 12 explicitly synthetic scenarios covering all 14 requested fixture conditions, including public download, purchase for participation, login, document-payment, restricted/confidential, unverified rights, empty, multiple documents, multiple source records for one Master, duplicate version, cross-Master conflict, unsafe URL, unapproved status and unknown price. All fixture domains use `example.invalid`; no real document URL or opportunity data is included.

## Validation results

### Database, API and security

- PostgreSQL 16 disposable container only; no persistent volume and removed after the test run.
- `tests/test_opportunity_documents.py`, `tests/test_opportunity_documents_migration_postgres.py`, and `tests/test_production_security.py`: **24 passed** on the final code.
- Migration upgrade from 0026, preservation of a legacy row, source namespace FK, publication gate, source-scoped uniqueness, downgrade preservation and re-upgrade: **passed**.
- API cases: exact Master/SourceOpportunity association, multiple rows/sources, latest-version deduplication, hidden unapproved/restricted/unknown/unsafe/cross-Master records, login and document-payment separation, participation purchase and verified price: **passed**.
- `node --check app/static/app.js` and `node --check app/static/data-dashboard.js`: **passed**.
- `git diff --check`: **passed**.

### Focused platform regression

Selected platform regressions covering production security/authentication, opportunity search/detail compatibility, geography, map payload metrics, dashboard metrics, filter canonicalization and lifecycle: **51 passed, 1 deselected**.

The excluded test is `test_exports_batch_geography_and_source_locations_without_changing_export_values`. It specifically expects the dirty-checkout-only XLSX write-only helper, which is not present in the verified running API image. The implementation did not import that unapproved XLSX change. One geography test assertion was aligned to the already deployed response contract by including `truly_missing_coordinates` and `coordinates_present_but_not_map_eligible`; no geography runtime logic was changed.

### Fresh-context Playwright browser preview

An isolated static frontend was served locally in a fresh headless Playwright context; all `/api/**` traffic was synthetic and authentication returned 401. No live administrator profile, real opportunity, or real document URL was used.

- Approved synthetic documents rendered with separate access and participation labels and a verified SAR 300 fixture price.
- Login-required, document-payment and official purchase actions rendered as source-page links.
- Empty document state and official source fallback rendered.
- Desktop and 390 px mobile layouts had no horizontal overflow.
- Unsafe schemes, loopback/private hosts, non-default ports, signed-token/API-key query or fragment links were rejected.
- Browser JavaScript errors: **0**; unexpected API calls: **0**; failed requests: **0**; auth cookies: **0**.

Screenshots:

- `docs/validation/ui-redesign/opportunity-documents-mvp-section-desktop.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-section-mobile.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-empty-state-section.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-synthetic-approved.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-empty-state.png`

## Changed files

- `app/models.py`
- `app/documents.py` (new)
- `app/main.py`
- `app/static/app.js`
- `app/static/ui-theme.css`
- `migrations/versions/0027_opportunity_documents_mvp.py` (new)
- `tests/fixtures/opportunity_documents/scenarios.json` (new)
- `tests/test_opportunity_documents.py` (new)
- `tests/test_opportunity_documents_migration_postgres.py` (new)
- `tests/helpers/opportunity_documents_browser.py` (new)
- `tests/test_data_dashboard.py` (assertion aligned to deployed geography metric response)
- Synthetic screenshots listed above

`app/static/data-dashboard.js` is retained as the deployed frontend baseline and was not changed by the Documents feature.

## Production safety and decision

- Approved real documents imported: **0**
- Real documents published: **0**
- Production data mutations: **0**
- Production migrations: **0** (live database remains at 0026)
- Production deployments/restarts: **0**
- Source synchronization or Furas/RCU scheduling changes: **0**

**Decision:** `ISOLATED_IMPLEMENTATION_VALIDATED`. The feature works with zero approved real documents and correctly displays the empty state. Production rollout is not performed. Real document publication remains blocked until exact source association, access and linking rights are approved per record.

## Recommended deployment sequence and rollback

1. Review this branch and integrate only the Documents changes onto the current approved runtime candidate, retaining any independently reviewed local changes.
2. Take and verify a production database backup; separately authorize the migration.
3. Apply migration 0027 before deploying the API that selects its new columns; then deploy the API and frontend assets.
4. Verify the empty state and publication gates in the protected environment. Import no real seed until it receives separate record-level authorization.
5. For rollback, restore frontend/API assets to their prior versions. Downgrade 0027 only after backing up any new document metadata; the downgrade removes the added columns. No new document rows were created in this task.
