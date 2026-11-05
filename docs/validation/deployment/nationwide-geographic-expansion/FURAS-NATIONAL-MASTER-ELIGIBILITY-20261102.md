# Furas National Master Eligibility — Dry Run — 2026-11-02

**Result: COMPLETE — read-only analysis.** This report analyzes every Furas `SourceOpportunity` currently stored in the `local_user` environment against the Job 694 snapshot, current Masters, existing source links, and configured source records. The row-level evidence is in [FURAS-NATIONAL-MASTER-ELIGIBILITY-DRY-RUN-20261102.json](FURAS-NATIONAL-MASTER-ELIGIBILITY-DRY-RUN-20261102.json).

No source was run. No business data, Master, source link, job, lifecycle state, or taxonomy was changed. National UI, map, and Furas enumeration remain disabled.

## Population and current state

| Measure | Rows |
|---|---:|
| Furas `SourceOpportunity` rows total | 6,546 |
| Members of completed Job 694 snapshot | 6,484 |
| Current snapshot members already linked to a Master | 374 |
| Current snapshot members unlinked | 6,110 |
| Non-snapshot Furas rows | 62 |
| All Furas rows already linked, including non-snapshot | 436 |
| All Furas rows unlinked | 6,110 |
| All configured-source `SourceOpportunity` rows | 9,290 |
| Source rows attached to current Masters | 591 |
| Current unmerged Masters | 566 |
| Master rows including merged history | 587 |

The completed snapshot is Job 694, with 6,484 provider IDs and digest `e91cfe73f53184fb698ca4eec18926d196039ebd0219f27547fa706580ad74e0`. The 62 rows outside that membership were retained. Sixty-one have `REMOVED_FROM_SOURCE` lifecycle evidence. One still has raw `Announced` status and only one successful missing check; it is classified non-current with LOW confidence, not as removed or cancelled.

## Classification and confidence

The required dispositions reconcile exactly to all 6,546 Furas rows. A and B follow the user’s explicit output enum: A means a proposed new Master; B means an existing Master match/link to retain.

| Disposition | Count | Treatment |
|---|---:|---|
| A_READY_NEW_MASTER | 6,057 | High-confidence proposed new Master; 87 proposals bundle a verified unlinked Invest Saudi source row with the Furas row |
| B_MATCH_EXISTING_MASTER | 374 | Retain the current Master links; no new link action proposed |
| C_IDENTITY_REVIEW | 46 | Hold for review: 41 exact official-reference candidates with owner conflicts, plus 5 Al-Ahsa Master candidates lacking resolver-approved identity evidence |
| D_NOT_QUALIFYING | 0 | No snapshot item was rejected solely for missing optional fields or the unverified query flag |
| E_READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED | 0 | All snapshot rows have explicit Furas point geometry; some administrative labels are absent |
| F_HISTORICAL_OR_NONCURRENT | 62 | Preserve all existing rows and links; 61 removed by source evidence, 1 low-confidence absence |
| G_SAME_SOURCE_DUPLICATE_REVIEW | 7 | Keep distinct provider IDs separate pending identity review |
| **Total** | **6,546** | **Reconciles** |

Confidence across all records: HIGH 6,492; MEDIUM 53; LOW 1. The `HIGH_CONFIDENCE_AUTOMATABLE` count is 6,057 because it counts new-Master actions; the 374 HIGH B cases already have links and require no incremental link write. Medium consists of 46 identity-review plus 7 same-source-review rows. The single low-confidence case is the active-looking row outside the snapshot.

The 87 exact-reference Furas/Invest Saudi pairs have the same source-verified official opportunity number and pass `compare_source_records` without a contradiction. Their Invest Saudi rows are unlinked, so the proposal is one future Master shared by two source records, not two Master creations. The other 41 exact-reference pairs conflict on normalized owner/municipality; they remain unlinked and in C. No exact official-reference match was found directly against the 566 current Masters. Five exact-title candidates against existing Al-Ahsa Masters (row IDs 8557, 8571, 8573, 4924, 4956) remain C; owner/reference support is absent and row 4956 has two Master candidates. Three exact-title parcel cases (6985, 6986, 6998) have explicit parcel conflicts and are treated as independent offers rather than matches.

Same-source review holds seven current unlinked rows: 4939, 4274, 5046, 5215, 8856, 6591, and 6770. Their different official Furas provider IDs remain intact. Evidence includes matching site names, location IDs, area, address, and/or close points; some pairs have meaningful coordinate or street differences. This supports review, not an automatic shared Master. Furas provider-key duplicate groups are zero.

