# KFU collector release candidate

Status: `ISOLATED_CANDIDATE_NOT_DEPLOYED`.

This is the historical candidate worker overlay record. Its `app/adapters.py` source (SHA-256 `e64519ebe36c193a8446a413f8a31137dada6d306924c9003c90e208ef0023bc`) has been consolidated into the official project directory. The former isolated worktree is retired; future builds and release preparation must use the official root described in `docs/development/SINGLE-SOURCE-OF-TRUTH.md`. KFU parser version: `2026.11.16-kfu-2`. This record does not authorize a deployment.

Candidate tag: `alahsa-local-worker:kfu-provenance-candidate-20261116`. Candidate image ID and manifest digest: `sha256:b8191dd075d7fe4cc7ec2542cfefe5bdc46f9a634dfe5c5cf338ed4b4d46c08a`. See `manifest.json` for machine-readable provenance and test results.

Only the Celery Worker executes `sync_source` and the KFU adapter. Celery Beat (`alahsa-local-scheduler-1`) enqueues due sources every minute; it is unchanged. The API only enqueues manual sync requests. A future deployment would recreate only the Worker service. API, scheduler, frontend, PostgreSQL, Redis, Documents MVP, migrations, and schedules are outside this release.

The production database is at migration `0027_opportunity_documents_mvp`; the worker change uses no new database schema. A verified production backup was restored into a private disposable PostgreSQL instance for the metadata dry run. The backup predates migration 0027, but the exact six KFU source rows compared equal to the live production rows by raw payload hash, content hash, provider identity, Master link, parser version, status, and last-seen time. The production migration itself was not rerun or changed.

The candidate corrects notice-panel extraction, separates forms from document links, keeps page-wide material at listing scope, avoids invented notice URLs, and fails closed for ambiguous duplicate-title or cross-panel associations. It preserves the existing URL-plus-normalized-title provider identity formula. Test evidence: 104 passed and 2 optional alias database tests skipped in the worker runtime; KFU-specific subset 36 passed; API Documents MVP and PostgreSQL migration gates 7 passed on a separate disposable database.

Before any deployment, obtain separate authorization for collector deployment and for any historical metadata correction. Then take and verify a fresh backup, recheck the worker digest and KFU queue, deploy the candidate Worker only, and allow one normal scheduled KFU collection. Do not trigger a manual sync. Verify the six record identities/Master links and listing provenance after that run. Reassess whether the one-row 2928 historical correction is still needed; the collector may already have corrected its current derived metadata. Do not clear or reassign the nine held references. The 2773 guide may move from item-level derived metadata to listing provenance on a successful collection; its source page evidence must remain preserved.

The current KFU source is enabled at a 720-minute interval; the last successful collection was `2026-11-16 06:35:30 UTC`, so the next due time is approximately `18:35 UTC` if normal scheduling remains unchanged. No schedule or service was changed in this preparation. The previous worker image is available as the immediate runtime rollback target before a collection. After a corrected collection, image rollback alone would not restore changed row metadata and could reintroduce shared links on a later run; any post-sync rollback requires a reviewed field-level recovery plan.

No deployment, schedule change, collection, metadata correction, document publication, or production mutation was performed while preparing this candidate.
