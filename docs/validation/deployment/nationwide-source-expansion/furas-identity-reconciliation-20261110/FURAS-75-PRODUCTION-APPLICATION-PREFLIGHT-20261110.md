# Furas 75 Alias Application — Production Preflight

**Date:** 2026-11-10  
**Mode:** Read-only production checks; disposable PostgreSQL 16 validation only. No production deployment, migration, alias application, source sync, ingestion, or service restart was performed.

## Decision

`PRODUCTION_APPLICATION_READINESS = GO — READY_FOR_SEPARATE_PRODUCTION_AUTHORIZATION`  
`FURAS_PILOT_READINESS = NO-GO`  
`PRODUCTION_DATA_MUTATIONS = ZERO`

This GO is for a separately approved, maintenance-window deployment and alias application following the sequence below. It is not authorization to deploy, apply aliases, or run a Furas pilot now.

## Required result matrix

| Gate | Result | Observed evidence |
|---|---|---|
| `LIVE_75_IDENTITY_REVALIDATION` | PASS — 75/75 | Read-only repeatable-read transaction: each target SourceOpportunity ID, Furas source ID, canonical source key, expected Master ID, and unmerged Master matched the approval artifact and saved identity snapshot. No missing targets, identity drift, merged Masters, or canonical provider-ID collisions. No target `last_seen_at` was later than the saved snapshot. |
| `ALIAS_INTEGRATION_REGRESSION` | PASS | The alias suite and existing ingestion, entity-resolution and nationwide-safety tests passed together. Exact-key/no-alias behavior, alias lookup, fallback, namespace isolation, Master preservation, and lookup-only ingestion path were covered. |
| `MIGRATION_0026_SAFETY` | PASS — isolated PostgreSQL 16 | Simulated an empty schema at revision 0025, upgraded to 0026, verified alias/audit tables and uniqueness, downgraded while empty, then re-upgraded. No production migration was run. |
| `BACKUP_RECOVERY_READINESS` | PASS — isolated validation | A disposable PostgreSQL custom-format dump passed `pg_restore --list`, restored into a second disposable database, and retained the revision, sentinel row, and alias/audit schema/counts. No live backup was taken. |
| `SOURCE_IDENTITY_PRESERVATION` | PASS — preflight | All 75 canonical source keys and target IDs matched the saved identity snapshot. The 150 referenced historical observation IDs exist. |
| `MASTER_IDENTITY_PRESERVATION` | PASS — preflight | All 75 expected Master links match and each linked Master exists with `merged_into_id IS NULL`. |
| `APPROVED_ALIAS_COLLISIONS` | 0 | 75 unique provider IDs; no provider ID currently exists as a canonical Furas key. Production is still at 0025, so alias tables are absent and no existing crosswalk assignment can be present. |
| `PRODUCTION_APPLICATION_BLOCKERS` | None for the separately authorized controlled procedure | Production code/schema deployment and the application remain pending that separate authorization and maintenance window. Furas pilot remains independently blocked. |

## Live revalidation details

- Approved CSV: 75 rows, 75 distinct provider IDs; every row remains `APPROVED_AUTOMATICALLY`.
- Artifact SHA-256: `4B7B0FE7C27E3FBA2D6AFF1FB8BA10AA1CAA7BB52D4378B18608BF6B4AF646B3`.
- All 75 official references match their provider IDs; all 75 record evidence digests have valid SHA-256 formatting.
- All 150 historical observation references in the approved decisions still exist.
- Snapshot: `2026-11-10T08:44:32.8004794Z`; live source key is `furas`, source ID 1. Identity fields for all proposed targets and Masters match the snapshot.
- Current live migration is `0025_source_geographic_coverage`; both alias tables are absent. API and scheduler each report Furas national enumeration and removal reconciliation disabled.
- The saved snapshot is an identity-state snapshot, not a full row-content snapshot. The revalidation proves current identifiers, source namespace, Master links/merge state, provider-key collisions, observation-reference presence, and no later `last_seen_at`; it does not claim byte-for-byte parity of all opportunity attributes/geography against the approval-time content.

