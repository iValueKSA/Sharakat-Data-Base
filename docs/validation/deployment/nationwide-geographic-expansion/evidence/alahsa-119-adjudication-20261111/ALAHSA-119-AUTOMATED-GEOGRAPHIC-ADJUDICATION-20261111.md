# Al-Ahsa 119 Candidate Geographic Adjudication

**Date:** 2026-11-11  
**Mode:** targeted automated adjudication; production read-only  
**Decision:** `GEOGRAPHIC_119_ADJUDICATION = PASS`  
**Correction readiness:** `GEOGRAPHIC_CORRECTION_READY = YES_FOR_118_ONLY`  
**Production mutations:** 0

## Decision summary

| Result | Count |
|---|---:|
| Accepted candidate set evaluated | 119 |
| `APPROVED_FOR_GEOGRAPHIC_CORRECTION` | 118 |
| Held for manual location review | 1 (Master 64) |
| Current Al-Ahsa Masters / map-eligible Masters | 518 / 27 |
| Simulated map-eligible Masters | 145 (+118) |
| Simulated excluded Masters | 373 |
| Identity mismatches | 0 |
| Source/Master coordinate mismatches | 0 |
| Suspected coarse/placeholder coordinate held | 1 (Master 64) |
| Candidate-specific retained-boundary conflicts | 0 |
| Independent GEOSA polygon verification | unavailable for all 119; not claimed |

The 118 approvals are technical adjudications for review, not permission to apply production data changes. Master 64 remains `HELD_COORDINATE_PROVENANCE`; its saved scope and point are unchanged. All 119 are present in the row-level register.

## Evidence and method

### Candidate and live-state reconciliation

The accepted `UNSPECIFIED_SCOPE_EXPLICIT_LOCATION_CANDIDATE` class was selected from the 491-row accepted coverage artifact. It produced exactly 119 unique Master IDs and 119 unique Furas provider references. Read-only current record evidence matched all 119 to a current, non-merged Master and one linked Furas `SourceOpportunity`; all remain `UNSPECIFIED`. For each, source record identity, provider reference, source latitude/longitude, Master latitude/longitude, and preserved geometry agree. No candidate was substituted. The other 302 scope-only cases, 55 boundary conflicts, and 15 regional failures were excluded from this adjudication.

Ten candidates have existing field conflict rows. Every such row is `RESOLVED` or `RESOLVED_KEEP`; no candidate has an open geographic review or current manual-review flag that blocks this decision.

### Official source and CRS

The official Furas GIS config resolves to the `InvestmentP` ArcGIS Feature Layer, which advertises `Query` and reports spatial reference WKID 4326. The targeted, non-enumerating query requested only the 119 exact candidate `OPPORTUNITYID` values in batches. It returned 118 exact features. All 118 geometries use `x=longitude`, `y=latitude`; all match the saved SourceOpportunity and Master coordinates within 1e-7 degrees. All coordinates are in valid ranges, are non-null/non-zero, and none of the 118 approved points duplicates another approved point or a baseline map point. No CRS transformation was needed.

Furas did not return current GIS feature `26-09-2439514`. Its exact official detail URL returned HTTP 200 and embeds `(latitude 25.420393514, longitude 49.742578994)`, matching Master 97 and its preserved source geometry. That exact-reference detail evidence closes the GIS-feature gap for Master 97; it is not a title-based identity join.

For official administrative evidence, the returned features expose `AMANA`, `CITY_ID`, `CITYNAME`, and the opportunity description. Across all 119 saved exact Furas source rows, the reviewed `CITY_ID` counts are `005011001=4`, `005020001=108`, `1298=1`, `1299=2`, `1949=1`, and `9=3`. The reviewed Furas locality ID set is used only alongside the exact provider reference, point geometry, explicit source locality text, and existing parent-scoped geography assignment; municipality ownership alone was not treated as proof of the physical point. Two features have blank `CITYNAME`; their official descriptions explicitly identify Al-Omran, and their `CITY_ID=1299` and `AMANA=أمانة محافظة الأحساء` agree with the retained assignment.

### Boundary limitation

All 119 saved evidence rows report `VERIFIED_IN_SAUDI` under their retained Ta'adeen v2 point-in-region check. A separate retained Ta'adeen v3 polygon check contains all 119 in Governorate 501 and Region 5; none appears in the accepted boundary-conflict or outside-region class. GEOSA reference acquisition remains unresolved, so this run does **not** claim an independent authoritative GEOSA polygon intersection. No boundary has been replaced and no boundary rule has been weakened.

### Held record: Master 64

Master 64 / Furas `02-25-017001-83001` has source, Master, current official feature, and official detail-page geometry all at the exact whole-degree point `(25,49)`. That point is already used by live mapped Master 1500. The record describes a specific park site at Jabal Al-Shaaba, while its raw location is only “الأحساء طريق خدمة”. The shared whole-degree point is a suspected coarse/generic placeholder; the repeated official value confirms what Furas currently publishes but does not establish site-level precision. It therefore fails the no-suspected-placeholder gate and is held for manual site-coordinate evidence. No scope correction is proposed for Master 64.

