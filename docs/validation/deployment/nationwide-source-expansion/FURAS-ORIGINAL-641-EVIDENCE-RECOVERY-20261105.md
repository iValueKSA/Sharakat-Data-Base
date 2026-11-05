# Furas Original 641 Evidence Recovery — 2026-11-05

**Generated at UTC:** 2026-11-05 08:22:46 UTC

**Result: UNRECOVERABLE_ORIGINAL_RECORD_EVIDENCE.** The 6,511-member capture and exact 641 unmatched provider IDs cannot be reconstructed from retained artifacts.

## Evidence reviewed

- docs/validation/deployment/nationwide-source-expansion/FURAS-NATIONAL-ENUMERATION-DRY-RUN-20261105.json and backups/national-source-scheduling/FURAS-NATIONAL-ENUMERATION-DRY-RUN-20261105.json: retain the 6,511 count, 5,870 exact-key match count, 641 difference count, and OBJECTID-membership SHA-256 f4f3e137bb97b4e2957263fed5b2fc8aebf373333c0d0d91d07cbe94c7a7aed6. Neither contains provider ID membership, raw payloads, per-record hashes, or page records.
- backups/national-source-scheduling/furas_repeat_snapshot_analysis.json and docs/validation/deployment/nationwide-source-expansion/FURAS-NATIONAL-REPEAT-DRY-RUN-20261105.json: contain the later 6,548 provider-ID list and the later 678 raw unmatched records. They do not contain the original 6,511-member set or original 641 difference.
- Read-only production PostgreSQL inspection: Furas SyncJob 694 is a successful national checkpoint with 6,484 processed provider keys and checkpoint digest e91cfe73f53184fb698ca4eec18926d196039ebd0219f27547fa706580ad74e0. It is a Nov 2 population, not the Nov 5 original capture. The current Furas source rows are 6,546, with raw SourceObservations attached to those rows; no independent 641-ID capture manifest was found.
- Relevant retained backup inventory includes database dumps/metadata through 2026-11-04 (including backups/20261104T123229Z-1ffa4f45.dump and .json); these precede the Nov 5 capture. No post-capture raw-response archive or capture manifest was present in the searched project backup locations.
- Targeted search for the original count, match count, digest, repeat digest, and capture filenames in the nationwide reports, Furas backup folder, scripts, and retained validation artifacts found only the aggregate report/digest for the original run.

## Why reconstruction is impossible

A SHA-256 digest is a one-way integrity value; it cannot recover the individual provider IDs. Current SourceOpportunity membership, job 694's older checkpoint, and the later public capture are not substitutes for the missing original ID list. The identical aggregate match count 5,870 does not prove the same 5,870 identities. Therefore no original A∩B or A−B member-level comparison is asserted, and the later 678 are never relabelled as the original 641.

## Verified retention defect and correction

The original dry-run retention path preserved aggregates and a digest but not its complete raw record set, page provenance, or member manifest. This is an evidence-retention defect.

A complete prospective 6,548-record read-only capture is now stored at docs/validation/deployment/nationwide-source-expansion/FURAS-NATIONAL-DURABLE-CAPTURE-MANIFEST-20261105.json. The reusable collector scripts/capture_furas_national_manifest.py, validator app/furas_capture_manifest.py, and isolated tests preserve typed raw fields, per-record checksums, request/page provenance, unique membership checksums, and refuse to overwrite an existing manifest. This corrects future retention; it cannot repair the historical loss.

The 6,548 capture is a **prospective baseline only**. A gate change that waives retrospective 641-record reconciliation still requires explicit approval and is not implied by this report.
