# Opportunity Documents MVP — Production Baseline Integration Readiness

**Date:** 2026-11-16  
**Decision:** `OPPORTUNITY_DOCUMENTS_MVP = PRODUCTION_INTEGRATION_VALIDATED`  
**Production migration / deployment / data changes:** Not performed

## Acceptance gates

| Gate | Result | Evidence |
|---|---|---|
| `PRODUCTION_BASELINE_RECONCILED` | PASS | Live API/frontend image IDs and hashes captured; production Alembic head read-only verified as `0026_source_identity_aliases`. |
| `DOCUMENTS_CHANGE_SET_ISOLATED` | PASS | Two focused Docker build contexts copy only the listed API and frontend assets onto the pinned production image digests. |
| `XLSX_EXPORT_REGRESSION` | PASS | Previously omitted test now runs and passes; full XLSX generated from the restored database copy. |
| `MIGRATION_0027_ISOLATED` | PASS | Upgrade, downgrade and re-upgrade verified on a disposable restore of the successful 2026-11-16 backup. |
| `API_COMPATIBILITY` | PASS | Existing detail fields preserved before and after migration; empty documents list returned after migration. |
| `SECURITY_REGRESSION` | PASS | 59-test focused suite includes production security/RBAC and document publication controls. |
| `DOCUMENT_PUBLICATION_GATE` | PASS | Exact source association, source namespace, current Master linkage, publication status, rights/access and safe URL checks pass. |
| `FRONTEND_REGRESSION` | PASS | Production dashboard/geography scripts retained; document UI appears only when approved documents are returned. |
| `BROWSER_ACCEPTANCE` | PASS | Fresh Playwright context against the built candidate Nginx image; synthetic API responses only. |
| `RELEASE_CANDIDATE_VALIDATED` | PASS | Both isolated images built and exercised; image IDs recorded below. |
| `ROLLBACK_PLAN_DOCUMENTED` | PASS | Image rollback and migration downgrade limits documented below. |
| `PRODUCTION_DATA_MUTATIONS` | ZERO | Only a read-only live inspection and operations on disposable database/container resources occurred. |
| `PRODUCTION_DEPLOYMENT` | NOT PERFORMED | No live container/configuration change, database write or migration, or service restart occurred. |

## Production baseline and reconciliation

- Live API image: `alahsa-local-api@sha256:0063b9161c8529d882e8bec878b17fee78c73d63a70a207f24c915c47eb036ca`.
- Live frontend image: `alahsa-local-frontend@sha256:24835b8fde13d543348b70e9655754caae5e6fe183072dddfee3425712335a31`.
- Production database head: `0026_source_identity_aliases` (read-only `alembic current`).
- Live API file hashes: `main.py` `0fd75cc67b6d5a96f9f88c2b51016f380cd21ad93a2360f416d4895930843ef6`; `models.py` `66a5a8331066786e9c2b9c90400d6b3ca5333770a0a5a965f9ea45006b24b691`; `excel_export.py` `f434e1ce74349a015078ea6358813f78114db3e7fd609055954688579dd4f3cf`. The production image has no `app/export_storage.py` and its XLSX route does not import or call `build_opportunities_workbook_write_only`.
- Live document baseline: `opportunity_documents` exists with **0 rows**. Read-only production counts: 6,680 Master rows and 9,470 SourceOpportunity rows.
- Authentication/RBAC module remains inherited unchanged from the API baseline: `app/security.py` SHA-256 `3d4f6b3074c9296f028a8be04b005ddffd0f5030c77edd546603ef8ef7cdbb29`.
- Geographic dashboard and selector assets are unchanged from the live frontend: `data-dashboard.js` `bbc7845b4d66de2096a5b00981a60b661a9642324110b4553d3fb246abd7cb06`; `national-geography.js` `0aacc95241636c6e0689125a8a6e4be71a53b0819bd09a77b5be72ffbfe09b25`; `ui-interactions.js` `6046cb41db4067d014dfa19cacae960d833b975dc0765b81a1ad0a7d8521d4a6`.

