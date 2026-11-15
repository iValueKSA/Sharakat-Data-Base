# Furas Strict Identity Quarantine — Isolated Acceptance

Date: 2026-11-10  
Project: Saudi Investment Opportunities Platform  
Scope: Backend quarantine gate and offline replay only  
Production deployment: Not performed

## Acceptance decision

| Requirement | Result |
| --- | --- |
| `QUARANTINE_GATE` | PASS |
| `603_UNRESOLVED` | PASS — 603/603 receive a decision in each pass |
| `SOURCE_CREATION_PROTECTION` | PASS — zero unresolved SourceOpportunity rows or inserts |
| `OBSERVATION_PROTECTION` | PASS — zero unresolved SourceObservation writes |
| `MASTER_PROTECTION` | PASS — zero unresolved Master links or Master writes |
| Lifecycle, geography, asset, review protection | PASS — zero unresolved write-ledger entries in these areas |
| Exact and approved-alias preservation | PASS — 5,870 exact; 75 aliases; no alias mutations |
| Production isolation | PASS — no production connection or writes |
| `FURAS_PILOT_READINESS` | **NO-GO** — known-record write idempotency remains Blocker B |

## Implementation

The national Furas path now resolves identities at the beginning of `_safe_record`, before normalization, candidate matching, taxonomy, observation, lifecycle, geographic, review, or asset processing:

1. Look up the exact canonical Furas source key.
2. If absent, use the existing active, approved alias resolver.
3. Continue through the existing record path only for exact or valid alias identities.
4. Return a structured, non-persistent quarantine decision for unresolved or invalid/conflicting aliases.

The lookup runs under `Session.no_autoflush`. It creates no quarantine table or review-queue row. For unresolved records, the live batch path skips source insert/update totals; the replay writes record-level quarantine evidence only to the isolated report directory. The gate is scoped to Furas while `FURAS_NATIONAL_ENUMERATION_ENABLED` is on; other sources and local Furas mode retain the existing path.

A quarantine decision includes provider ID, source namespace, capture snapshot/run ID, official reference, exact-then-alias lookup attempt/status, reason, source endpoint, OBJECTID, captured record SHA-256, processing timestamp, and recommended review action. Existing adjudication evidence maps the 603 reasons as follows:

| Quarantine reason | Count |
| --- | ---: |
| `UNRESOLVED_EXISTING_IDENTITY` | 268 |
| `IDENTITY_ATTRIBUTE_CONFLICT` | 3 |
| `CROSS_SOURCE_MASTER_UNRESOLVED` | 4 |
| `INSUFFICIENT_IDENTITY_EVIDENCE` | 328 |
| **Total** | **603** |

Previously unseen IDs receive `UNRECOGNIZED_PROVIDER_ID`. Invalid references and alias integrity failures are quarantined with their specific reason categories.

## Isolated two-pass replay

The saved 6,548-record capture completed twice against a disposable PostgreSQL 16 clone restored from the verified pre-alias backup. The clone was migrated to 0026 and seeded with the approved alias fixture only inside the clone. The runner had no external egress, production credentials, Celery connection, or writable project mount; only the evidence output directory was writable.

| Result | First pass | Second pass |
| --- | ---: | ---: |
| Records completed | 6,548 | 6,548 |
| Exact source identities | 5,870 | 5,870 |
| Approved aliases | 75 | 75 |
| Quarantined unresolved identities | 603 | 603 |
| Quarantined IDs with any write-ledger entry | 0 | 0 |
| Unresolved source rows after replay | 0 | 0 |
| Unresolved Master links after replay | 0 | 0 |

The classification remained 5,870 exact / 75 alias / 603 unresolved, with no unexpected identity changes. All 75 active alias table rows matched the approved CSV mappings, including their existing SourceOpportunity and Master targets. The replay returned all 75 existing targets and made no alias-record writes.

Across the whole clone, first pass recorded zero SourceOpportunity creations and zero Master creations. Its 5,870 SourceOpportunity updates, 5,870 observations, 446 Master updates, 77 lifecycle decisions, 53 geography decisions, and 68 data-conflict/review rows belonged to known exact records, not quarantined IDs. The 603 quarantined records had empty write ledgers and no lifecycle, geography, observation, review, or other mutation dimensions.

## Blocker B remains open

The replay intentionally did not fix known-record idempotency. On the second pass, known exact records repeated:

- 5,870 SourceOpportunity updates.
- 446 Master updates.
- 446 asset-assignment delete calls affecting 402 rows, followed by 402 inserts.
- 68 additional system events.

No new SourceOpportunity, Master, or SourceObservation rows were created in the second pass. These repeated writes remain a separate blocker and keep Furas pilot readiness at NO-GO.

## Focused validation

Executed in a read-only, network-none test container:

`pytest -q -p no:cacheprovider tests/test_furas_identity_quarantine.py tests/test_furas_offline_replay.py tests/test_source_identity_aliases.py tests/test_furas_capture_manifest.py tests/test_ingestion.py`

Result: **51 passed, 2 skipped**, with one existing Alembic `path_separator` deprecation warning. The skipped cases require separately configured PostgreSQL integration-test URLs. Tested the actual `_safe_record` path for unresolved and unseen IDs, exact and alias matches, key collision, inactive/invalid/missing alias targets, Master-reference conflict, repeated and concurrent unresolved processing, autoflush safety, and source-namespace isolation. The full saved-capture replay verifies zero unresolved writes in both passes.

## Diagnostic attempts

Two earlier isolated attempts are retained under `attempt-1-flag-scope-diagnostic/` and `attempt-2-count-aggregation-diagnostic/`:

1. The first harness scoped its national-flag override to adapter fetch, so the record-path gate was not active. Its clone was destroyed before the acceptance rerun.
2. The second attempt activated the gate and produced zero unresolved writes, but the runner incorrectly aggregated a nested reason-count dictionary as an integer. That harness-only reporting error was fixed; the clone was destroyed before the successful acceptance rerun.

The final replay above started from a fresh restore and completed with runner status `PASS` and quarantine-gate status `PASS`.

## Production safety

`PRODUCTION_DATA_MUTATIONS = 0`. The replay connected only to disposable database `furas_replay` on an internal-only Docker network. No production connection or write was used by this task. Production migration, aliases, schedules, and feature flags were not changed by this task; no ingestion or sync was triggered. No deployment or service restart was performed. Both temporary replay databases and their internal networks were removed after validation.

## Files changed or created

- Modified `app/service.py` — early Furas-national gate and quarantine-aware batch totals.
- Created `app/furas_identity_quarantine.py` — lookup-only decision logic.
- Modified `scripts/dry_run_furas_national_offline_replay.py` — two-pass quarantine replay, per-record evidence, assertions, and alias-target reporting.
- Created `tests/test_furas_identity_quarantine.py` — focused integration-path safety scenarios.
- Created `FURAS-NATIONAL-OFFLINE-REPLAY-20261110.json` and `.csv` — full replay ledger and per-provider decisions.
- Created this acceptance report.

No migration, frontend, geography, source-identity approval, or production files were changed.

## Next recommended action

Keep Furas enumeration and removals disabled. Address Blocker B in a separate scoped task by making known-record updates and side effects idempotent, then repeat isolated replay before considering any separately authorized pilot.

