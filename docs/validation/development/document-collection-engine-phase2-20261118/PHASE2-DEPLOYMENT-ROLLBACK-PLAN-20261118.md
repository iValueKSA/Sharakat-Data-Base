# Automated Document Collection Engine — Deployment and Rollback Plan

**Status:** Prepared only; not executed. Production remains at migration 0027 with current services/images.

## Exact baseline and artifacts

- Current API image: `opportunity-documents-mvp-api:furas-booklet-20261118` — `sha256:1eab3bfeded9a77af3520051eefdd287bd7a4c10b2bc8261fcdb789b77669825`.
- Current Worker image: `alahsa-local-worker` — `sha256:b8191dd075d7fe4cc7ec2542cfefe5bdc46f9a634dfe5c5cf338ed4b4d46c08a`.
- Current schema head: `0027_opportunity_documents_mvp`.
- Required additive migration: `0028_document_collection_engine`, predecessor 0027, SHA-256 `F4726457B10B8D432D593B029DB23890682A08ED12AF3BCC7ED6CCDF61E7EED0`.
- API candidate: `opportunity-documents-mvp-api:phase2-20261118-candidate` — `sha256:3d34d678c6082c04f5de650202441191e6738caae6771d388bc7bd6667968418`.
- Worker candidate: `opportunity-documents-mvp-worker:phase2-20261118-candidate` — `sha256:ab2070b8ab955ddaba98fdacc2615f5da803c9abe66366102289788c3e301613`.
- Source/image hash manifest: [phase2-release-manifest.sha256](phase2-release-manifest.sha256).
- Restored isolated backup: 6,680 Masters; 9,470 SourceOpportunities; 62,044 SourceObservations; 75 aliases; one published document. Document 1 serialized SHA-256: `2c46ba8597e8179dd956043257beb04799099253959c517b5756fcef5c6f59c2`.

## Required services

1. Database migration 0028.
2. API candidate image.
3. Worker candidate image.

Frontend and Scheduler do not need replacement. No collection schedule is included. Keep existing source schedules intact.

## Deployment sequence

1. Obtain separate deployment authorization. Take a fresh production PostgreSQL backup, record SHA-256, and restore it to isolated PostgreSQL 16. Verify current head, counts, aliases, Document 1 identity/hash, and backup restoreability.
2. Confirm all six flags are false: engine, manual collection, scheduled collection, candidate staging, automatic approval, and automatic publication. Confirm no document-collection task appears in Beat.
3. Check Worker active tasks, reserved tasks, and queue depth. Drain/finish existing work before replacing Worker. Do not restart Worker with active or reserved tasks.
4. Apply migration 0028 once against production. Verify head, three new tables, foreign keys/indexes/check constraints, and unchanged legacy counts/Document 1 hash.
5. Recreate API and Worker only with the exact candidate image digests above. Leave Frontend and Scheduler unchanged.
6. Verify health, login/RBAC, private candidate API authorization, migration head, all six flags off, no collection Beat entry, row counts/75 aliases, and Document 1 state/hash. Confirm no collection task ran automatically.
7. If manual collection is later separately authorized, begin with an explicit allowlist of no more than 25 existing SourceOpportunity IDs. Review the private staged batch first. Approval and publication require separate human decisions; do not enable national enumeration or automation.

## Rollback

- **Before migration:** restore the current API and Worker image digests; no schema action is needed.
- **After migration but before any run/candidate/event rows exist:** the tested downgrade to 0027 is technically available, but use it only with explicit deployment rollback approval after confirming all three new tables are empty.
- **After collection data exists:** do not run the downgrade because it drops run checkpoints, candidates, and verification/review history. Restore the prior API/Worker images only if they can tolerate the additive schema; otherwise roll forward a fix. A full database restore is a separate recovery action requiring authorization and a reviewed RPO/RTO plan.
- Preserve the fresh predeployment backup and exact previous image references until post-deployment acceptance is complete.

## Stop/rollback triggers

- Migration integrity/foreign-key/check-constraint failure.
- Any change to Document 1 identity, publication state, or fingerprint.
- Existing business counts or identity aliases change unexpectedly.
- API authentication/RBAC regression or public exposure of private candidates.
- Any automatic document task starts while flags are off or a Beat schedule is present.
- Worker active-task drain cannot be completed safely.

This plan was not executed. No production migration, image recreation, service restart, source synchronization, candidate approval, or publication occurred.
