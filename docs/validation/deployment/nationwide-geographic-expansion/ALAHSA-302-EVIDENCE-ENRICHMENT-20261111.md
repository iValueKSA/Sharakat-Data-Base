# Al-Ahsa 302 Evidence Enrichment and Isolated Adjudication

**Captured:** 2026-11-11  
**Mode:** targeted evidence enrichment; production read-only; offline isolated simulation  
**Live platform:** http://localhost:8080/

## Decision summary

- `CANDIDATES_EVALUATED=302` (302 unique Master IDs; exact remainder of the source-filter-only group after excluding the already corrected 118, 27 previously eligible, held Master 64, 55 boundary conflicts, and 15 regional failures).
- `AUTOMATICALLY_APPROVED=302` **as an automated recommendation in this read-only package only**. This is not a human approval or a production write authorization.
- `HELD_FOR_REVIEW=0` under the supplied decision criteria and current saved Al-Ahsa boundary evidence.
- `OFFICIAL_LOCATION_EVIDENCE_VERIFIED=302/302`.
- `ADMINISTRATIVE_EVIDENCE_VERIFIED=302/302`.
- `COORDINATE_CONFLICTS=0`; `IDENTITY_CONFLICTS=0`.
- `BOUNDARY_UNCERTAINTY_CASES=0` against the currently saved Al-Ahsa/Governorate 501 boundary: all 302 existing points pass its saved point-in-boundary validation. Independent GEOSA boundary verification was **not performed** and is not claimed.
- `CURRENT_MAP_ELIGIBLE_COUNT=145`.
- `SIMULATED_ADDITIONAL_ELIGIBLE=302`.
- `SIMULATED_TOTAL_MAP_ELIGIBLE=447`.
- `ALL_APPROVED_IDS_PRESENT_IN_SIMULATED_API=YES (302/302)`.
- `OTHER_GOVERNORATE_REGRESSION=0 in the isolated test set`; the test snapshot contains only governorate 501 / region 5, so it verifies that no outside ID entered this simulation but is not a cross-governorate full-catalog test.
- `PRODUCTION_DATA_MUTATIONS=0`; source synchronization was not triggered; no production service was restarted.
- `FINAL_DECISION=EVIDENCE_ENRICHMENT_COMPLETE; APPROVAL-READY PROPOSED CORRECTION SET`. Apply only under a separate explicit production authorization after review of the package and the GEOSA boundary limitation.

The previous 118 corrections and existing 145 map-eligible Masters were not reconsidered or modified. The decision register contains exactly the 302 remaining candidates and proposes only `geographic_scope: UNSPECIFIED -> SPECIFIC_LOCATION`; coordinates, source/master identities, region and governorate IDs, and boundaries are unchanged.

## Evidence and decision method

Each candidate was revalidated against the live read-only record snapshot: the Master remains current/unmerged with scope `UNSPECIFIED`, governorate 501 and parent region 5; exactly one linked Furas source opportunity has the same provider reference; coordinates and provenance remain consistent; there are no open geographic conflicts or location reviews; and the saved Al-Ahsa polygon contains the point.

The additional source is Balady's public `InvestmentP` layer (MapServer layer 0), discovered through its published configuration. The requests were exact `OPPORTUNITYID` lookups for only these 302 registered Furas references, sent in 16 batches of at most 20 with a one-second interval. The query returned 302 unique features, one per requested provider reference. All geometries are EPSG:4326 and have usable non-null coordinates; none is `(0,0)`. For all 302, the official feature's geometry matches the linked Furas/Master coordinate within `1e-7` degrees, and the opportunity-specific `AMANA`, `BALADYA`, `CITY_ID`, `CITYNAME`, `REGION_ID`, and `REGIONNAME` values exactly match the preserved source attributes. All have `REGION_ID=005`; `AMANA` is “أمانة محافظة الأحساء” on 298 features and “أمانة الاحساء” on 4. `REGIONNAME` is “المنطقة الشرقية” on 295 and blank on 7; the stable official `REGION_ID=005` is present on all 302. The municipal attribution identifies Al-Ahsa, and locality fields provide additional site context where populated.