## Method and matching rules

The analysis used the persisted Job 694 checkpoint for snapshot membership and verified its accepted digest. It examined all Furas rows, all non-Furas source rows, all 566 current Masters, and all currently linked source rows. Provider identity is the official Furas `OPPORTUNITYID` carried as the Furas provider key.

Candidate generation was indexed on normalized source reference and normalized core title. It then applied the current shared `compare_source_records` resolver to narrowed candidates. Same-source screening compared records only inside repeated normalized-title groups, then reviewed parcel/site/owner/area and point evidence. It did not use an all-record cross-source fuzzy product. Title similarity, shared publisher, city, sector, or municipality alone never authorized a match. A deterministic exact reference only supported an automatic shared-Master proposal when both platforms’ reference semantics were verified and the resolver reported no contradiction.

Runtime for the generated candidate screen was 58.39 seconds. The screen evaluated 128 exact trusted cross-source reference pairs; the resolver accepted 87 and blocked 41. Same-source screening compared 10,960 pairs within repeated-title groups; five strong composite candidates were inspected against site/point detail, leaving seven distinct current Furas rows in four review groups. The current-source link and Master candidate population screened was 591 linked source rows and 566 current Masters.

When evidence conflicts, source records remain separate and current canonical fields remain unchanged. Existing provenance and precedence remain authoritative; this dry run writes no field conflict or history rows. The model’s exact-reference auto-match behavior is described in [app/service.py](../../../../app/service.py) and [app/entity_resolution.py](../../../../app/entity_resolution.py).

## Itemization, source quality, and lifecycle

Every current snapshot row has a stable provider ID matching the official opportunity ID, nonempty title, public detail URL, source owner/reference, explicit point geometry, and raw `Announced` status mapped by the lifecycle model to active/available. The 6,484 rows are itemized Furas listings of types `TemporaryRental` (4,191) and `Investment` (2,293). The query-selected `QUALIFYINGOPPORTUNITY=0` flag has no local rule that makes the record non-qualifying by itself; it was not used as a rejection gate. Missing optional value, area, deadline, or owner evidence does not invalidate an otherwise identified listing.

