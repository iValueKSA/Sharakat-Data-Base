# Al-Ahsa 302 Evidence Enrichment — Current-State Addendum

**Captured:** 2026-11-11 (read-only reconciliation)  
**Mode:** production read-only; no source sync, service restart, deployment, or data mutation in this verification.

## Context and baseline drift

The original evidence package was completed before the separate production correction. It remains the 302-row record-level evidence and isolated simulation result, but its pre-correction baseline is no longer the current production state. A later, separately authorized operation committed the exact 302 `geographic_scope` updates in transaction 7916. This addendum does not repeat, reverse, or authorize that operation.

## Current live state

A read-only query against `alahsa-local-db-1` found all 302 register IDs, each `SPECIFIC_LOCATION`, current/unmerged, governorate 501, parent region 5, and with no open conflict or location review. Furas linkage remained one per candidate (302/302). Eighteen records also have one additional non-Furas source link; this does not change the one-Furas-link result. Counts at capture: 6,680 Masters, 6,659 non-merged Masters, 9,470 SourceOpportunity rows, 57,661 SourceObservation rows, migration head `0026_source_identity_aliases`. No scope, identity, coordinate, or source changes were performed during this verification.

## API and simulation reconciliation

- Live `GET /api/data-dashboard/geography` returned HTTP 200, NATIONAL, 6,659 total, and 6,309 exact-mapped unique IDs. The live ID set exactly matched the prior isolated national simulation (zero set differences).
- Live `GET /api/data-dashboard/geography?governorate_id=501` returned HTTP 200, 518 records, and 447 exact-mapped unique IDs. All 145 pre-existing map-eligible IDs and all 302 register IDs are present; there are no duplicates or unexpected Al-Ahsa IDs. The current API's `missing_coordinates=71` is the unmapped complement, not a literal count of database NULL coordinate values.
- The prior isolated regression evidence reports all other-governorate eligible sets unchanged and held records unchanged. The 302 scope correction package records no independent GEOSA polygon verification; that limitation remains.

## Existing enrichment package

The earlier report and artifacts remain the detailed evidence source: [ALAHSA-302-EVIDENCE-ENRICHMENT-20261111.md](ALAHSA-302-EVIDENCE-ENRICHMENT-20261111.md), [302-row decision register](evidence/alahsa-302-evidence-enrichment-20261111/alahsa-302-record-level-decision-register.csv), targeted official feature responses, validation JSON, and isolated simulation JSON. Its decision labels mean automated recommendations from the read-only enrichment stage; the current live database has since been changed by the separately authorized transaction.

The enrichment report's UI observation remains: the governorate selector did not become usable after selecting a region, so Al-Ahsa cannot be selected through the normal UI workflow. The 145 prior IDs were exposed by the map API. No frontend code was changed. GEOSA boundary verification remains unavailable/not performed.

## Decision for this task

- `CANDIDATES_EVALUATED`: 302, using the preserved pre-correction evidence package.
- `AUTOMATED_RECOMMENDATIONS_IN_EXISTING_PACKAGE`: 302; `HELD_IN_THAT_PACKAGE`: 0.
- `CURRENTLY_UNSPECIFIED_AMONG_THOSE_302`: 0; they are already `SPECIFIC_LOCATION` in the live database following transaction 7916.
- `SIMULATED_ADDITIONAL_ELIGIBLE`: 302 in the prior isolated simulation; confirmed live API increment from its 145-ID pre-correction baseline to 447.
- `PRODUCTION_DATA_MUTATIONS_DURING_THIS_VERIFICATION`: 0.
- `FINAL_DECISION`: Evidence enrichment and API impact are documented and reconciled. Do not treat the old 302-row package as a pending correction set; the set was applied later under separate authorization. Independent GEOSA boundary validation and the governorate selector issue remain separate limitations.
