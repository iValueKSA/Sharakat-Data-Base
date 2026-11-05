# National Map Partition — Root Cause and Targeted Remediation

**Environment:** `alahsa-local` (`local_user`)  
**Result:** `MAP_PARTITION_REMEDIATION = COMPLETE`  
**National map:** remains disabled

## Root cause

`CURRENT_MASTER_MAP_PARTITION` summed four values from the national map payload: `exact_mapped`, `outside_boundary`, `unverified_coordinates`, and `missing_coordinates`. In the payload, `missing_coordinates` is the complement of verified map Masters (`total - exact_mapped`), so it includes every unverified-coordinate Master. The DQ gate counted those 604 Masters a second time.

The original calculation was:

```text
exact_mapped                 5,889
outside_boundary                 0
unverified_coordinates         604
missing_coordinates            768  (604 unverified + 164 with no coordinates)
                              -----
original observed            7,261
expected current Masters      6,657
excess                          604
```

This was a **DQ aggregation defect**. The map projection queried one row per current Master and did not join `SourceOpportunity` or `OpportunityLocation`. It did not count duplicate Master rows. Source links are one-to-many in the database (6,769 source rows linked to 6,657 current Masters, a 112-row source-link excess), but those joins do not participate in the national map payload. The `opportunity_locations` table has 22 current linked rows and is not joined by that payload either.

The current map-eligibility counts further separate by scope: `SPECIFIC_LOCATION` has 5,889 verified, 168 unverified, and 9 without coordinates; `UNSPECIFIED` has 436 coordinate-bearing records excluded by existing scope semantics and 155 without coordinates. No current Masters have `NATIONWIDE`, `REGION_WIDE`, or `MULTIPLE_VERIFIED_LOCATIONS` scope. These scope labels remain secondary attributes; they are not added to the primary partition.

## Record-level partition

The live current population is exactly **6,657 distinct, nonmerged Master IDs**. The 604 affected IDs and per-Master membership, scope, geographic reference labels, coordinate eligibility, source-link count, and location-row count are in [the reconciliation dataset](NATIONAL-MAP-PARTITION-RECONCILIATION-20261104.json).

Before correction, the reported memberships were:

| Reported category | Master memberships | Distinct Masters | Note |
|---|---:|---:|---|
| Exact verified point | 5,889 | 5,889 | Exclusive |
| Outside reference | 0 | 0 | Exclusive |
| Unverified / map-ineligible coordinates | 604 | 604 | Exclusive against verified points |
| `missing_coordinates` complement | 768 | 768 | Includes the same 604 unverified Masters |
| **Sum** | **7,261** | **6,657 in the union** | **604 overlapping memberships** |

Original membership distribution: **0 Masters in zero categories, 6,053 in one category, 604 in multiple categories**. The exact intersection is `unverified_coordinates ∩ missing_coordinates = 604`; there is no verified/unverified or verified/missing intersection.

The corrected primary partition is:

```text
VERIFIED_COORDINATE       5,889
OUTSIDE_BOUNDARY              0
UNVERIFIED_COORDINATE       604
NO_COORDINATE               164
                           -----
PRIMARY PARTITION TOTAL   6,657
MULTI-PARTITION MASTERS       0
UNPARTITIONED MASTERS         0
```

The exclusive no-coordinate group is derived as `current_masters - exact_mapped - outside_boundary - unverified_coordinates`. The API’s reported `missing_coordinates=768` is preserved as a secondary complement and recorded in the DQ message; the DQ gate does not sum it as a second primary category.

## Map locations and joins

Current evidence recalculates **5,889 verified-coordinate Masters** and **5,889 verified source-coordinate locations**. The map projection groups them into **5,847 coordinate markers** with **5,889 Master-to-marker memberships**. Three markers contain shared coordinates; no Master appears at multiple verified map points. The national projection reports **0 outside-boundary markers**. Coordinate provenance and scope checks are unchanged; no coordinate was added, inferred, or discarded.

The map function selects current `Opportunity` rows directly, then groups only verified points from each Master’s stored coordinate provenance. Its Master total is not derived from source links, location rows, or observations. Merged Masters are excluded by `merged_into_id IS NULL`; source-only rows are not included as Masters.