The deselected XLSX test exposed an integration gap: the tested Documents branch's `main.py` still used the in-memory export route and did not import the available write-only workbook builder. The production image also lacked the bounded scratch-file module. The release candidate takes only the accepted write-only route and its imports from the clean source baseline, and includes `excel_export.py` plus `export_storage.py`. The geographic implementation, authentication, scheduler, and source processing were not copied from the dirty OneDrive checkout.

The live UI baseline's `app.js` hash is `0f6b6b83170abacb85b51874f21584dc909b996f8af2f48096db1940d2a7eabc`; `ui-theme.css` is `3d67e2119556fa603f96de8a43aa76e8d4e80b0396ecdb8bebdad155438cc22a`. The candidate adds only the document details UI and its styles to those assets. The Ahda Text font, Arabic RTL, dark theme, opportunity detail fields, map, selectors, dashboard, and existing navigation are preserved.

## XLSX regression

The previously deselected `test_exports_batch_geography_and_source_locations_without_changing_export_values` now passes against the integrated candidate. The applicable CSV, XLSX, search/detail and storage tests pass as part of the 59-test run.

The candidate also generated the full workbook from the restored database copy: HTTP 200, XLSX MIME type, 1,603,514 bytes, worksheet `الفرص الاستثمارية` with 6,665 rows and 32 columns, and `معلومات التقرير`. The request-specific scratch directory was removed after response completion. The existing CSV route and export filter/column contract were retained.

## Migration 0027 on a disposable restored database

Restore source: `20261116T062832Z-902f6a17.dump`; metadata status `SUCCESS`; size 67,109,149 bytes; recorded and independently checked SHA-256 `2d1512e6c9db48d7f492921b8bc38d617c7eaea5eb32daabfcd91b74ed068fdc`.

The dump was mounted read-only and restored into the throwaway `documents-mvp-pg-test` database. Before migration it reported head `0026_source_identity_aliases`, 6,680 Masters, 9,470 SourceOpportunity rows, and an existing `opportunity_documents` table with 0 rows. Upgrade reached `0027_opportunity_documents_mvp`; all Master/source counts and the empty legacy document table were preserved. The migration added the source namespace and supersedes foreign keys, ten checks, and the source/status/deduplication indexes. The focused migration test also verified multiple document rows, source-scoped uniqueness and rejection of unsafe publication states.

Downgrade to `0026_source_identity_aliases` and re-upgrade both passed on the disposable restore. Downgrade preserves the legacy table and its original columns, but drops the new provenance/publication columns, checks, foreign keys, and indexes. It would discard metadata for any rows created after 0027; therefore a future rollback must restore old API/frontend images first and leave the additive schema in place unless a fresh backup and a verified no-new-document condition authorize downgrade. The disposable clone was removed after validation.

The base application detail function returned its existing fields before migration. The candidate returned those same fields after migration plus `documents: []`; it returned no synthetic or imported document records. Production remains at 0026.

## Feature visibility and publication safety

- Production document rows remain zero; test fixtures and `example.invalid` links are absent from the candidate image.
- The API exposes only approved records that pass the exact source/Master and publication checks. Unknown or restricted access, unverified rights, unsafe destinations, unapproved status, and cross-Master associations are excluded.
- The frontend now returns no documents panel when the API returns no approved documents. It does not show a misleading empty panel or document download button. Verified records can be displayed later using the current schema; no live feature setting was changed.
- No real document was imported or published. Any future public approval remains record-specific.

## Validation evidence

The integrated candidate test run completed with **59 passed** and 5 non-failing dependency/configuration deprecation warnings. It covered the Documents API/model, migration guard, export storage, the formerly deselected XLSX test, production security, opportunity search/details, geographic dashboard and summary, location geography, canonical filters, and lifecycle behavior.

