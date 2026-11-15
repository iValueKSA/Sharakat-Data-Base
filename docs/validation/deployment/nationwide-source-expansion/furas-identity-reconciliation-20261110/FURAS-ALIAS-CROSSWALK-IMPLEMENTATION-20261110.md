# Furas Alias Crosswalk — Isolated Implementation and Validation

**Date:** 2026-11-10  
**Scope:** Controlled development and isolated testing only. No production migration, alias application, sync, ingestion, or service restart was performed.

## Result matrix

| Acceptance item | Result | Evidence |
|---|---|---|
| `ALIAS_CROSSWALK_IMPLEMENTATION` | PASS | Crosswalk model, resolver, atomic batch application and deactivation rollback implemented. |
| `ALIAS_SCHEMA_VALIDATION` | PASS | Composite namespace/target foreign keys, alias uniqueness, status/action checks, audit constraints and indexes validated. Migration 0026 was exercised in the isolated migration validation. |
| `ALIAS_RESOLUTION` | PASS | Exact canonical key is checked first. An active alias resolves only to the existing source row when namespace, canonical key, and expected Master relationship still match. Conflicts, inactive aliases, missing/merged Masters and unsupported IDs fail closed. |
| `APPROVED_75_ALIASES` | PASS — isolated fixture | All 75 approved CSV rows applied and resolved to the SourceOpportunity and MasterOpportunity IDs stated in the approved artifact. A second application attempt returned 0 new mappings and 75 idempotent mappings. |
| `COLLISION_PREVENTION` | PASS | Tests cover conflicting reassignment, canonical-key collision, wrong namespace, missing target and database constraints; failed batch leaves no partial writes. Concurrent insertion yields one active mapping and one application audit. |
| `IDEMPOTENCY` | PASS | Repeated single-row application and the full 75-row retry produced no duplicates. |
| `ROLLBACK_VALIDATION` | PASS | Isolated rollback deactivated all 75 aliases, retained all 75 mapping rows and audit history, made aliases unresolvable, and left source/master identities unchanged. Repeated rollback was harmless. |
| `MASTER_IDENTITY_PRESERVATION` | PASS — isolated fixture | All 75 expected Master IDs remained linked; no Master rows were created, merged, or reassigned. |
| `SOURCE_IDENTITY_PRESERVATION` | PASS — isolated fixture | All 75 canonical source keys remained unchanged; no SourceOpportunity rows were created or overwritten. Observation preservation and lookup-only repeated ingestion resolution were tested. |
| `ISOLATED_TEST_RESULTS` | PASS | `tests/test_source_identity_aliases.py`: **13 passed** against a disposable, unpublished PostgreSQL 16 database; no skips. CLI help succeeded and an application invocation without the explicit environment gate exited blocked before opening a database session. The project bind mount was read-only. |
| `PRODUCTION_DATA_MUTATIONS` | ZERO | No aliases applied, production migration run, source sync, or ingestion triggered. |

## Approved artifact and fixture scope

The approved input is `FURAS-75-APPROVED-ALIASES-20261110.csv` (75 rows), SHA-256:

`4B7B0FE7C27E3FBA2D6AFF1FB8BA10AA1CAA7BB52D4378B18608BF6B4AF646B3`

The isolated integration test builds sanitized identity-only fixtures using the artifact’s approved source and Master IDs and canonical keys. It does not copy opportunity business content into the disposable database. This verifies implementation behavior against the approved mapping values; it does **not** replace the mandatory current-state production revalidation before any future application.

The isolated test database was created in a temporary internal Docker network, had no published port or production credentials, and was deleted after the test. No production container was recreated or restarted.

## Implementation

- `SourceIdentityAlias` stores the source namespace, provider alias, target SourceOpportunity, preserved canonical source key, expected Master ID, evidence/artifact hashes, decision fingerprint, approval metadata, application batch, and active state.
- `SourceIdentityAliasAudit` records application and rollback actions with before/after evidence. History is retained; rollback deactivates mappings rather than deleting them.
- Database constraints prevent duplicate aliases in a source namespace and cross-namespace targets. Foreign keys protect source, target, Master, and audit references.
- Application requires a clean transaction, the complete expected batch, valid approved evidence, and the exact artifact digest. A shared PostgreSQL advisory lock serializes alias application with the existing Furas sync checkpoint writer. Conflicts roll back the complete batch.
- `_safe_record` uses alias resolution as lookup only. An alias hit returns the existing SourceOpportunity and increments a counter; it does not apply incoming fields, create observations, update lifecycle/geography/review state, or change Master relationships.
- Migration `0026_source_identity_aliases` follows `0025_source_geographic_coverage`. Its downgrade refuses to remove alias or audit history when rows exist.
- `scripts/manage_source_identity_aliases.py` offers explicit `apply` and `rollback` commands. Both require `SOURCE_IDENTITY_ALIAS_APPLICATION_ENABLED=true`. The application command also pins the approved CSV SHA-256 and expected row count.