Furas’s official [temporary rental service](https://furas.momah.gov.sa/ar/services/55400?page=1) describes temporary rental opportunities; raw source and item detail evidence remain preserved per row. `STARTDATE`, `ENDDATE`, `LASTRFPSELLDATE`, `LASTBIDATE`, and raw `DURATION` remain unverified for canonical deadline/duration semantics. No missing deadline was treated as expired, and `REMOVED_FROM_SOURCE` was not converted to cancelled.

## Geography

All counts below are for the 6,484 current snapshot records and use direct Furas fields only.

| Supported field | Deterministic records | Missing/unrecognized |
|---|---:|---:|
| Region label (`REGIONNAME`) | 6,169 | 315 |
| Governorate | 0 | No dedicated field or approved national mapping |
| City label (`CITYNAME`) | 4,258 | 2,226 |
| Explicit source point | 6,484 | 0 |
| `LOCATION_UNSPECIFIED` (no point and no usable location text) | 0 | — |

Region distribution as supplied: Asir 1,132; Eastern 824; Riyadh 787; Qassim 695; Najran 447; Madinah 446; Hail 437; Jazan 355; Makkah 320; Jawf 237; Northern Borders 210; Baha 164; Tabuk 115. The remaining 315 rows have blank or unrecognized region labels (308 blank, 7 `NA`). City values and counts are retained in the JSON using raw source labels; aliases were not collapsed. `AMANA` is treated as an issuer/administrative authority, not a Governorate. Coordinates were not reverse-geocoded, and no city, region, or governorate was inferred from a title, publisher, owner headquarters, or centroid.

Thus, zero records need the E disposition based on absence of all location evidence. This does **not** mean national administrative geography is complete: over a third lack a city label, and no governorate assignments are supported. Geography remains an attribute rather than a Master eligibility gate.

## Taxonomy and field projection

The existing source-scoped taxonomy was read without adding categories. For current snapshot rows:

- Sector mapping: 1 mapped to “أخرى”; 6,483 missing/unspecified. Raw `ActivityType` was not treated as sector.
- Activity: 1,915 mapped; 4,132 missing; 437 unmapped.
- Sub-activity: 2,023 mapped; 4,191 missing; 270 unmapped.
- Opportunity type: 4,191 `TemporaryRental` values map to “تأجير مؤقت”; 2,293 `Investment` rows remain unspecified under the accepted mapping.

The row-level JSON records current mapping status and raw source taxonomy. No new taxonomy category is proposed. For future execution, the current national adapter’s default Al-Ahsa city fallback must not be reused: use exact `CITYNAME` when present, otherwise an unspecified city value, and retain explicit Furas coordinate provenance.

## Duplicate and DQ simulation

The dry-run simulation proposes 6,057 new Masters and retains 374 existing links. Against 566 current Masters, the projected current total is **6,623**. The 87 verified cross-source pairs are the projected duplicate Masters prevented by bundling each pair into one proposed Master. The 53 medium-confidence review rows are held out; they are not counted as confirmed duplicates.

The projected DQ-style checks return zero failures:

- Duplicate Furas provider keys/groups: 0 / 0.
- Source rows assigned to multiple Masters: 0 (one Master FK per source row).
- New Masters without source provenance: 0 (each proposal is sourced; 87 proposals include the matching Invest Saudi row).
- Unsupported geographic assignments: 0.
- Automatic same-source fuzzy merges: 0.
- Current Masters without source: 0.
- Duplicate current normalized Master references: 0.
- Projected DQ FAIL: **0**.

The latest persisted full DQ result after Job 694 was 130 PASS, 4 WARNING, 0 FAIL (run `06ddabf91f804caab572e02ac8fd0458`). This task did not execute a new persisted DQ run; the zero-fail result above is a read-only simulation over the proposed output.

Existing Al-Ahsa Master rows and all 374 current Furas-to-Master links are preserved; **EXISTING_ALAHSA_MASTER_DUPLICATES_CREATED = 0**. The current 5 Al-Ahsa candidate cases are held for review and no replacement Master is proposed.

## Final controls and stop point

| Control | Result |
|---|---:|
| MANUAL_SOURCE_SYNCS | 0 |
| BUSINESS_DATA_CHANGES | 0 |
| MASTER_LINK_CHANGES | 0 |
| NATIONAL_UI_ENABLED | FALSE |
| NATIONAL_MAP_ENABLED | FALSE |
| FURAS_NATIONAL_ENUMERATION_ENABLED | FALSE |
| Job 692 / Job 694 edits | 0 |

**FURAS_MASTER_ELIGIBILITY_DRY_RUN = COMPLETE.** The deliverables are the JSON evidence file linked above and this report. Stop here for review; no promotion, linking, merging, sync, or UI/map activation was performed.

## Final status values

```text
FURAS_MASTER_ELIGIBILITY_DRY_RUN = COMPLETE
TOTAL_FURAS_ROWS = 6546
CURRENT_SNAPSHOT_FURAS_ROWS = 6484
ALREADY_LINKED_FURAS_ROWS = 436
UNLINKED_FURAS_ROWS = 6110
TOTAL_ANALYZED = 6546
READY_NEW_MASTER = 6057
READY_NEW_MASTER_GEOGRAPHY_UNSPECIFIED = 0
MATCH_EXISTING_MASTER = 374
IDENTITY_REVIEW = 46
SAME_SOURCE_DUPLICATE_REVIEW = 7
NOT_QUALIFYING = 0
HISTORICAL_OR_NONCURRENT = 62
HIGH_CONFIDENCE_AUTOMATABLE = 6057
MEDIUM_CONFIDENCE = 53
LOW_CONFIDENCE = 1
PROJECTED_NEW_MASTERS = 6057
PROJECTED_EXISTING_MASTER_LINKS = 374 (retained; incremental link writes = 0)
PROJECTED_CURRENT_MASTERS_AFTER = 6623
PROJECTED_DUPLICATES_PREVENTED = 87
DETERMINISTIC_REGION_ASSIGNMENTS = 6169
DETERMINISTIC_GOVERNORATE_ASSIGNMENTS = 0
DETERMINISTIC_CITY_ASSIGNMENTS = 4258
LOCATION_UNSPECIFIED = 0
PROJECTED_DQ_FAIL = 0
EXISTING_ALAHSA_MASTER_DUPLICATES_CREATED = 0
MANUAL_SOURCE_SYNCS = 0
BUSINESS_DATA_CHANGES = 0
MASTER_LINK_CHANGES = 0
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
```