The live check ran inside a PostgreSQL `REPEATABLE READ READ ONLY` transaction and ended with `ROLLBACK`. No write statements were issued.

## Implementation and integration review

- `apply_approved_alias_batch` is limited to source key `furas`, requires the complete expected batch and approved evidence, validates the exact artifact hash, locks the source/targets, and applies mappings plus audit rows atomically. It shares the Furas advisory lock used by the checkpointed sync path.
- Database constraints enforce alias uniqueness per source, namespace-to-source and target-to-source referential integrity, Master/audit foreign keys, and allowed status/action values. The cross-table check that a proposed alias is not already a canonical SourceOpportunity key is enforced in the application transaction under the shared lock; the resolver fails closed if an alias/canonical conflict is encountered. The supported Furas sync path uses the same lock.
- `resolve_source_identity` scopes aliases by `source.id`; exact canonical lookup is performed first. With no alias, exact identity and no-match fallback behavior remain unchanged. If an inconsistent state contains both a canonical row and an alias for the same token, resolution fails closed instead of choosing an arbitrary target.
- `_safe_record` calls the resolver for source identity lookup. A valid alias returns the existing SourceOpportunity and increments in-memory counters. It does not update SourceOpportunity or MasterOpportunity fields, create an observation, or alter lifecycle/geographic/review state. Existing exact-key matches continue through the pre-existing ingestion behavior.
- Alias application is separate from ingestion and does not enqueue work or start Furas collection. The known `allow_master_creation=false` limitation remains; it is not used as a safety boundary.
- All ingestion paths using the changed resolver require migration 0026 first because the resolver queries the alias table. Old API/Worker code is compatible with the additive schema; new API/Worker code must not be started against revision 0025.

## Isolated tests and backup results

- Command scope: `tests/test_source_identity_aliases.py`, `tests/test_ingestion.py`, `tests/test_entity_resolution.py`, and `tests/test_nationwide_expansion_safety.py`.
- Result: **93 passed, 1 skipped**. The skip was the optional generic PostgreSQL checkpoint-lock test requiring `FURAS_CHECKPOINT_TEST_DATABASE_URL`; the alias-specific PostgreSQL concurrency test ran and passed. Warnings were library deprecation notices.
- Migration: upgrade from the simulated 0025 schema, empty downgrade, and re-upgrade all passed against PostgreSQL 16.
- Backup: custom-format `pg_dump`, archive listing, restore to a second disposable PostgreSQL database, and verification of migration version plus fixture/schema counts passed. The disposable containers and internal networks were removed afterward.
- No project runtime code or tests were changed during this preflight. The local project tree was mounted read-only into test containers.

## Backup and recovery procedure for the future window

