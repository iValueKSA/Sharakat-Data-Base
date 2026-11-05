# Furas Snapshot Stability and Live Recovery — 2026-11-02

**Result: COMPLETE.** A fresh post-Job-692 backup was restored and validated in isolation. The snapshot and checkpoint fixes passed focused and full regression tests, were deployed to `alahsa-local`, and a new controlled national Furas scan (Job 694) completed. Post-capture full DQ reported zero FAIL. Beat and API readiness are healthy. National enumeration, UI, map, dashboard, and removal reconciliation are left disabled for future scheduled work.

## Historical Job 692

Job 692 remains `FAILED` and unchanged. Its metrics JSON SHA-256 is `b15987ceee618bfb1ce42c6f7817e34d3e293368b6f2c16d3bd8c85e39eb0bd0`, matching the pre-recovery value. The failure handler had replaced its detailed V1 checkpoint with a rejection summary; deterministic cursor/page state is no longer available. It is therefore explicitly non-resumable. No cursor was inferred from row counts, record IDs, observations, or timestamps, and the job was not retried or edited.

## Post-692 backup and restore test

| Evidence | Result |
|---|---|
| Backup | `backups/20261102T072743Z-post692-furas-recovery.dump` |
| Created (UTC) | `2026-11-02 07:27:50.072318` |
| SHA-256 | `7310111e9ac276d3a7698a76b42fc91833b1e8e1d86bffada168ef862f1b269c` |
| Alembic | `0025_source_geographic_coverage` |
| Included baseline | 9,289 SourceOpportunity; 6,545 Furas; Job 692; 587 Masters |
| Restore test | Passed in isolated PostgreSQL 16; revision and counts verified |
| Sidecar | `backups/20261102T072743Z-post692-furas-recovery.manifest.json` |

An isolated partial-state rerun was performed only against the restored copy. Reprocessing 100 existing provider IDs inserted 0, updated 100, removed 0, and left total/Furas SourceOpportunity counts at 9,289/6,545, Masters at 587, duplicate provider-key groups at 0, and Job 692's metrics hash unchanged. The disposable restore container and network were removed after validation.

## Fixes and validation

`app/adapters.py` now obtains the complete ArcGIS object-ID membership set at scan start (`returnIdsOnly=true`), sorts and persists it with a deterministic digest, and fetches that exact membership in `objectIds` batches. New IDs are left to the next scan. Content updates during collection do not invalidate membership; disappeared snapshot members are recorded as missing and cannot trigger removals. Page hashes remain diagnostic. Completion requires every persisted snapshot object ID to be accounted for, with no duplicate object IDs/provider IDs and valid batch results.

The live Furas layer is `https://gisOppertunities.momra.gov.sa/arcgis/rest/services/GISProjects/InvestmentView/MapServer/0`, discovered through the public config at `https://gisapps.balady.gov.sa/opportunities/assets/config.json`. The live service identified `OBJECTID` as its OID field and accepted both `returnIdsOnly=true` and exact `objectIds` queries. Esri documents these query mechanisms in the [ArcGIS Map Service Layer Query reference](https://developers.arcgis.com/rest/services-reference/enterprise/query-map-service-layer/).

`app/furas_checkpoint.py` stores immutable checkpoint state separately from appended failure diagnostics. Failure handlers in `app/service.py` preserve the last committed batch checkpoint on validation, stale snapshot, HTTP, database, worker, cancellation, and finalization failures. Job 692's rejected legacy checkpoint remains historical non-resumable evidence. National removal reconciliation is default-off and additionally guarded for first bootstrap. No Master promotion was added. `app/celery_app.py` now refreshes the worker heartbeat independently of Beat, so pausing Beat does not cause a false stale-worker readiness failure and the readiness contract stays intact.

Deterministic tests cover IDs added, removed, reordered, and moved across pages; record-content drift; differing final page hashes; checkpoint retention across failure points; and the bootstrap removal guard. Focused lifecycle/Furas/adapter/ingestion suite: **59 passed, 1 skipped**. Canonical full suite `tests/`: **657 passed, 1 skipped, 42 warnings**. No migrations were run; Alembic remains 0025.

## Live deployment and health

The same candidate image digest `sha256:3ad925fef8999a11b073e152b1cb6abccc033636b952aeb569a9c4d07ec6a2da` runs API, Worker, and Beat. Automatic migration execution is disabled in the recovery Compose override. The API, worker, and scheduler all run with `ENVIRONMENT=local_user`; national enumeration, UI, map, dashboard, and removals are false. PostgreSQL and Redis are healthy, Celery worker ping returns `pong`, frontend returns HTTP 200, and `/health/ready` returns HTTP 200 with database/Redis/worker checks all `ok`. Beat was restored after Job 694 and post-capture DQ completed.

An unexpected old scheduler container was found running during repair, and it naturally dispatched scheduled Job 693 for `alahsa-opportunities` (source ID 2) before the controlled Furas capture. That job is distinguished from manual work: it was `scheduled` and outside the recovery capture. It was stopped before the controlled scan. After the successful DQ gate, Beat was restored with the patched image; its normal worker-heartbeat, due-source enqueue, and alert-dispatch maintenance entries ran, but no additional sync job appeared in the final live counts. Other manual source syncs: zero.

## Controlled Furas capture and DQ

Pre-recovery full DQ run `f409b7ce803b4587937d1919579437ef`: **130 pass, 4 warnings, 0 fail**. The only new controlled dispatch was Furas Job **694** (Celery task `5f061a21-f48a-4505-92a1-6fbc30205f37`), scope `SAUDI_NATIONAL_V1`, fingerprint `1c620978a5371335fe602a22fdc2da6873beb57a05f5f416400dfaece1cf4565`. It completed 2026-11-02 08:00:30 UTC with 6,484 IDs and digest `e91cfe73f53184fb698ca4eec18926d196039ebd0219f27547fa706580ad74e0`; 65 data pages, 6,484 received/parsed/unique, zero missing IDs, zero duplicates, and complete checkpoint V2. Counts: 1 inserted, 6,483 updated, 0 removed. Reconciliation was not executed; `master_rows_created_total=0`.

After Job 694: SourceOpportunity 9,289→9,290; Furas rows 6,545→6,546; Masters 587→587 (current Masters 566→566); observations 42,128→48,612; qualification rows 0→0; location rows 26→26. Furas provider-key duplicate groups remain 0. Existing linked Furas records stayed at 436; the one new record is unlinked. Job 692 remains unchanged with the original failed status and metrics hash.

Post-recovery full DQ run `06ddabf91f804caab572e02ac8fd0458`: **130 pass, 4 warning, 0 fail**, no failed gates. Its warnings are the existing generic-source-page, historical-review-audit, stale-source, and sync-runtime warnings. No DQ gate was weakened.

## Final controls

- Job 692 resumable: **false**; historical record changed: **false**.
- Recovery Job 694: **complete**; checkpoint final state: **complete**.
- Snapshot content changes invalidate scan: **false**; final page-hash equality required: **false**.
- Bootstrap removals/reconciliation: **disabled**, 0 removals.
- New Masters: **0**; duplicate Furas provider keys: **0**.
- Runtime patch deployed: **true**; API readiness: **200**; Beat: **healthy**.
- `FURAS_NATIONAL_ENUMERATION_ENABLED`: **false** after capture to prevent unattended national rescans until separately scheduled; removal reconciliation remains false.
- National UI/map/dashboard: **false**; environment remains `local_user`.
