# Furas National Offline Replay — Acceptance Report

Date: 2026-11-10
Project: Saudi Investment Opportunities Platform
Execution mode: Offline replay in disposable PostgreSQL clone; read-only production verification

## Decision

- `OFFLINE_REPLAY = PASS` — all 6,548 saved capture records completed in two isolated passes.
- `PRODUCTION_ISOLATION = PASS` — replay evidence reports zero production DB connections, production mutations, Furas network requests, sync invocations, or scheduler/Celery invocations.
- `ALIAS_RESOLUTION = PASS` — 75/75 approved aliases matched the exact approved CSV mapping and 75 alias audit fixtures; no alias row had record mutations.
- `UNRESOLVED_IDENTITY_HANDLING = FAIL` — no unresolved record acquired a Master link, but the actual record path created 603 SourceOpportunity keys and 603 related observations for the 603 unresolved records before manual identity review. This violates the required quarantine/manual-review-before-source-key-creation rule.
- `WRITE_INTENT_REPORTING = PASS` — ORM writes and bulk SQL deletes are captured per provider, with table, operation, field names, and value hashes; record-level actions are in the CSV.
- `FURAS_PILOT_READINESS = NO-GO` — this offline result is not pilot authorization.

## Capture and identity results

The saved manifest validated with 6,548 records, 66 pages, and 70 captured requests. The reference and observed classifications matched exactly:

| Classification | Count |
| --- | ---: |
| Exact Furas SourceOpportunity match | 5,870 |
| Approved alias match | 75 |
| Unresolved/manual review | 603 |
| Unexpected classification changes | 0 |
| Identity conflicts | 0 |

The approved alias CSV SHA-256 is `4b7b0fe7c27e3fba2d6aff1fb8ba10aa1caa7bb52d4378b18608bf6b4af646b3`; the fixture had 75 active alias rows, 75 APPLIED audit rows, and zero mapping mismatches.

## Simulated database effects

These are clone-only effects. They are not production changes.

| Effect | First pass | Second pass |
| --- | ---: | ---: |
| New SourceOpportunity rows | 603 | 0 |
| New MasterOpportunity rows | 0 | 0 |
| SourceOpportunity update events | 5,870 | 6,473 |
| MasterOpportunity update events | 446 | 446 |
| SourceObservation inserts | 6,473 | 0 |
| Lifecycle record decisions | 680 | 0 |
| Geographic record decisions | 53 | 0 |
| Data-conflict/review records | 68 | 0 |
| Direct asset-assignment SQL delete calls | 446 (402 rows) | 446 (402 rows) |
| Asset-assignment insert events | 402 | 402 |

First pass additionally recorded 308 alert events, 68 audit events, 132 field-provenance rows, 3 change-history rows, and 512 system events. Second pass created 68 more system events. Table row counts were stable on the second pass, but it still repeated 6,473 source updates, 446 Master updates, and asset-assignment delete/reinsert work. Therefore repeated replay is not write-idempotent even though it does not create more source or observation rows.

The unresolved 603 ended with no MasterOpportunity links. The first-pass 603 new SourceOpportunity rows had null Master links; the report now defines `master_link_changed_in_replay` as true only for a materialized non-null Master link. The 603 were classified for manual review as 268 possible existing Furas identities, 3 conflicting source attributes, 4 unresolved cross-source Master references, and 328 insufficient-evidence potential Furas keys. No alias was approved or inferred by this replay.

## Isolation and backup provenance

The clone was restored from the existing verified backup `alahsa-local-sharakat_local-pre-furas-alias-20261110T101131Z.dump` (64,817,549 bytes; SHA-256 `5FEF9CDAAF8CA75E589A17F5CC6B57DCF8D3FE81CBB3834BBF88CE8B6E14E100`), migrated to 0026 and given only the approved 75-alias fixture in the disposable database. The replay container had a read-only project mount, a report-only writable mount, no external network route, no production credentials, and no Celery services. No Furas live capture was fetched.

The disposable database and its internal-only Docker network were removed after validation. No production services were restarted.

## Focused tests

Command executed in a read-only, network-none container:

`pytest -q -p no:cacheprovider tests/test_furas_offline_replay.py tests/test_source_identity_aliases.py tests/test_furas_capture_manifest.py tests/test_ingestion.py`

Result: **46 passed, 2 skipped**, with one existing Alembic `path_separator` deprecation warning.

Covered controls include disposable-PostgreSQL DSN rejection, saved-capture-only responses, alias and identity paths, bulk-delete ledger capture, lifecycle/geography/observation classification, ingestion matching and duplicate prevention, and null Master-link reporting.

## Production read-only snapshot

A separate transaction marked `READ ONLY` verified:

- Alembic head: `0026_source_identity_aliases`.
- Active aliases: 75; APPLIED alias audit rows: 75.
- MasterOpportunity rows: 6,678 total = 6,657 non-merged + 21 merged.
- Current SourceOpportunity rows: 9,468.
- Current SourceObservation rows: 56,371.
- Current SourceSyncJob rows: 858.
- Furas national enumeration and removal flags: false in API, Worker, and Scheduler environments.
- Latest Furas sync job remains November 2, 2026; no Furas sync was initiated by this task.

Compared with the task's earlier baseline, the current production snapshot is +29 observations and +1 sync-job row. The live scheduled service continued independently during the offline run; recent observed jobs were for `alahsa-opportunities`. The isolated runner had no production connection, so these later production counts are not replay effects. No writes were issued by the read-only verification.

## Required next step

Before any Furas pilot, implement and separately validate a safety gate that quarantines unresolved provider IDs before SourceOpportunity or SourceObservation creation. Then rerun this isolated replay and specifically require zero source-key, Master, and observation writes for the 603 unresolved IDs. Also address repeated second-pass updates/side effects before calling the pipeline idempotent. Enumeration and removals remain disabled; no pilot is authorized.

## Artifacts

- `FURAS-NATIONAL-OFFLINE-REPLAY-20261110.json` — full capture, write ledger, first/second pass, and per-record results.
- `FURAS-NATIONAL-OFFLINE-REPLAY-20261110.csv` — per-record proposed action and resulting clone-only identity links.
- `scripts/dry_run_furas_national_offline_replay.py` — isolated replay runner.
- `tests/test_furas_offline_replay.py` — focused safety tests.
