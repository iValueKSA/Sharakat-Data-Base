# Main Project Consolidation Acceptance

Date: 2026-11-18

## Decision

`MAIN_PROJECT_SINGLE_SOURCE_OF_TRUTH = ESTABLISHED_AND_VERIFIED`

The official project directory is now the only development source of truth:

`C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`

The previous worktree is retained temporarily as recovery evidence and is retired from development use:

`C:\Users\QusaiAbdElhalim\.codex\worktrees\opportunity-documents-mvp\Sharakat-Data-Base`

## Recovery checkpoint and preservation

- The official checkout was clean before consolidation, on `main` at `4be09c5d876132428e83f1e7cfc0a031e1bf2b88`.
- A Git bundle checkpoint was verified before edits: `%TEMP%\Sharakat-Data-Base-pre-consolidation-20261118.bundle` (SHA-256 `D9C211F615D7AB048E8A36F6222A965C1CAB9ECEACC64CC6DF048A17CA18E26D`).
- The old worktree was not reset, cleaned, moved, or deleted. Its uncommitted files remain available for recovery until separately retired.
- The worktree contained deletion-only changes for previously accepted audit artifacts. Those deletions were not carried over, so the corresponding official-project files remain present.
- The official checkout had no pre-existing uncommitted user changes to preserve. Environment files and credentials were not copied or replaced.

## Files reconciled

Compared the worktree against the official project by file path and SHA-256. Copied 145 new files and updated 13 existing files; verified 0 post-copy hash mismatches.

The 13 updated files were `.env.example`, `app/adapters.py`, `app/celery_app.py`, `app/main.py`, `app/models.py`, `app/static/app.js`, `app/static/ui-theme.css`, `docs/design/data-dashboard-metric-dictionary.md`, `tests/test_data_dashboard.py`, `tests/test_data_quality.py`, `tests/test_furas_offline_replay.py`, `tests/test_nationwide_expansion_safety.py`, and `tests/test_wave3_adapters.py`.

The new files include the Documents MVP and collection-engine source, migrations 0027/0028, Furas adapter and staging/review/task code, KFU and document fixtures, regression tests, pilot/export scripts, UI screenshots, validation reports, rollback and deployment plans, and release artifacts/manifests.

The README now points developers to `docs/development/SINGLE-SOURCE-OF-TRUTH.md`, which records the canonical root, retired worktree, and runtime separation rule. Historical MVP/KFU release notes and Phase 1 deployment instructions were amended to direct future builds to the official root and state that historical candidate records do not authorize deployment.

## Deployed-image reconciliation

Read-only inspection of the running image contents established:

- The running API contains `app/documents.py` and migration `0027_opportunity_documents_mvp.py`; these files are now in the official source tree with matching SHA-256 hashes.
- The running frontend's `static/app.js` and `static/ui-theme.css` exactly matched the consolidated source hashes.
- The running Worker adapter contained the deployed KFU parser correction and matched the consolidated adapter source (`2026.11.16-kfu-2`). The official API baseline had not contained this correction before consolidation.
- The official source now includes the newer document-collection routes/tasks and migration 0028, which are source candidates and were not deployed by this task.
- Production API and Worker images are image-baked. Their only project-host bind mount is the backup directory; frontend and scheduler have no host source mount. Source edits therefore did not modify or reload running service code.

## Build and regression validation

- API image built successfully from the official root as `sharakat-main-consolidation-20261118-api`; image ID `sha256:315bfd043817d6ba9a7cbcbeb96fc68ebf3c9a5d3427aeb01f8fa00e2df7c2c8`.
- Frontend image built successfully from the official root as `sharakat-main-consolidation-20261118-frontend`; image ID `sha256:bc15686b147e21dce900652a0d45f299779a6157d589d2df8783524243426183`.
- Alembic source head: `0028_document_collection_engine`.
- The Phase 2 regression suite ran with the official root mounted read-only into an isolated test container. Final result: **131 passed, 0 skipped**.
- The first run encountered stale fixture rows in the isolated `furas_alias_test` database (2 failures, 129 passes). After verifying the configured host and database were `documents-mvp-pg-test` / `furas_alias_test` on the isolated test network, only that disposable test schema was reset and recreated from official source metadata. The clean rerun passed all 131 tests.
- `docker compose config --quiet` could not resolve required deployment environment values because this checkout has no configured deployment environment file. No credentials were created or injected. The API and frontend Dockerfile builds and the isolated test suite passed.

## Production safety evidence

- A read-only database query returned production Alembic head `0027_opportunity_documents_mvp`; 0028 remains unapplied.
- Production services remained running: API healthy; frontend, Worker, scheduler, PostgreSQL, and Redis up.
- No production image was replaced; no container was restarted; no migration, source synchronization, or application API mutation was executed.
- No database, source identity, published document, source schedule, Furas quarantine/feature flag, or RCU setting was changed.

## Final status

| Field | Result |
|---|---|
| `MAIN_PROJECT_CONSOLIDATION_STATUS` | `COMPLETE` |
| `OFFICIAL_PROJECT_ROOT` | `C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base` |
| `FILES_CONSOLIDATED` | `145 added; 13 updated; 0 hash mismatches` |
| `AUTOMATED_DOCUMENT_ENGINE_IN_MAIN_PROJECT` | `YES` |
| `MIGRATION_0028_IN_MAIN_PROJECT` | `YES — source only, unapplied in production` |
| `REGRESSION_TEST_RESULTS` | `131 passed, 0 skipped` |
| `MAIN_PROJECT_BUILD_STATUS` | `API and frontend image builds PASS; Compose interpolation requires deployment environment values` |
| `OLD_WORKTREE_STATUS` | `RETIRED; retained temporarily; not deleted` |
| `PRODUCTION_DATA_MUTATIONS` | `NONE` |
| `PRODUCTION_DEPLOYMENT_STATUS` | `NOT DEPLOYED` |
| `FINAL_DECISION` | `MAIN_PROJECT_SINGLE_SOURCE_OF_TRUTH = ESTABLISHED_AND_VERIFIED` |
