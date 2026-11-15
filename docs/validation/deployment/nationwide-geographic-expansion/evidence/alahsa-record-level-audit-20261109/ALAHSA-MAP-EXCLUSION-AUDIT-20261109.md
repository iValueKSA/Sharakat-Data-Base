# Al-Ahsa Map Exclusion Record-Level Audit — 2026-11-09

**Result:** Read-only audit complete. **No production data or application changes were made.**

## Population and exclusive classification

The current Al-Ahsa Governorate 501 API population is **518 Masters**: **27 map-eligible + 491 map-ineligible = 518**. The 491 excluded Master IDs were classified exactly once. Percentages are out of 491.

| Primary category | Count | % | Evidence / disposition |
|---|---:|---:|---|
| 1. No original coordinate evidence | 0 | 0% | All 491 have Master coordinates and linked Furas geometry; none. |
| 2. Coordinates available but unverified | 0 | 0% | No residual generic unverified-only cases after applying more specific causes. |
| 3. Conflicting coordinate evidence | 0 | 0% | No valid nonzero coordinate disagreement across Master, provenance, or linked source geometry. Existing field conflicts are mostly city/location text, not coordinate conflicts. |
| 4. Coordinates inconsistent with geography | 15 | 3.05% | Validator says outside Saudi; saved v3 Al-Ahsa and all 13 region polygons also exclude these points. Exclusion is supported by retained geography. |
| 5. Geographic evidence disconnected | 0 | 0% | Every excluded Master has linked Furas evidence with matching source identity; none disconnected. |
| 6. Possible verification or mapping defect | 421 | 85.74% | Provenance is verified, source identity matches, point is inside saved Eastern Region geometry, and coordinates match. Current map helper suppresses all 'UNSPECIFIED' scope records before evaluating provenance. Potential candidates only; no change justified without scope adjudication. |
| 7. Insufficient evidence | 55 | 11.2% | All are flagged outside Saudi by region check, yet saved Al-Ahsa Governorate 501 polygon contains the point; the saved region polygons do not. Resolve this official-layer disagreement before classifying or remapping. |
| **Total** | **491** | **100%** | Exclusive partition. |

## Record-level evidence

The companion JSON contains one row for each of the 491 Master IDs: canonical ID/title, Master coordinates and scope, source links and raw/standardized coordinate fields, complete coordinate provenance, geographic unit/evidence, saved polygon membership, map gate evidence, review records, existing field-conflict records, and historical presence/hash comparison.

Key read-only checks: **491/491** have both Master coordinates; **491** linked Furas records; **491/491** identity links match provenance; **491/491** Master points match provenance; **491/491** Master points match raw Furas geometry; **0** broken links and **0** valid nonzero coordinate conflicts.

There are **41** excluded Masters with at least one existing field conflict, including conflicts on 'city', 'location_description', and location metadata. These do not contradict coordinates. Two existing source LocationReview rows are 'REJECTED'; their reasons are preserved in the JSON and remain review evidence, not changed here.

## Historical comparison

The read-only Nov 1, 2026 baseline reports **566** total Masters, **565** Al-Ahsa-filter Masters, and **435** 'map_exact_mapped'. Of the current 491 excluded IDs, **434** were present in that snapshot; all **434** of the historically present rows with coordinates have unchanged Master latitude/longitude. **60** current exclusions have at least one Furas source payload hash matching the snapshot.

The baseline lacks a historical per-Master map eligibility list and retains source payload hashes instead of raw source coordinates. Therefore the historical aggregate cannot identify which current records were among the 435 mapped or prove that historical and current eligibility rules match. No backup was restored.

## Adjacent governorate-association check

Outside the 491 excluded set, **5 of 27 currently map-eligible Masters** have points outside the retained Governorate 501 polygon. All five carry Governorate 501 assignment and fall inside the saved Eastern Region polygon. This is a verified disagreement between filter membership and the saved governorate boundary; keep the 27/491 count reconciliation intact, but include these five IDs in the same authoritative-boundary review. Their IDs and coordinates are included in the evidence JSON.

## Defect, exclusion, and review assessment

- **Confirmed lost coordinates, broken source relationships, coordinate conflicts, or code regression:** none found in this population.
- **Potentially recoverable candidates:** the 421 verified 'UNSPECIFIED' records. Their coordinates are evidenced, but existing scope semantics intentionally exclude broad/unspecified locations. Treat as candidates for governed scope review, not approved map points.
- **Supported exclusions:** 15 points outside both governorate 501 and every saved region polygon with the existing outside-Saudi review status.
- **Unresolved geographic reviews:** 55 points where the governorate and region polygon layers disagree.
- **Correction justified now:** none. No coordinates were created, scopes changed, records linked, or validation rules relaxed.

## Recommendation

Next, perform one governed review against a single authoritative, versioned administrative boundary set: adjudicate the **421** verified 'UNSPECIFIED' scopes, reconcile the **55** Governorate-501/region-boundary disagreements, and check the **5** currently map-eligible Al-Ahsa-filter records whose points are outside the Governorate 501 polygon. Preserve current fail-closed map behavior until that review is approved.

## Validation and safety

- Exact population: **27 + 491 = 518**.
- Classification sum: **491**, with each excluded Master appearing once.
- Database access used read-only queries; no mutation statements were executed.
- No database changes, source synchronization, Docker restarts, code changes, or UI checks were performed.

## Files

- Record-level evidence: [alahsa-map-exclusion-records-20261109.json](alahsa-map-exclusion-records-20261109.json)
- Reference snapshot: [saudi-administrative-reference-20261102.json](../saudi-administrative-reference-20261102.json)
- Historical API baseline: [prechange-api-reconciliation.json](../../baseline-20261101T071825Z/prechange-api-reconciliation.json)
- Historical database baseline: [prechange-database-baseline.json](../../baseline-20261101T071825Z/prechange-database-baseline.json)