## Minimal repair

The fix is in [app/data_quality.py](../../../../app/data_quality.py): the gate now derives an exclusive no-coordinate category from the current Master total after counting verified, outside-reference, and unverified categories. It rejects negative category counts or inconsistent missing-complement semantics; the failure severity and gate remain intact.

The DQ run invokes the national map projection directly when the geographic reference is ready, even while the public national-map feature flag is off. This prevents the DQ check from silently switching to the legacy local map route during acceptance. The public map route and its marker projection were not changed. **No business or geographic data was edited.**

The three focused tests in [tests/test_data_quality.py](../../../../tests/test_data_quality.py) passed. They cover the 604-member overlap, fail-closed behavior if primary categories exceed the Master universe, verified and unverified coordinates, nationwide and unspecified scope, a Master with multiple verified points, merged Master exclusion, source-link multiplicity, and map-marker grouping. Full regression completed with **693 passed, 1 skipped, 0 failed**.

## Final validation

- Full read-only DQ: **128 pass / 6 warning / 0 fail** across 134 gates. `CURRENT_MASTER_MAP_PARTITION`: **PASS**, observed 6,657, expected 6,657. Evidence: [final-dq-after-partition-fix.json](evidence/post-activation-20261104/final-dq-after-partition-fix.json).
- Current Masters: **6,657**; no new Master was created.
- Al-Ahsa Governorate 501: **518 Masters**, **0 false positives**, **0 false negatives**, **0 unresolved display memberships**. The accepted reconciliation is preserved in [ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104.json](ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104.json).
- Source regression: RCJY **3** current Masters; RCU **6**; NCP **26** under the single `ncp` identity; Ta’adeen **28** source-only records and **0** current Masters.
- RCU integrity: **0** incorrect canonical statuses, **0** incorrect canonical deadlines; **6** status and **6** deadline conflicts remain open.
- API live health **200**, readiness **200**; PostgreSQL, Redis, worker, and Beat are running and healthy/responding.
- Live flags after deployment: national UI `true`, dashboard `true`, national map `false`. Furas national enumeration and removals remain disabled.
- Task-initiated source syncs: **0**. Business-data changes: **0**.

Service, feature-flag, Master, and RCU read-only evidence is in [live-health-after-partition-fix.json](evidence/post-activation-20261104/live-health-after-partition-fix.json).

## Final fields

```text
MAP_PARTITION_REMEDIATION = COMPLETE
ROOT_CAUSE = DQ aggregation double-counted unverified Masters in missing_coordinates complement
ORIGINAL_EXPECTED = 6657
ORIGINAL_ACTUAL = 7261
ORIGINAL_EXCESS = 604
CURRENT_MASTERS = 6657
FINAL_PRIMARY_PARTITION_TOTAL = 6657
MULTI_PARTITION_MEMBERSHIP_BEFORE = 604
MULTI_PARTITION_MEMBERSHIP_AFTER = 0
UNPARTITIONED_MASTERS = 0
VERIFIED_COORDINATE_MASTERS = 5889
VERIFIED_COORDINATE_LOCATIONS = 5889
MAP_MARKERS = 5847
OUTSIDE_BOUNDARY_MARKERS = 0
BUSINESS_DATA_CHANGES = 0
MAP_QUERY_FIX = FALSE
DQ_QUERY_FIX = TRUE
CURRENT_MASTER_MAP_PARTITION = PASSED
FINAL_DQ_PASS = 128
FINAL_DQ_WARNING = 6
FINAL_DQ_FAIL = 0
REGRESSION_PASSED = 693
REGRESSION_SKIPPED = 1
REGRESSION_FAILED = 0
NATIONAL_UI_ENABLED = TRUE
NATIONAL_MAP_ENABLED = FALSE
MANUAL_SOURCE_SYNCS = 0
NEW_MASTERS_CREATED = 0
FURAS_REMOVALS_ENABLED = FALSE
```

The national map remains off. No browser acceptance or new source work was performed.
