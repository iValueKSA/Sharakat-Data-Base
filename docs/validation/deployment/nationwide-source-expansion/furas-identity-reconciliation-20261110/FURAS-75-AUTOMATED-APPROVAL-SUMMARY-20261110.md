# Automated Furas alias approval — 2026-11-10

## Result

**AUTOMATED_APPROVAL = PASS**. The decision engine evaluated exactly 75 proposals. Automatically approved: **75**. Held: **0**. Already applied: **0**. No alias mapping was applied to production.

| Decision | Count |
|---|---:|
| APPROVED_AUTOMATICALLY | 75 |
| HELD_INSUFFICIENT_EVIDENCE | 0 |
| HELD_IDENTITY_CONFLICT | 0 |
| HELD_COLLISION_RISK | 0 |
| HELD_MASTER_RELATIONSHIP_CONFLICT | 0 |
| ALREADY_APPLIED | 0 |
| **Total** | **75** |

## Evidence and checks

Each approved row passed the versioned deterministic checks for official source reference and direct Furas link; historical Furas provider-key observations; existing SourceOpportunity in the Furas namespace; current source and Master IDs; unmerged Master relationship; no attribute/geometry conflicts beyond OPPORTUNITYID and LAST_EDITED_DATE; unique proposal targets; traceable capture hash; and absence of an already-applied Furas key or alias mapping. No decision relied on the prior READY recommendation alone or title similarity alone.

The current identity check was a PostgreSQL transaction marked READ ONLY. It found 75 of 75 target SourceOpportunity rows in Furas source ID 1, 75 current unmerged Master rows, zero matching new Furas provider keys already present, and 0 identity alias/crosswalk tables. Furas enumeration and removals flags were both false at snapshot time.

## Decisions and artifacts

- Approved rows: [FURAS-75-APPROVED-ALIASES-20261110.csv](FURAS-75-APPROVED-ALIASES-20261110.csv)
- Held rows: [FURAS-75-HELD-ALIASES-20261110.csv](FURAS-75-HELD-ALIASES-20261110.csv)
- Full per-candidate audit: [FURAS-75-AUTOMATED-APPROVAL-AUDIT-20261110.json](FURAS-75-AUTOMATED-APPROVAL-AUDIT-20261110.json)
- Read-only live-state evidence: [FURAS-75-CURRENT-IDENTITY-STATE-SNAPSHOT-20261110.json](FURAS-75-CURRENT-IDENTITY-STATE-SNAPSHOT-20261110.json)
- Reproducible decision script: [approve_furas_75_aliases_evidence_based.mjs](../../../../../scripts/approve_furas_75_aliases_evidence_based.mjs)

The held file contains only a header when no candidates are held. Decisions are recorded as APPROVED_AUTOMATICALLY using EVIDENCE_BASED_AUTOMATED_VALIDATION under USER_AUTHORIZED_AUTOMATED_PROCESS. No human reviewer or signature is represented.

## Scope and operational status

The 603 excluded cases (268 possible existing, 3 attribute conflicts, 4 cross-source Master unresolved, 328 insufficient evidence) were not evaluated for approval or modified. The evaluator reads only their existing classification report to validate the candidate boundary.

**APPROVED_ALIAS_APPLICATION_READINESS = APPROVAL DECISIONS READY; PRODUCTION APPLICATION NOT AUTHORIZED/PENDING SEPARATE IMPLEMENTATION.** The application has no identity alias/crosswalk table, and no production mapping was applied. **FURAS_PILOT_READINESS = NO-GO**; the previously documented ingestion write-path issue remains. National enumeration and removals remain disabled. No ingestion, scheduler, service restart, migration, or production data mutation occurred.

## Focused validation

The evaluator asserted 75 unique candidate decisions, exact count reconciliation, no approved target/source/Master collisions, all approved rows passed every required rule, and zero production writes. Decision fingerprints are deterministic for the same evidence and rule version; the processing timestamp is recorded separately. **Focused result: PASS.**

## Next step

If implementation is desired, separately authorize and design a reversible, unique identity crosswalk and a safe application procedure. This approval artifact does not authorize that change.
