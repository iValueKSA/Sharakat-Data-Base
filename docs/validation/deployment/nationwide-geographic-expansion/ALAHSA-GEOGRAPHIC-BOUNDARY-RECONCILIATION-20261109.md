# Al-Ahsa Geographic Boundary Reconciliation — 2026-11-09

**Status: PARTIAL / NO CORRECTION AUTHORIZED.** Read-only reconciliation completed using the Nov 9 record-level audit, retained Ta’adeen reference v3, targeted read-only PostgreSQL aggregates, and live anonymous point-intersection queries against Ta’adeen layers 2 and 3. The retained layers are internally inconsistent and their reuse license is unverified; they are cross-validation evidence, not a production-authoritative boundary set.

## Executive findings

- **421 UNSPECIFIED records:** not missing coordinates. All 421 have direct linked Furas geometry, matched Master/provenance coordinates, source identity, recorded region code 005, and points inside the saved Al-Ahsa 501 and Eastern 5 polygons. The November 2 system event normalized 566 null scopes to UNSPECIFIED while changing no location values. In this 421 set, 302 used SOURCE_FILTER location detection and 119 used explicit_location detection. Primary evidence buckets are mutually exclusive: 119 explicit-location records are potential eligibility-correction candidates; the other 302 source-filter records require manual review; 0 lack point/region evidence. All 421 still require authorized scope-policy review; none is approved automatically.
- **55 boundary conflicts:** all 55 points are inside the saved Al-Ahsa Governorate 501 polygon but outside its parent Eastern Region 5 polygon. The same retained snapshot has 4,347 of 8,645 Al-Ahsa outer-ring vertices outside the Eastern polygon. The records are 0.86–1.60 km from the saved regional boundary, so axis order or the average datum shift alone does not explain the mismatch. The combined hierarchy geometry is defective; this evidence does not prove which source layer is wrong.
- **15 outside-boundary records:** a live Ta’adeen REST point query intersects Governorate 511 (Al Udayd) for **12** but returns no region polygon for any of the 15. Three intersect no saved governorate or region polygon. The 12 show Al Udayd/Salwa membership rather than Al-Ahsa 501; the three remain unresolved. Do not label all 15 genuinely outside Saudi.
- **5 currently map-eligible records:** live geometry returns Governorate 511 and Eastern Region 5 for all five, although each is assigned to Governorate 501 and included in the Al-Ahsa map filter. These are high-confidence false-positive candidates for the Governorate 501 map/filter, pending approval of an authoritative boundary source.
- **Confirmed technical defect:** retained governorate and region boundaries fail parent containment, and this causes both false-negative outside-Saudi flags and incorrect Governorate 501 map membership. No coordinate identity mismatch or source-link break was found.

## Boundary source and geometry inventory

The current saved/imported dataset is 'saudi_administrative_units / taadeen-public-gis-20261102-v3', digest 'ec0f22308cc4b6960c5c39aad416f7d7dafa5c13d5b2c7afd56a13f9dc634b8b', captured November 2, 2026. It contains 13 regions, 149 governorates, and one country hierarchy row; **the country row has no geometry**. The effective date is the capture date, not a source-published release date. Governorate 501 uses layer 2 ('Governorates_المحافظات_2023'); the Eastern Region uses layer 3 ('Emirates_الحدود_الإدارية'). Their source feature classes and edit dates differ; the service offers no shared effective date or release identifier. The parent code in the saved dataset is derived from governorate source name labels ('Emirates_Ar/En'), not a native parent code field.

The Ta’adeen layer REST metadata reports native spatial reference WKID/EPSG:4204 for both layers. The stored GeoJSON is longitude/latitude EPSG:4326. A read-only comparison of the saved geometry’s first vertices with the live service 'f=geojson' and 'outSR=4326' responses matched, so no axis-order reversal was found and the WGS84 output is consistent with server reprojection. The snapshot did not retain the exact transformation operation/version. GEOSA’s national spatial reference guidance identifies Ain Al Abd as an older Saudi reference and describes a grid transformation to KSA-GRF17; transformation details therefore matter for boundary decisions.

Structural checks across the saved geometry found all 189 region rings and 338 governorate rings closed, at least four vertices, finite and within longitude/latitude ranges. Full ring self-intersection, pairwise region overlap and nationwide region-union gap analysis were not certified. The region polygon is the only Saudi-wide geometry used by this reference; the country unit has none. The point-in-polygon function uses ray casting with no distance tolerance; coordinate equality checks use a separate 1e-7 degree tolerance.

