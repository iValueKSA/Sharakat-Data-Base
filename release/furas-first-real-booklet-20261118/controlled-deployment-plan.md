# Furas first booklet — controlled deployment and rollback plan

**Prepared:** 2026-11-18 UTC  
**State:** preparation only; nothing in this document was applied to production.

## Preconditions

1. Obtain separate authorization for deployment and for publication of this individual record.
2. In a normal browser, verify the exact Furas page, its current lifecycle, date labels, booklet entry, purchase action and actual link destinations. If expired, keep the record historical and do not approve it.
3. Do not infer a currency for the displayed `1500`; the seed keeps amount and currency NULL.
4. Take a fresh verified production backup. Confirm the live API/frontend image digests and production Alembic head still match the baselines in the acceptance report. Stop if they differ.
5. Verify the exact identity chain again: Furas SourceOpportunity `3188` / provider reference `01-26-017001-42008` / non-merged Master `597`.

## Controlled sequence after separate authorization

1. If production is still at `0026_source_identity_aliases`, apply migration `0027_opportunity_documents_mvp` once using the approved migration procedure. Verify the head and constraints. Do not downgrade as part of ordinary rollback.
2. Run `production-seed-draft.sql` in one transaction. It inserts one DRAFT record only, uses an exact source/Master guard and a source-scoped unique key, and verifies its own result. Repeat execution is idempotent.
3. Run `production-verify-record.sql`. Confirm the exact provider ID, Master and source links, official page URL, null price/currency, and DRAFT state. DRAFT records are not returned to public API clients.
4. Following successful browser review and a separate explicit record-level publication approval, change only this row from DRAFT to APPROVED through the authorized publication workflow. Do not include a price or purchase URL unless separately verified.
5. Deploy API image `opportunity-documents-mvp-api:furas-booklet-20261118` and frontend image `opportunity-documents-mvp-frontend:furas-booklet-20261118` as one controlled frontend/API release. Leave PostgreSQL data except the authorized migration and one document row, Redis, Worker, Scheduler/Beat, source schedules, and source settings unchanged. Do not synchronize Furas.
6. Verify readiness, anonymous opportunity detail response, authenticated behavior, published document JSON, page-only label/link, hidden price, and no failed attachment URL. Perform human desktop and mobile acceptance before closing release acceptance.

## Rollback

- Restore the API to `alahsa-local-api@sha256:be0e5ac43f9030bbcf441c4a3e96b08fcad3c1ea1bfe1977d5eedd31ab123ba4` and the frontend to `alahsa-local-frontend@sha256:defb9fd08a2cedda79ba23d8bbf64a3a4420952dc004b52976e1d634173bdcd5`. These are the inspected current production image baselines; reconfirm them immediately before any future rollback.
- Keep additive migration 0027 in place during image rollback. Do not downgrade without a new backup and proof that no document metadata would be lost.
- If the row is still DRAFT and has never been public, `production-rollback-draft.sql` removes exactly that DRAFT row and errors unless exactly one row matches.
- If the row was ever APPROVED/public, preserve its evidence and set only its publication status to REVOKED through the authorized workflow. Do not delete the public record as a rollback shortcut.

## Prepared SQL artifacts

- `production-seed-draft.sql` — guarded, idempotent DRAFT insertion; not executed on production.
- `production-verify-record.sql` — read-only exact-record verification.
- `production-rollback-draft.sql` — exact-target DRAFT removal only; tested on a disposable database.
