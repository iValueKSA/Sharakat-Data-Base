# Furas Controlled Pilot Readiness — 2026-11-05

**Generated at UTC:** 2026-11-05 08:22:46 UTC

## Decision: NOT_READY

A durable complete **prospective** 6,548-record national capture is now available. It contains 6,548 unique OPPORTUNITYID values and OBJECTIDs, 66 data pages, 70 observed HTTP requests (all 200), complete pagination, request-response hashes, per-record payload hashes, an ordered capture-index hash, raw locations, raw date fields, source status, detail URLs, and page provenance. Manifest validation reconciles every record/page/request and all membership checksums.

The adjudication for the newer 678 population is complete and mutually exclusive:

| Primary classification | Count |
|---|---:|
| VERIFIED_EXISTING_SOURCE_IDENTITY | 75 |
| VERIFIED_CROSS_SOURCE_MASTER_IDENTITY | 0 |
| VERIFIED_NEW_CURRENT_SOURCE_ONLY | 0 |
| VERIFIED_NONCURRENT_SOURCE_ONLY | 0 |
| CONFIRMED_INVALID_OR_DUPLICATE_CAPTURE | 0 |
| UNRESOLVED_REVIEW_REQUIRED | 603 |
| **Total** | **678** |

The 75 identities have high-confidence evidence and proposed alias mappings to existing source rows/current Masters. The 603 unresolved records are explicitly reviewable. No new Master eligibility is established.

## Acceptance gates

- National capture complete, page and manifest integrity: **PASS**.
- Capture retention defect remedied for prospective snapshots: **PASS**; collector and validator are isolated and write-once.
- Original 6,511/641 member-level evidence: **FAIL / UNRECOVERABLE**. The missing set cannot be recovered from counts/digest, and must not be replaced by the later 678.
- Identity classification of the later 678: **PASS**, 75 verified existing identities and 603 unresolved, zero omissions.
- Alias handling: **PASS for conservative review**. Only the 75 with explicit public cross-reference and historical lineage are proposed as aliases; 271 other OBJECTID/title candidates stay unresolved.
- Master promotion: **NOT AUTHORIZED / NOT ESTABLISHED**. No new Master candidate identified.
- Isolated idempotency and fixed-fixture checkpoint recovery: results in FURAS-IDEMPOTENCY-CHECKPOINT-ACCEPTANCE-20261105.md.
- Full DQ and full isolated regression: results in the versioned national scheduling readiness update.
- Feature-flag and production safety: **PASS**; national UI/map remain enabled; Furas enumeration/removals remain disabled; no production business-data mutation occurred.

## Blockers and next stage

Do not run a controlled production pilot. Blockers:

1. Recover the original 6,511 member manifest and 641 payloads from the capture operator/archive, or submit an explicit approval request to amend that historical acceptance gate to use the 6,548 capture as a prospective baseline. The new capture cannot waive this requirement on its own.
2. Have the identity-governance owner review and approve the 75 proposed alias mappings before any production source-link/crosswalk change.
3. Resolve or formally quarantine the 603 identity reviews under approved source-only governance; keep the four cross-source-only records without Masters unpromoted.
4. Keep Furas date semantics raw until they have provider-backed definitions.

FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE
FURAS_REMOVALS_ENABLED = FALSE
FURAS_CONTROLLED_PILOT = NOT_RUN
FURAS_CONTROLLED_PILOT_READY = FALSE