1. Confirm a restorable backup destination with adequate space and an approved retention/access policy. Record pre-change migration version and read-only counts for `sources`, `source_opportunities`, `opportunities`, `source_observations`, lifecycle/audit tables, and alias tables (absent at 0025).
2. With no TTY, create a custom archive from the API container’s configured database URL and copy it to the approved host backup directory. Example PowerShell commands:

   ```powershell
   $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
   $containerDump = "/tmp/furas-alias-preflight-$stamp.dump"
   $hostDump = ".\backups\furas-alias-preflight-$stamp.dump"
   docker exec alahsa-local-api-1 sh -lc "pg_dump --dbname=`$DATABASE_URL --format=custom --no-owner --no-privileges --file=$containerDump"
   if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
   docker cp "alahsa-local-api-1:$containerDump" $hostDump
   if ($LASTEXITCODE -ne 0) { throw 'docker cp failed' }
   Get-FileHash $hostDump -Algorithm SHA256
   ```

3. Check archive readability with `pg_restore --list`, then restore it into a fresh isolated PostgreSQL 16 database. Compare migration head and pre-change row counts; verify representative source, Master, observation, lifecycle, and audit rows. A successful dump command alone is not backup acceptance. Do not restore into production as a test.
4. Keep the verified archive unchanged. Record path, hash, size, verification time, and operator in the change record. No live backup was taken during this read-only preflight.

## Proposed deployment and application sequence

1. Obtain separate explicit authorization naming the production environment, 75-row artifact/hash, operator, maintenance window, and rollback owner. Confirm platform health and no active Furas sync/checkpoint job.
2. Stop/pause Beat and Worker ingestion during the schema/code transition; drain already-running work without deleting queued jobs. Keep Furas national enumeration/removals disabled. Take and verify the backup above.
3. In a read-only repeatable-read transaction immediately before migration, repeat the 75 target checks: source namespace, target ID, canonical key, linked unmerged Master, current canonical-key collisions, existing alias collisions, and evidence references. Abort the full batch if any row drifts; do not silently apply a subset.
4. Apply migration 0026 while old code is still running or all application processes are stopped. This is additive; confirm Alembic head and both tables/constraints before deploying the new code.
5. Deploy the same reviewed backend revision to API and Worker. Do not start the new Worker while the database remains at 0025. Verify API readiness and worker import/startup while Beat remains paused.
6. With ingestion still paused, apply exactly 75 rows using the existing gated CLI and the pinned SHA-256. Use a unique batch ID and authorized actor. The transaction is all-or-nothing.
7. Verify exactly 75 active aliases and 75 `APPLIED` audit rows for the batch; resolve every provider ID to its approved SourceOpportunity ID; confirm all canonical keys and Master links unchanged; confirm counts of Masters, SourceOpportunity rows, observations and lifecycle rows unchanged; recheck both Furas flags remain disabled.
8. Run focused post-application identity checks, preserve CLI output/audit IDs and backup hash, then resume normal scheduling only under the separate change authorization. Alias deployment does not authorize a Furas pilot.

Example application command (proposal only; **not executed**):

```powershell
$env:SOURCE_IDENTITY_ALIAS_APPLICATION_ENABLED = 'true'
python scripts/manage_source_identity_aliases.py apply `
  --approved-csv docs/validation/deployment/nationwide-source-expansion/furas-identity-reconciliation-20261110/FURAS-75-APPROVED-ALIASES-20261110.csv `
  --expected-sha256 4B7B0FE7C27E3FBA2D6AFF1FB8BA10AA1CAA7BB52D4378B18608BF6B4AF646B3 `
  --expected-count 75 --source-key furas `
  --batch-id <unique-approved-batch-id> --actor <authorized-operator>
```

## Rollback and recovery

- **Batch validation or insert fails before commit:** the whole alias transaction rolls back. Confirm 0 active rows/audit rows from that attempted batch; correct no identities in place. Revalidate and seek authorization again before retry.
- **Batch committed but post-check fails:** keep ingestion paused and invoke the gated `rollback` command for the exact application batch and count 75. It deactivates all 75 mappings and appends rollback audit rows; it does not delete history or alter source/Master records. Verify all aliases are inactive/unresolvable and identity counts unchanged.
- **Code defect after migration:** keep schema at 0026. Old application code can run against the additive schema; do not downgrade after alias/audit history exists. Fix or roll back application images only under the approved window.
- **Migration failure before alias application:** transactional PostgreSQL DDL should leave the revision at 0025 on failure. Inspect version/table state before retry. Downgrade to 0025 is permitted only while alias and audit tables are empty. If schema/data integrity is uncertain, restore the verified pre-change archive only under explicit recovery authorization and maintenance; preserve the failed state and audit evidence first.

## Files and remaining conditions

- Runtime files modified in this task: **none**.
- Migration 0026 applied to production: **NO**.
- Alias rows applied to production: **NO**.
- Live backup taken: **NO**; isolated backup/restore validation passed.
- Furas national enumeration/removals: **DISABLED**.
- Furas pilot: **NO-GO** pending a separate ingestion-safety review.

**Single recommended next action:** request a separately authorized production maintenance window for the migration and 75-alias application; repeat the read-only identity preflight and take/verify the live backup inside that window before any write.