## Production state — read-only check

At final verification, the live local API reported migration version `0025_source_geographic_coverage`; the alias and alias-audit tables were absent. The API and scheduler each reported:

- `FURAS_NATIONAL_ENUMERATION_ENABLED = false`
- `FURAS_NATIONAL_REMOVAL_RECONCILIATION_ENABLED = false`

No migration was applied to production. These checks were read-only.

## Controlled future application procedure

Production application is **not performed or authorized by this implementation task**. Before a separately approved application window:

1. Obtain explicit approval for the exact 75-row batch, operator, environment, and maintenance window. Confirm Furas enumeration and removals remain disabled.
2. Take and verify a restorable PostgreSQL backup. Record the current migration head and row counts for `sources`, the affected `source_opportunities`, their linked Masters, observations, and existing aliases/audits.
3. Revalidate the approved CSV digest above and every evidence reference against the saved capture. Re-read every target SourceOpportunity: source namespace, canonical key, target ID, Master ID, merge status, and any intervening identity changes must still match the approval artifact.
4. Check that none of the 75 provider IDs now exists as a canonical Furas source key or an alias, and that no target is missing, moved to another source, merged, or linked to a different Master. Abort on any mismatch; do not repair or infer identities during application.
5. Deploy the reviewed code and migration as a separate controlled deployment. Apply migration 0026 in the approved window, verify schema and migration version, then use a unique batch ID with the explicit gated command below. The function applies all 75 mappings and audits atomically in one transaction under the Furas namespace lock:

   ```powershell
   $env:SOURCE_IDENTITY_ALIAS_APPLICATION_ENABLED = 'true'
   python scripts/manage_source_identity_aliases.py apply `
     --approved-csv docs/validation/deployment/nationwide-source-expansion/furas-identity-reconciliation-20261110/FURAS-75-APPROVED-ALIASES-20261110.csv `
     --expected-sha256 4B7B0FE7C27E3FBA2D6AFF1FB8BA10AA1CAA7BB52D4378B18608BF6B4AF646B3 `
     --expected-count 75 --source-key furas `
     --batch-id <unique-approved-batch-id> --actor <authorized-operator>
   ```

6. Verify 75 active mappings and 75 `APPLIED` audit events; resolve each provider ID to its approved target; confirm canonical keys, Master links, source/Master counts, observations and Furas flags are unchanged. Disable the one-time application gate after the window.
7. If rollback is required, use the exact application batch ID and expected count with the gated `rollback` command. It deactivates the batch and records rollback audit events; it does not delete crosswalk history. Verify no provider ID resolves through the deactivated aliases and canonical/Master identities remain unchanged.

Rollback invocation after re-enabling the explicitly authorized gate: `python scripts/manage_source_identity_aliases.py rollback --source-key furas --application-batch-id <application-batch-id> --rollback-batch-id <unique-rollback-id> --expected-count 75 --reason <documented-reason> --actor <authorized-operator>`. A successful alias application alone does not authorize Furas ingestion or a national pilot. A separate ingestion safety review is required because `allow_master_creation=false` does not prevent updates to an existing Master.

## Readiness and remaining blockers

- `PRODUCTION_APPLICATION_READINESS = PREPARED_NOT_APPLIED`
- `FURAS_PILOT_READINESS = NO_GO`
- `MIGRATIONS_CREATED = 1 (0026_source_identity_aliases)`
- `MIGRATIONS_APPLIED_TO_PRODUCTION = NO`
- `FURAS_NATIONAL_SCHEDULING = DISABLED`
- `FURAS_NATIONAL_REMOVALS = DISABLED`

Remaining requirements are a separately authorized production deployment/application window, backup and live identity revalidation at that time, and a separate review before any Furas pilot. The other 603 provider IDs remain unresolved and are not included in this crosswalk.

## Files created or modified for this task

**Created**

- `app/source_identity_aliases.py`
- `migrations/versions/0026_source_identity_aliases.py`
- `scripts/manage_source_identity_aliases.py`
- `tests/test_source_identity_aliases.py`
- `docs/validation/deployment/nationwide-source-expansion/furas-identity-reconciliation-20261110/FURAS-ALIAS-CROSSWALK-IMPLEMENTATION-20261110.md`

**Modified**

- `app/models.py`
- `app/service.py`

No unrelated existing workspace changes were included in the isolated test image; project files were mounted read-only.