Playwright used the built frontend image at `http://candidate-frontend:8080/` on an isolated Docker network. All API responses were synthetic; the browser context had no authentication cookies. Desktop and 390 px mobile layouts passed, RTL and Ahda Text checks passed, safe link attributes and URL validation passed, and browser errors, unexpected API calls, and failed requests were all zero. An opportunity with no approved documents showed no documents section. Test screenshots:

- `docs/validation/ui-redesign/opportunity-documents-mvp-synthetic-approved.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-section-desktop.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-section-mobile.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-mobile.png`
- `docs/validation/ui-redesign/opportunity-documents-mvp-empty-state.png` (no-document section hidden)

`git diff --check` passed. Candidate Python modules were imported by the passing suite. A direct `compileall` invocation could not write bytecode into the root-owned migration directory in the candidate image; it made no source changes. The candidate source syntax was exercised by the API, migration, export, and test runs.

## Release candidate images and source package

Built from the exact production base digests above using the focused contexts under `release/opportunity-documents-mvp-20261116/`:

- API: `opportunity-documents-mvp-api:candidate-20261116`; image ID `sha256:be0e5ac43f9030bbcf441c4a3e96b08fcad3c1ea1bfe1977d5eedd31ab123ba4`.
- Frontend: `opportunity-documents-mvp-frontend:candidate-20261116`; image ID `sha256:defb9fd08a2cedda79ba23d8bbf64a3a4420952dc004b52976e1d634173bdcd5`.
- Migration SHA-256: `45ba8ccf04089bb7472b31cc45e0aac4204a5a2bce5660413f6bfe93a85db257`.
- API source hash manifest: `main.py` `866d1c43fb9c15b1ba37add8d63e2b686c1a80e0a12165e50c12bdcd62ba686a`; `models.py` `3b9f7a03eed9830e406b6410e89309e869a4ca17cd94567c9e22ffa8a5cb4009`; `documents.py` `31136a0396d009f2ef8eee97b6e6f2ef4f5c66bea26d00e7da638108c800d69c`; `excel_export.py` `f4711093702d7f99e27cbe24d1cead9d931af63b8d6a7af0b33325679cd21451`; `export_storage.py` `5dda7396a24e35f16ee469d31c058719a7d95d52e1c366ababea08c9f2cb2d2e`.
- Frontend source hash manifest: `app.js` `433ac5a1f5f1cc547ec0da475c5cee19b91dcca1e59c40a4c50d80717ec27340`; `ui-theme.css` `68c7c6042c137cf743e5d6479882f3d71f4a9ed59cd36bc76d603abe55d66e4c`.

The API context contains only the selected runtime overlays and migration; the frontend context contains only the two updated static assets. Test fixtures were not included.

## Future controlled deployment sequence

1. At deployment time, create and verify a fresh production backup and checksum. Confirm live API/frontend base image IDs and Alembic head still match this report; otherwise stop and reconcile.
2. Restore that backup into a new isolated PostgreSQL database and rerun migration 0027 upgrade, compatibility checks and the export/security regression suite.
3. Run the migration job once using the candidate API image; verify head `0027_opportunity_documents_mvp`, document table/indexes/constraints, and unchanged Master/source counts.
4. Replace only the API service with the candidate API image. Verify readiness, anonymous and authorized behavior, opportunity details, zero-document visibility, dashboard/map routes and CSV/XLSX exports.
5. Replace only the frontend service with the candidate frontend image. Verify RTL/font, opportunity details and no-document behavior. Keep Worker, Beat, database, Redis, source schedules and all feature configuration unchanged.
6. If needed, restore the API/frontend baseline image digests above. Keep the additive 0027 schema in place during image rollback. A schema downgrade needs a separate backup and proof that no document metadata would be lost.

This sequence was documented only; no deployment command was run.

## Final status

`OPPORTUNITY_DOCUMENTS_MVP = PRODUCTION_INTEGRATION_VALIDATED`  
`PRODUCTION_DATA_MUTATIONS = ZERO`  
`PRODUCTION_DEPLOYMENT = NOT_PERFORMED`

The candidate is ready for a separately authorized deployment decision. Public document availability remains empty until individually verified records receive publication approval.
