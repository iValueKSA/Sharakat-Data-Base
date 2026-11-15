# Furas National Write Idempotency — Acceptance Report

Date: 2026-11-10  
Project: Saudi Investment Opportunities Platform  
Mode: offline saved-capture replay; disposable PostgreSQL 16 clone; no production access

## Decision

- `SOURCE_WRITE_IDEMPOTENCY = PASS`
- `MASTER_WRITE_IDEMPOTENCY = PASS`
- `ASSET_WRITE_IDEMPOTENCY = PASS`
- `BUSINESS_EVENT_IDEMPOTENCY = PASS`
- `OBSERVATION_IDEMPOTENCY = PASS`
- `GENUINE_UPDATE_PRESERVATION = PASS`
- `QUARANTINE_GATE_PRESERVED = PASS`
- `ALIAS_RESOLUTION_PRESERVED = PASS`
- `THREE_PASS_REPLAY = PASS`
- `PRODUCTION_ISOLATION = PASS`
- `PRODUCTION_DATA_MUTATIONS = ZERO`
- `FURAS_PILOT_READINESS = NO-GO`

## Root cause

The repeated updates came from ingestion assigning `last_seen_at` on every pass for existing SourceOpportunity and Master rows, and refreshing Master `last_updated_at`/`updated_at` even when no Master business field had changed. The asset projection deleted every assignment for a source row and reinserted the desired set even when it was identical. Alert generation also ran for monitored fields without first requiring a changed value.

Review reevaluation used a capped scan of recent `SYSTEM_REEVALUATION` events. Its JSON job-id comparison did not reliably match JSON `null` in PostgreSQL. A precise event-type/fingerprint/job lookup now recognizes the same event without scanning an arbitrary recent window. New conflicts still receive their first `NO_MATERIAL_CHANGE` reevaluation event as per-job operational telemetry.

The changed-record fixture also found that `full_description` was omitted from the existing Master update/provenance field list, and aggregate lifecycle transitions could add status provenance only on a later pass. Both are corrected through the existing precedence and provenance flow.

The earlier accepted replay report measured ORM dirty-write intents, not the SQL executed by PostgreSQL. Its second-pass counts (5,870 SourceOpportunity intents and 446 Master intents) therefore are not presented as actual SQL counts. Actual SQL was instrumented in this run.

## Three-pass saved-capture replay

The replay used the saved 6,548-record capture, restored from the verified pre-alias backup into disposable PostgreSQL 16, migrated only that clone to 0026, and applied the exact approved 75-row alias fixture only there. The replay container had a read-only project mount, a report-only writable mount, an internal-only Docker network, and no Celery or live HTTP client.

Identity partition on each pass: 5,870 exact matches, 75 approved aliases, 603 quarantined identities. All 6,548 records completed on all three passes. Alias CSV SHA-256: `4b7b0fe7c27e3fba2d6aff1fb8ba10aa1caa7bb52d4378b18608bf6b4af646b3`; 75/75 mappings and 75 clone audit rows matched.

| Actual SQL mutation statements | Pass 1 | Pass 2: identical | Pass 3: identical |
| --- | ---: | ---: | ---: |
| SourceOpportunity UPDATE | 5,870 | 0 | 0 |
| MasterOpportunity UPDATE | 199 | 0 | 0 |
| SourceObservation INSERT | 5,870 | 0 | 0 |
| Asset assignment INSERT/UPDATE/DELETE | 0 | 0 | 0 |
| Business-table SQL mutations overall | 13,449 total writes across all tables | **0** | **0** |
| `SYSTEM_REEVALUATION` operational telemetry INSERT | 367 | 71 | 0 |

Pass 1 also inserted 800 field-provenance rows, 71 conflict rows, 53 alerts, 68 audit rows, 3 change-history rows, and 515 system events (71 fingerprint-capture, 77 sector-classification, 367 review-reevaluation events). These are actual statements and their row counts matched.

The 71 pass-2 `SYSTEM_REEVALUATION` events were the first no-material-change reevaluation for review fingerprints introduced in pass 1, grouped as per-job operational telemetry. They contain no business state transition, are reported separately, and did not recur in pass 3. Pass 3 executed zero SQL mutation statements.

Of the 603 unresolved IDs, source creations, observations, Master changes, lifecycle/geography writes, asset writes, and all other business writes were zero on all passes. No Master was created. The 75 aliases resolved to their existing targets and generated no SourceOpportunity or Master mutation.

## Genuine change and concurrency validation

The isolated `_safe_record` fixture captured SQL and verified that an identical repeat produced no DML. A controlled real change then updated title, description (including `full_description`), raw deadline, lifecycle status, location and coordinates, and asset assignments. Existing asset A/B assignment row IDs were preserved while C was removed and D added. Provenance and change history remained present. The next identical replay produced no business DML; the one-time no-change review telemetry was separately classified.

A two-thread test processed the same known national Furas provider ID concurrently against the disposable PostgreSQL clone. The exact-match resolver acquired a transaction-scoped row lock for national Furas only. Both calls resolved to the same SourceOpportunity and executed zero INSERT/UPDATE/DELETE statements.

## Focused tests

Executed in isolated containers, with both PostgreSQL fixtures enabled:

`tests/test_furas_identity_quarantine.py`, `tests/test_source_identity_aliases.py`, `tests/test_furas_offline_replay.py`, `tests/test_furas_capture_manifest.py`, `tests/test_ingestion.py`, `tests/test_review_lifecycle_triage.py`, `tests/test_review_queues_governance.py`, `tests/test_asset_facility_types.py`, and `tests/test_sector_inference_phase2.py`

Result: **101 passed, 0 skipped**. This includes the 75-alias PostgreSQL apply/rollback test, alias concurrency test, same-provider concurrent replay test, quarantine and namespace isolation, source/Master/asset idempotency, changed-field preservation, event review behavior, lifecycle and geography regressions. Only existing pytest-asyncio, Starlette/httpx, and Alembic deprecation warnings were emitted.

`py_compile`-equivalent in-memory syntax checks passed for every changed Python file. `git diff --check` passed.

Performance observation: the full three-pass replay took about 12 minutes wall time, with the disposable PostgreSQL container peaking below 0.5 GiB in observed samples. This is the first replay with SQL-level instrumentation, so no comparable pre-fix SQL/runtime baseline exists. The concurrency serialization uses the same identity lookup with `FOR UPDATE` and adds no second lookup.

## Isolation and remaining blockers

No production database connection, mutation, source synchronization, live Furas request, Celery/scheduler invocation, migration, alias application, or production service restart occurred. Only the disposable replay and alias-test databases were changed. Production flags and the accepted quarantine gate were not changed.

The offline replay does not exercise the control-plane checkpoint/sync-job wrapper. No production pilot or deployment is authorized. The accepted production alias batch and 0026 migration were not reapplied.

## Artifacts and code changes

- `FURAS-NATIONAL-OFFLINE-REPLAY-20261110.json` — three-pass per-record decisions, ORM intent ledger, actual SQL ledger, before/after clone counts.
- `FURAS-NATIONAL-OFFLINE-REPLAY-20261110.csv` — record-level identity and quarantine results.
- `FURAS-WRITE-IDEMPOTENCY-ACCEPTANCE-20261110.md` — this report.
- Code/test edits: `app/service.py`, `app/source_identity_aliases.py`, `app/furas_identity_quarantine.py`, `scripts/dry_run_furas_national_offline_replay.py`, `tests/test_ingestion.py`, `tests/test_furas_offline_replay.py`.

Recommended next action: retain Furas enumeration/removals disabled and perform a separate pilot-readiness review before any controlled production execution.