## Proposed minimum correction

For the 118 approved rows only:

```text
geographic_scope: UNSPECIFIED -> SPECIFIC_LOCATION
```

`SPECIFIC_LOCATION` is an existing accepted scope value. The live API helper currently rejects `UNSPECIFIED` before checking otherwise valid point provenance. Changing only scope lets the existing `_verified_coordinate_points` and `_national_map_payload` emit the already-preserved point. Keep coordinates, SourceOpportunity and Master identities, governorate 501 and parent region 5 assignments, boundaries, source records, and eligibility code unchanged. No point or opportunity is created. Master 64 remains `UNSPECIFIED` pending review.

## Isolated API-level dry run and focused checks

The read-only live endpoint `GET /api/data-dashboard/geography?governorate_id=501` returned 518 records, 27 exact-mapped Master IDs, 26 point groups, and 491 unmapped records. The actual Master ID set was compared with the baseline generated by the API container's `app.main._verified_coordinate_points` and `_national_map_payload`; the sets matched exactly.

The dry run changed scope only on in-memory objects for the approved 118, then called those same API functions. It returned 145 exact-mapped Master IDs (27 existing + 118 approved), 144 point groups, and 373 unmapped records out of the unchanged 518. All existing 27 IDs remained; exactly the 118 approved IDs were added; Master 64 remained absent; no approved point collided with a baseline map point or another approved point. All governorate/region assignments and the 518-Master universe stayed unchanged, so no other-governorate row was promoted.

Focused assertions passed for exact candidate selection, source identity preservation, coordinate preservation, official CRS/order and source equality, retained geography assignment, API baseline ID parity, API simulation output, rejection of identity mismatch, rejection of coordinate mismatch, rejection of boundary conflict, and rejection of `UNSPECIFIED`, `REGION_WIDE`, and `NATIONWIDE` scopes. These were non-mutating assertions against the actual API helper and payload builder, plus the live read-only endpoint; no production database session was used by the simulation.

## Metric semantics recommendation

The current `missing_coordinates` / `unmapped` complement reports `total - exact_mapped`; it counts geographically ineligible records even when latitude and longitude exist. In this snapshot, the endpoint reports 491 “missing” while the accepted audit confirms all 491 exclusions have coordinates.

Expose separate, mutually interpretable measures:

1. `coordinate_values_missing`: latitude or longitude absent, malformed, or outside numeric ranges.
2. `coordinate_provenance_unverified`: values exist but source identity, direct-source evidence, or source/Master equality fails.
3. `scope_unverified`: valid source point exists but scope remains `UNSPECIFIED` or a broad scope.
4. `boundary_validation_failed`: point is outside, conflicting, or lacks required retained boundary validation.
5. `map_eligible`: unique Masters whose point passes the current API helper.
6. `not_map_eligible`: total non-merged Masters minus `map_eligible`; label this as an eligibility complement, never “missing coordinates.”

For the accepted 518 Al-Ahsa population, truly missing coordinate pairs are 0; 27 are currently map-eligible; the 491 complement consists of 421 scope-gated records and 70 boundary-gated records. If the 118 proposed scope decisions are separately applied, the expected split becomes 145 map-eligible, 303 still scope-gated (302 manual-review cases plus held Master 64), and 70 boundary-gated.

## Artifacts

- [119-row adjudication register](alahsa-119-geographic-adjudication.csv)
- [Targeted official Furas GIS features and candidate link mapping](official-furas-targeted-features.json)
- [Targeted official detail-page checks](official-furas-detail-page-checks.json)
- [Live API baseline](live-api-baseline.json)
- [Non-mutating API eligibility simulation](isolated-api-eligibility-simulation.json)
- [Focused regression results](focused-regression-results.json)
- [Machine-readable adjudication summary](adjudication-summary.json)
- Accepted input: `../alahsa-map-source-coverage-20261111/alahsa-excluded-map-records-20261111.csv`

## Final status

```text
GEOGRAPHIC_119_ADJUDICATION=PASS
CANDIDATES_EVALUATED=119
AUTOMATICALLY_APPROVED=118
HELD_FOR_REVIEW=1 (Master 64)
CURRENT_MAP_ELIGIBLE=27
SIMULATED_ADDITIONAL_MAP_ELIGIBLE=118
SIMULATED_TOTAL_MAP_ELIGIBLE=145
COORDINATE_MISMATCHES=0
SUSPECTED_COORDINATE_PLACEHOLDERS=1 (Master 64)
OTHER_GOVERNORATE_REGRESSION=NONE
GEOGRAPHIC_CORRECTION_READY=YES_FOR_118_ONLY
PRODUCTION_DATA_MUTATIONS=0
PRODUCTION_APPLICATION=NOT_AUTHORIZED / NOT PERFORMED
```

Next action: separately authorize a production data change for the 118 approved Masters after reviewing the CSV; keep Master 64 held until site-level coordinate evidence resolves the `(25,49)` anomaly.