The source is an official, publicly queryable ministry GIS service ([Governorates layer](https://gis.taadeen.sa/server/rest/services/Common/BaseMaps/MapServer/2), [Emirates/Regions layer](https://gis.taadeen.sa/server/rest/services/Common/BaseMaps/MapServer/3)). Public access is not a reuse license. The imported dataset records 'license_verified=false' and no explicit license URL. The existing [geographic reference decision](../GEOGRAPHIC-REFERENCE-DECISION-20261101.md) already marks Ta’adeen as cross-validation only. GEOSA identifies the [Official Saudi Map](https://www.geosa.gov.sa/en/About/Pages/OfficialSaudiMap.aspx) as the approved national map reference; its [National Geospatial Platform](https://geosa.gov.sa/en/Pages/nationalgeospatialplatform.aspx) publishes through a rights-protecting policy, and the National Platform offers a [geospatial data request service](https://my.gov.sa/en/services/319418).

## 421 UNSPECIFIED scope adjudication

The 421 records are all legacy 'UNSPECIFIED' Masters. The read-only event 'NATIONAL_GEOGRAPHIC_SCOPE_NORMALIZATION' says 566 null scopes were set to 'UNSPECIFIED' on 2026-11-02 and 'location_values_changed=0'; promotion documentation says the 566 legacy Masters retained their old null/unspecified scope while new Furas Masters used direct point evidence. This explains the current scope gate as a preservation decision, not missing source coordinates. The prior audit confirms every one of these 421 passes all map provenance gates except scope.

| Evidence subgroup | Count | Interpretation |
|---|---:|---|
| SOURCE_FILTER detection | 302 | Point and administrative evidence exist; source-derived locality detection needs approval before scope correction. |
| explicit_location detection | 119 | Stronger textual location signal plus direct source point; still requires governed approval. |
| Raw 'SOURCE_SCOPE_AL_AHSA' + 'AL_AHSA_SUBSET_V1' | 363 | Source enumeration scope; this alone does not define each asset’s physical scope. |
| Those two raw scope fields absent | 58 | Older payloads lack those enumeration metadata fields; coordinate and administrative evidence remain present. |

All 421 have 'REGION_ID=005', 'CITY_ID' and 'CITYNAME' source fields; 408 retain the Eastern Region name. Therefore, classify them as **confirmed source-point/region evidence**, **potential eligibility correction**, and **manual approval required**. Do not change 'UNSPECIFIED' until the source owner confirms that Furas 'geometry' is a point on each opportunity asset and the approved policy defines that as 'SPECIFIC_LOCATION'. If all 421 are approved individually under that rule, the existing helper would admit up to 421 additional Masters; this is a conditional impact, not a target.

## 55 parent-boundary conflicts

The retained Al-Ahsa polygon is sourced from a 2023 governorate layer and parented by source label to Eastern 5. The Eastern polygon comes from a separate administrative-boundaries layer with different edits. All 55 audited points intersect the Governorate 501 geometry but fail Eastern polygon containment. Their Furas coordinates and Master/provenance coordinates match, and source location evidence remains linked. The live current REST spot check reproduced this split. Since the points sit at least approximately 860m outside the region polygon, a simple axis swap or a small datum conversion is not an evidence-supported root cause.

**Cause established:** cross-layer parent geometry non-containment in the retained reference. **Cause not established:** which of the governorate/region source geometries is authoritative or defective. These 55 remain manual boundary adjudications; the 43 currently SPECIFIC_LOCATION records could become candidates only after region membership is authoritatively resolved. The other 12 are also scope-blocked. No rule relaxation is proposed.

## 15 outside-boundary records

Live layer 2 intersects these IDs with Governorate 511 (Al Udayd): **70, 1618, 2005, 2693, 2988, 3066, 4205, 4208, 4601, 6330, 6382, 6540**. Their Furas descriptions/locality evidence refer to Salwa; ID 70’s original Al-Ahsa subset query used 'CITY_ID=104' and its retained review explicitly noted the location outside the local boundary. The live layer 2 does not return a region polygon for these 12, which demonstrates the same parent-geometry gap. Their current Governorate 501 association is not supported by the stored governorate geometry. Propose moving them out of the Al-Ahsa filter and assigning 511 only after authoritative reference approval.

Three records have no live governorate or region polygon hit: **2972, 5357, 5510**. They remain 'SOURCE_COORDINATE_OUTSIDE_SAUDI_REVIEW' and require manual boundary review. Some lie within about 500m of a saved region edge; others are farther. No corrected coordinates are proposed.

## 5 currently eligible boundary reviews

Live point-intersection queries return Governorate 511 (Al Udayd) and Region 5 (Eastern) for all five IDs: **5340, 6380, 6637, 6652, 6657**. All five have direct source coordinates matching Master/provenance and pass the current national region check. Their stored Governorate 501 assignments come from text evidence; raw Furas records describe Al Batha/Salwa and do not carry a city ID/name. The exact geometry hit points to Governorate 511.

These are **five likely Al-Ahsa Governorate-filter/map false positives**, not nationwide map errors. If the official source is approved, propose reassigning them from 501 to 511. They should remain eligible in the Eastern national map, while no longer appearing in the Al-Ahsa filter/map.

## Proposed correction plan (not applied)

| Class | Master IDs | Proposal | Confidence / blocker |
|---|---|---|---|
| Scope review | 421 IDs in companion evidence JSON | Review each existing direct Furas point for 'SPECIFIC_LOCATION'; approve only under an explicit policy. | High confidence in source point/region; medium for semantic scope; authorized per-record review required. |
| Al-Ahsa assignment candidates | 12 IDs listed above plus 5 eligible IDs above | Reassign from Gov 501 to Gov 511 after source and licensing confirmation. | Strong current polygon and Salwa/Al Batha evidence; saved region hierarchy is inconsistent and reuse license is unverified. |
| Parent geometry conflict | 55 IDs listed in companion evidence JSON plus the 12 Al Udayd hits | Reconcile governorate/region layers against the authoritative version; do not promote provenance yet. | Defect in combined reference confirmed; which layer should change is unresolved. |
| No polygon match | 2972, 5357, 5510 | Preserve outside-boundary review; request manual authoritative adjudication. | Insufficient evidence. |

Conditional effects: approved scope decisions could add up to 421 Masters to map eligibility; approved reassignment would remove 17 Masters from the Al-Ahsa 501 population, including 5 currently eligible markers. If the regional boundary is then authoritatively reconciled, up to 11 specific Al Udayd records among the 12 may become verified in the Eastern map. These are separate conditional effects; no aggregate target count is set. The verified current partition remains **27 eligible + 491 ineligible = 518**.

## Focused validation and remaining uncertainties

- 421/421 source point, Master coordinate, provenance and Furas identity pairs match; 421/421 saved points are inside both saved Al-Ahsa and Eastern polygons.
- 55/55 are inside saved Al-Ahsa 501 and outside saved Eastern 5; no point coordinate conflict was found.
- Live REST point queries: 12/15 outside-status points intersect Gov 511; 3/15 intersect no governorate or region; all 15 miss region polygons. Live queries also confirmed 55/55 conflict points intersect Gov 501 and miss every region polygon.
- Live REST point queries: 5/5 currently eligible records intersect Gov 511 and Eastern 5, not Gov 501.
- Geometry structure: all stored rings closed and in valid numeric lon/lat ranges. Full self-intersection, pairwise overlaps and region-union coverage were not certified; no licensed/versioned authoritative dataset was available for a final adjudication.
- No source sync, data changes, identity changes, code changes, Docker restart, or deployment occurred.

## Recommended next action

Request from GEOSA the same-release machine-readable Saudi country/region/governorate boundaries with stable codes and parent IDs, declared EPSG CRS/datum and transformation operation, effective/release date, geometry QA, and the exact reuse/display license. Then run a controlled read-only crosswalk of these 421, 55, 15 and 5 records against that release and prepare the approval-bound migration proposal.

## Evidence files

- [Record-level reconciliation JSON](evidence/alahsa-geographic-boundary-reconciliation-20261109/ALAHSA-GEOGRAPHIC-BOUNDARY-RECONCILIATION-20261109.json)
- [Prior 491-record source audit JSON](evidence/alahsa-record-level-audit-20261109/alahsa-map-exclusion-records-20261109.json)
- [Saved official-reference snapshot](evidence/saudi-administrative-reference-20261102.json)
- [Ta’adeen governorate GeoJSON snapshot](evidence/taadeen-governorates-20261102.geojson)
- [Ta’adeen region GeoJSON snapshot](evidence/taadeen-regions-20261102.geojson)
- [GEOSA SANSRS Implementation Guidelines](https://www.geoportal.sa/pdf/SANSRS_Implementation_Guidelines_V_2_0.pdf)
