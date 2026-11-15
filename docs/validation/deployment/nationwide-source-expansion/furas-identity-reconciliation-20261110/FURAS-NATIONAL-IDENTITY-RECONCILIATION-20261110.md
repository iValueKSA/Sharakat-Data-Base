# Furas 6,548 Capture Identity Reconciliation — 2026-11-10

## Decision

**FURAS_PILOT_READINESS = NO-GO.** This read-only review accounts for all 678 unmatched IDs, with 75 high-evidence existing Furas identities proposed as aliases and 603 assigned non-overlapping review classes. The 75 proposals remain unapplied.

## Baseline and integrity

- Captured on 2026-11-05: **6,548** unique official provider IDs; exact SourceOpportunity key matches: **5,870**; unmatched: **678**. The capture manifest has 66 complete pages, 70 retained request evidence entries, complete pagination, unique provider IDs/OBJECTIDs, and verified per-record raw payload hashes and page membership.
- All 678 adjudication IDs are unique, present in the durable capture, and have a matching record SHA-256. There are no omissions or overlaps. The earlier 6,511/641 membership set was not mixed into these results.

## Mutually exclusive classification of 678

| Primary class | Count | Meaning |
|---|---:|---|
| CONFIRMED_MATCH_EVIDENCE | 75 | Official InvestSaudi reference/link plus one-to-one historical Furas lineage; existing current Master identified; alias proposal only. |
| POSSIBLE_EXISTING_FURAS_IDENTITY_MANUAL_REVIEW | 268 | Same Furas OBJECTID and exact title, but only OPPORTUNITYID differs and there is no independent alias/migration proof. |
| CONFLICTING_SOURCE_ATTRIBUTES_MANUAL_REVIEW | 3 | Same-OBJECTID candidates with changed raw description or date-related attributes; not accepted as aliases. |
| OFFICIAL_CROSS_SOURCE_REFERENCE_MASTER_UNRESOLVED | 4 | Exact official InvestSaudi opportunity number and Furas URL; no linked Master or verified historical Furas source identity. |
| INSUFFICIENT_EVIDENCE_POTENTIAL_NEW_FURAS_SOURCE | 328 | No exact current Furas key/OBJECTID candidate or exact cross-source token; a new Furas source key is possible, but Master identity is not established. |
| **Total** | **678** | **75 + 268 + 3 + 4 + 328; no duplicate classification.** |

The 603 remaining IDs reconcile as **328 potential new Furas SourceOpportunity keys + 268 possible existing Furas identities + 3 attribute-conflict reviews + 4 cross-source references without a Master = 603**. All 603 remain unresolved for activation, including the 328 potential source-only candidates. None is a confirmed new Master.

## Alias evidence review

The 75 alias proofs each require exact official InvestSaudi opportunityNumber and direct Furas link to the captured provider ID, one-to-one current Furas OBJECTID, equal geometry, stable raw attributes equal except OPPORTUNITYID/LAST_EDITED_DATE, historical observations retaining the prior provider key, and an existing unmerged/current Master. Results: confirmed evidence 75; rejected 0; conflicting evidence 0; identity manual review 0 within this 75-candidate set. Alias proposals applied: 0. Separate identity-governance approval remains required.

The separate 271 same-OBJECTID/title candidates were not elevated to alias proof: 268 lack independent official migration evidence and 3 have conflicting source attributes. Exact title/OBJECTID is not sufficient.

## Separate eligibility decisions

- **Source identity:** 75 existing identities with unapplied alias proposals; 268 possible existing; 3 conflicting; 4 cross-source-only; 328 potentially new Furas keys only. No source identity was changed.
- **Master identity:** Existing current Master evidence is present for the 75 only. The other 603 have no approved Master identity; no new Master is confirmed.
- **Geography:** Raw provider location/geometry retained, but canonical geographic eligibility was not established in the identity adjudication.
- **Lifecycle:** Raw status/date values retained. Furas date semantics remain unverified for canonical deadline, publication date, expiry, or cancellation.

## Identity rules and live activation boundary

Furas SourceOpportunity identity uses the official OPPORTUNITYID (falling back to OBJECTID only if OPPORTUNITYID is absent); the current SourceOpportunity uniqueness key is (source_id, source_opportunity_id), while MasterOpportunity is a separate entity and one Master can retain multiple source rows. Same-source fuzzy resolution is prohibited. The 75 crosswalks are proposals; no merge or link is applied. Source owner and publication platform remain separate projections. Snapshot absence is not treated as DELETED_FROM_SOURCE or CANCELLED.

A read-only environment check on 2026-11-10 found both Furas flags unset in API and scheduler containers. The application flag helper defaults unset values to false, so national enumeration and national removal reconciliation resolve false. No services were restarted.

## Safety and activation blockers

No production row, identity, link, or Master was changed; no sync/ingestion, schedule, removal, or database operation was run. Docker was used only for read-only environment inspection of two Furas flags; no service restart or container mutation occurred. The current national capture commit path calls _safe_record with allow_master_creation=false, but that guard only prevents new Master creation when no Master is resolved; exact existing-key rows can still follow the existing-Master update path. Therefore this assessment does not establish a non-mutating production pilot boundary.

Blockers: (1) 603 unresolved identities; (2) 75 provider-key aliases need governed approval and a tested reversible crosswalk; (3) 4 cross-source references lack a canonical Master; (4) 3 attribute-conflict records; (5) geography and lifecycle remain separately unresolved; (6) no reviewed proof that national ingestion can run with every production SourceOpportunity/Master mutation constrained to an approved allowlist. Furas national enumeration/removals remain disabled.

## Artifacts and reproduction

Run `node scripts/reconcile_furas_678_readonly.mjs` to revalidate the saved manifest, every raw record checksum/page membership, all 678 adjudication hashes, and regenerate the JSON/CSV below. The script has no network, database, Docker, or source-sync code.

- `FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.json` — detailed record-level findings and evidence fields.
- `FURAS-678-RECORD-LEVEL-RECONCILIATION-20261110.csv` — review queue with provider ID, proposed identity, class, support, confidence, uncertainty, next action, and raw evidence.

**Next action:** identity-governance approval and a separately tested, read-only/source-only allowlisted pilot design; do not activate Furas national scheduling or removals.
