# Public-source nationwide rollout runbook

Use this runbook for anonymous, publicly accessible official reference data and source listings. Separate written licensing, access permission, or custodian approval is not a rollout prerequisite. A public landing page is not proof that restricted detail records may be accessed. Never bypass login, API-key, CAPTCHA, subscription, or other access controls.

1. Record a read-only production baseline: deployed API/worker/beat image tags, lifecycle behavior, database revision, flags, source/job state, counts, and DQ.
2. Verify a current production backup manifest and SHA-256. Restore it to an isolated PostgreSQL environment and confirm row counts/digests before changes.
3. For each public reference dataset, record the official publisher, public URL, retrieval time, version/effective date when published, source evidence, expected counts, and raw-file digest. If no version or count is published, document that limitation; do not invent one.
4. Verify the source can be reached anonymously through its normal public page/download/API. Skip restricted records and document the limitation.
5. Run `python scripts/validate_geographic_reference.py --input <public-reference.json>`; review source authority, public access, IDs, hierarchy, counts, coverage, and digest. Dry-run performs zero writes.
6. In the isolated database, apply migrations 0024 then 0025. Import the immutable public reference version and confirm its evidence and digest.
7. Run isolated DQ and focused API/filter/export/map checks. Resolve every FAIL gate without weakening it. City may remain unavailable when the source reference lacks confidently verified city coverage.
8. Run source expansions one source at a time. For each: anonymous public-scope review; isolated implementation and focused tests; bounded dry-run and volume estimate; stable-ID/idempotency checks; geography and eligibility review; removal-scope safety checks; isolated DQ; then verify current backup and no overlapping active job before the controlled production sync.
9. Reconcile removals only after complete enumeration of the identical recorded scope. Any partial page, timeout, error, truncation, count mismatch, scope change, zero-page anomaly, or failed job means no removals.
10. Preserve raw locations, IDs, URLs, source observations, provenance, and merge lineage. Unknown locations remain `UNSPECIFIED/REVIEW`. Do not infer from titles, owners, or centroids.
11. Before national activation, run full regression, DQ, five viewport Playwright, API/filter/CSV/XLSX parity, dependent-filter behavior with and without City, map provenance checks, duplicate checks, and lifecycle monotonicity checks.
12. Confirm the resulting deployable API/worker/beat images preserve terminal-state monotonicity and atomic state transitions. Never deploy older base images over the lifecycle patch.
13. Keep national flags off until migrations, public reference readiness, source validation, DQ, and UI checks pass. Enable national UI, dashboard, and map only after a production read-only preflight confirms the correct revision and source evidence. Map pins require verified source coordinates.
14. Keep Furas enumeration as a separate switch from UI/geography flags. Enable its national mode only after isolated full count/ID/page validation, source identity checks, and safe complete-scope reconciliation checks pass.
15. Validate national unique Master totals, by-region/governorate/sector/source/status summaries, mapped and unspecified counts, and non-additive multiple-location/nationwide scope. Confirm Al-Ahsa remains an available geographic filter and all prior Masters/SourceOpportunity records remain intact.

## Source and reconciliation safeguards

- Keep `SOURCE_ENUMERATION_SCOPE`, `MASTER_GEOGRAPHIC_ELIGIBILITY`, and `REMOVAL_RECONCILIATION_SCOPE` separate.
- Furas must use stable official IDs, bounded batches, bounded concurrency, retries, and resumable checkpoints. The existing Job 651/666 ordering-race fix must remain in all deployed images.
- Invest Saudi expansion reuses current SourceOpportunity identities. Dry-run and review eligibility before any Master promotion; never mass-promote all national records.
- One current Master represents one real opportunity. Cross-source matching requires strong identity evidence; similar titles alone do not justify merging.
- A national or region-wide scope is not a fabricated physical location. Unknown coordinates remain unpinned and visible in the list.

## Rollback

1. Turn off national UI, dashboard, map, and Furas national enumeration flags.
2. Restore the previous public reference version by its immutable version record; retain the rolled-back version and evidence.
3. Do not delete or rewrite Masters, source rows, observations, reviews, audits, merge lineage, raw source values, or coordinates as a rollback side effect.
4. Verify Al-Ahsa legacy behavior, lifecycle health, DQ, flags, and deployed image tags; record the rollback result.
