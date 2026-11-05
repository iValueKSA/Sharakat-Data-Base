# Furas 641 Identity Reconciliation — 2026-11-05

## Status: PARTIAL — original record-level set is not recoverable from retained evidence

The previously accepted shadow capture recorded 6,511 provider records, 5,870 exact matches against Furas SourceOpportunity provider keys, and 641 unmatched IDs. Its retained artifact stores the population count and OBJECTID membership SHA-256 f4f3e137bb97b4e2957263fed5b2fc8aebf373333c0d0d91d07cbe94c7a7aed6, but not the member IDs or per-record payloads. The exact 641 cannot be enumerated from a one-way digest. Historic ArcGIS historicMoment requests did not restore that membership and returned the current set instead. The later repeat set has 678 unmatched IDs; it is not substituted for the original 641.

Consequently, there is no defensible mutually exclusive category count or per-record evidence for the original population. The companion classification JSON records this gap explicitly; it does not fabricate placeholders as if those were classified records.

## Identity schema and current repeat

The Furas adapter selects raw OPPORTUNITYID as the SourceOpportunity.external_id, falling back to OBJECTID only when OPPORTUNITYID is absent. Read-only comparison against the current 6,546 Furas source rows found all 6,546 keys equal raw OPPORTUNITYID; none equal raw OBJECTID; all were unique. No string/number/leading-zero normalization defect was demonstrated.

A repeat official public enumeration on 2026-11-05 returned 6,548 unique provider IDs in 69 requests with pagination complete. The current source row set had 6,546 rows: A∩B=5,870; A−B=678; B−A=676. Prior national checkpoint/job 694 represented 6,484 keys: all 6,484 remain in current rows, with 62 additional current rows outside that checkpoint. Compared with the earlier capture, the OBJECTID digest changed. Count changes are not removals or expirations.

Of 678 repeat unmatched IDs, 346 have an OBJECTID that points to exactly one existing Furas source row and have an exact title match, while the current official OPPORTUNITYID differs from the stored source key. This is a review lead, not an approved alias: provider migration/immutability and identity governance evidence were not found. No links or keys were changed. The remaining 332 have no same-OBJECTID candidate in the current Furas rows. All 678 remain IDENTITY_REVIEW_REQUIRED; no high-confidence Master link or promotion candidate is asserted.

## Safety and eligibility

Provider-key capture is deterministic and unique in the observed sets. Official raw identifiers are preserved. Lifecycle dates are not treated as reliable deadlines; geographic values remain raw evidence until reconciled to the accepted canonical geography. Master eligibility, cross-source duplicate decisions, and historical-alias classifications were not established for the missing original set. The isolated repeat report retains the 678 unmatched raw records for subsequent review.

No Furas national scheduling, removals, production sync, Master promotion, or production source-link modification occurred. Existing Masters, SourceOpportunity rows, and links were inspected read-only.

## Decision

FURAS_READY_FOR_CONTROLLED_PILOT = FALSE. The exact original unmatched IDs and their per-record payloads must first be recovered from the capture operator/archive. The 346 OBJECTID/title candidates need approved provider migration/alias evidence and a governed crosswalk decision. For every candidate considered for Master promotion, assess lifecycle, type, Saudi geography, source publication, existing Master correspondence, and source-specific eligibility. Keep all uncertain records source-only/review-required. Then rerun a read-only national dry run and idempotency/checkpoint acceptance before proposing a controlled pilot. Pilot not run.