The source-filter membership was used only to define the candidate group; it was **not** treated as approval evidence. General publisher/owner address and inferred centroid locations were not used. No conflicting official attribution was found. The approval recommendation rests on the exact opportunity-specific official point and municipal/region fields, identity and coordinate agreement with Furas, and the existing saved-boundary check—not on coordinates alone. The public feature evidence supports an Al-Ahsa attribution but is not a substitute for an independently validated GEOSA administrative polygon. If policy requires GEOSA confirmation before any scope correction, pause production application pending that reference.

### Isolated API simulation

The simulation ran in a disposable container from the exact live API image (`sha256:1536c3e3229684fd2feee62aa3bf896c2b3d35d1bf585522abed3d7d6d62a59a`) with `--network none`. It called the deployed image's actual `app.main._national_map_payload` helper over the saved 518-row snapshot through a fake in-memory DB result; it had no production database connection. The baseline generated 145 unique mapped Master IDs and exactly matched the saved live API ID set. The in-memory-only change to the scope field for the 302 recommended IDs produced 447 mapped Masters; the only IDs added were those 302. The prior 145 remained present, held Master 64 remained excluded, all 518 records remained in the payload, no duplicate IDs appeared, coordinates/provenance/identities were unchanged, and the maximum rounding difference stayed within `1e-7`. The grouped marker count increased by 300 because some locations coincide; the eligible-record increase is 302.

The API's current output for governorate 501 reports `missing_coordinates=373`; the isolated simulation reports 71. Those figures are the complement of the API's verified mapped count (`total - mapped`), not SQL NULL coordinate counts. The read-only 518-row snapshot has non-null latitude and longitude for all 518 records (0 with either coordinate missing). Thus the present 373 are unmapped/ineligible points, including the 302 scope-gated candidates, rather than absent coordinate values.

## Narrow UI observation

The live geography catalog reports ready, with 13 region and 149 governorate options. The live filter-options response contains Al-Ahsa (`id=501`, parent `5`, 518 Masters). A fresh guest session initially shows the governorate dropdown disabled; selecting the Eastern Region applies the region filter and updates the dashboard/map, but the governorate dropdown remains disabled in the accessible UI despite the populated options. This reproduces without authentication, so it is not an Admin/Viewer permission issue. The served JavaScript includes the filter-options request and the expected enablement assignment (`governorate.disabled = !region.value`); therefore the initial disabled state is expected, but its persistence after region selection is inconsistent with the UI logic and indicates a frontend runtime/state or served-asset discrepancy. Al-Ahsa cannot currently be selected through the normal UI. The map API contains the existing 145 eligible IDs, but the normal dashboard cannot use this dropdown to isolate Al-Ahsa, so workflow accessibility of those IDs through governorate selection is blocked. No frontend code was changed.

## Reproducible artifacts

All detailed evidence is under `docs/validation/deployment/nationwide-geographic-expansion/evidence/alahsa-302-evidence-enrichment-20261111/`:

- `alahsa-302-record-level-decision-register.csv` — exactly 302 decision rows with the required fields, per-record evidence, proposed field change and simulation result (`PASS`). The value `APPROVED_FOR_GEOGRAPHIC_CORRECTION` means the automated proposed classification in this read-only package only.
- `official-balady-targeted-302-features.json` — exact batched official feature responses and provider references.
- `official-evidence-validation.json` and `adjudication-summary-final.json` — computed cross-source checks and counts.
- `live-302-revalidation.json` / `.sql` — read-only live-row revalidation and query.
- `current-alahsa-518.json` / `.sql` — read-only current population snapshot used for simulation and coordinate-null semantics.
- `live-map-api-before-simulation.json` — captured live API baseline and IDs.
- `simulated-api-eligibility.json` — actual live-image helper output, assertions, and resulting IDs.
- `ui-geography-catalog.json`, `ui-geography-filter-options.json`, and `ui-diagnosis.json` — live UI data and narrow browser observation.
- `missing-coordinates-diagnosis.json` — metric definition and observed counts.
- `simulate-302-scope-eligibility.py` and `finalize-evidence.py` — offline reproducibility scripts; neither accesses production.

## Remaining items

1. Review the 302-row register and evidence package.
2. Resolve the disabled governorate selector separately; no UI fix was in scope here.
3. Obtain/validate GEOSA boundaries if the production approval policy requires them.
4. Obtain separate authorization before any production scope update. Nothing in this run applied, staged, or deployed a correction.