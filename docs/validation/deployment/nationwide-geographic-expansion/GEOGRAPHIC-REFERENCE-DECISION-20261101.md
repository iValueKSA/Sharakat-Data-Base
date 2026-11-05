# Geographic Reference Decision — 2026-11-01

## Executive decision

**We do not yet have a verified, production-usable Saudi geographic reference for Region → Governorate.** GEOSA's public geographical-names file is an aggregate feature-class summary, not an administrative-unit register. The newly located NCAR unified coding guide is the strongest region/governorate candidate: it shows 13 regions and hierarchical codes for regions, governorates and administrative centers. However, the evidence reviewed does not establish an explicit reuse license, a machine-readable complete dataset, or an unambiguous effective/version date. Do not import it or enable national selectors on this evidence.

**PHASE 1 (Region + Governorate) followed by PHASE 2 (City) remains the recommended product shape**, because city coverage need not be a prerequisite. Phase 1 cannot start production population or activation until an authoritative, reusable, versioned source is obtained and validated. No geographic rows were loaded.

## Candidate findings

### GEOSA — priority source

- GEOSA identifies the Official Saudi Map as the approved reference for national borders and administrative regions. The [2026 Official Saudi Map product page](https://geoportal.geosa.gov.sa/Geoportal/GeospatialOpenData/OfficialSaudiMap) describes a national 2D topographic map and digital GeoPDF/GeoTIFF deliverables on request. This is a map product, not a row-level region/governorate/city register; no deliverable was requested or acquired in this review.
- GEOSA's public [Open Data catalog](https://www.geosa.gov.sa/en/Pages/Open_data.aspx) includes a “Geographical Names” XLSX covering classes such as regions, governorates, centers and villages. The accessible workbook reviewed here has 93 feature-type rows with class codes and aggregate counts. It has no per-unit region/governorate/city rows, stable administrative IDs, parent IDs, or effective dataset version. Its workbook file timestamps are not evidence of an effective date.
- The catalog asks reusers to carry the copyright notice and open-data licence, but the inspected asset did not identify a dataset-specific license/evidence or a usable administrative register. Thus the generic reuse statement is insufficient to approve this file for production geography.
- GEOSA's [July 2026 notice](https://geosa.gov.sa/ar/mediacenter/news/Pages/Newas30080026.aspx) says the National Geographic Names Database was recommended as the national reference for geographical names. It does not publish the database contents, hierarchy fields, identifiers, effective version, or terms needed for this import decision.

### NCAR — new strongest region/governorate candidate

The National Center for Archives and Records [Unified Coding Guide](https://ncar.gov.sa/regions-coding) and its linked 80-page PDF are publicly viewable. The guide shows 13 regions with codes `0001`–`0013`, a region-capital entry, and four-digit codes for governorates and administrative centers. Its text says the region order follows Royal Orders, assigns sequential codes, and distinguishes governorates into two categories; page tables nest units under their region. The PDF cover says issuance 1448 and file metadata records a July 2026 document timestamp, but that is not a clearly stated effective date or version contract. No explicit dataset reuse license was identified. The PDF/UI are not a machine-readable row-level register; this review did not scrape or hand-transcribe a production dataset from them.

This is a useful official-looking candidate for a follow-up acquisition/terms inquiry, but not yet `VERIFIED_FOR_PRODUCTION`: custodian authority over the current roster, reuse terms, explicit version/effective date, and a deterministic structured extract still need confirmation. It does not resolve 150 vs 151.

### Other official/reference candidates

- **Ta’adeen GIS:** public ArcGIS layers expose 149 governorates (`Governorate_Code` values unique in the observed service snapshot), 13 emirates, and 3,661 city records. Governorate-to-region association is by `Emirates_Ar/En` names, not a parent-region key or relationship. The layer reports `FC_SOURCE=Governorate_المحافظات_2023`; observed edits are not a release/effective date. The item has no reuse license or clear custodian statement. **Role: CROSS_VALIDATION_ONLY.** Public queryability is not permission to reuse.
- **NCM TileServer:** public vector tile metadata exposes 149 governorate polygons with `Govern_ID`, `Region_ID`, Arabic/English names and 13 region polygons; TileJSON attributes the administrative boundary source to a GASTAT statistical boundaries map dated 2019-06-20. The cities tiles list 4,581 point features and a `region_id`, but do not document a governorate key; tile statistics sample values and do not prove a unique city ID roster. No current effective date or reuse license was found. **Role: CROSS_VALIDATION_OR_GEOMETRY_ONLY.**
- **Saudi National Address / SPL:** the documented Regions API returns IDs and names; the Cities API returns city IDs/names and accepts `RegionId=-1` to list all cities. Both require an access token generated from a subscription. The Cities response includes a `GovernorateName` text value, but no complete governorate lookup/register is documented. API terms govern reuse and output. No authorized subscription key was available or used. **Status: BLOCKED_ACCESS.**
- **GASTAT:** publications state 150 and 151 for different statistical products and frames. They are conflict evidence, not a geographic register.

Full candidate-level fields and evidence are in [geo-reference-candidate-matrix.json](geo-reference-candidate-matrix.json). The count analysis is in [governorate-count-conflict-analysis.md](governorate-count-conflict-analysis.md).

## Level decisions

| Level | Decision | Reason |
|---|---|---|
| Region | **NOT_VERIFIED** | NCAR lists all 13 with codes, but reuse rights, unambiguous effective/version date, and machine-readable data contract are not established. GEOSA map delivery is on request; its public names file is not a unit register. |
| Governorate | **NOT_VERIFIED** | NCAR guide provides a promising coded hierarchy, but production rights/version/completeness are not proven. Cross-check sources report 149; GASTAT statistical outputs report 150 or 151. No complete authoritative membership file reconciles these. |
| City | **NOT_VERIFIED** | GEOSA names data is aggregate; NCM tiles are not a documented complete/licensed city reference; SPL requires an authorized subscription and does not establish a city-to-governorate register. City is not a prerequisite for a future Phase 1. |

## Licence, reuse and access

GEOSA publishes generic open-data reuse conditions that require attribution and inclusion of the applicable data license; the inspected XLSX does not establish a dataset-specific license or the required administrative structure. NCAR's accessible guide has no clear reuse grant in the reviewed page/PDF. Ta’adeen and NCM publish readable GIS metadata but no applicable reuse grant was found. SPL publishes API-use terms, but requires a subscription key and its terms do not grant unrestricted reuse of all returned content. No access control was bypassed, no credentials were used, and no external inquiry was sent.

The exact next action is to request from GEOSA the structured region/governorate register (and separately confirm city availability), its dataset identifier/version and effective date, stable unit IDs and parent IDs, completeness/count statement, geometry package if needed, and the applicable license text. Ask NCAR to confirm the guide's current custodian/version and reuse rights as a cross-check. Then validate a candidate with importer fixtures and a dry-run before any separately approved import/deployment phase.

## Importer verification and safety

The existing importer was retained and narrowly strengthened: missing `effective_date` is now rejected (previously it was only a warning), and a parent link to a known unit at the wrong level is reported as `INVALID_PARENT_LEVEL`. It already rejects missing version/operator/source URL, unverified or incomplete license metadata, unattested stable IDs, duplicate IDs, missing/orphan parents, and digest mismatches. The fixed parent-level graph is acyclic by construction; attempted cycles violate a level edge and are rejected. Fixture dry-run checks confirm no database writes.

Focused test command: `python -m pytest -q tests/test_nationwide_expansion_safety.py -k reference_import` in the isolated project image — **4 passed, 13 deselected**. No unrelated regression suite was run. No live production services or database were used by the test command.

## Final status

```text
GEOGRAPHIC_REFERENCE_REGION = NOT_VERIFIED
GEOGRAPHIC_REFERENCE_GOVERNORATE = NOT_VERIFIED
GEOGRAPHIC_REFERENCE_CITY = NOT_VERIFIED

GEOSA_DATASET_FOUND = TRUE
GEOSA_DATASET_ACCESSIBLE = TRUE
GEOSA_STABLE_IDS_VERIFIED = FALSE
GEOSA_PARENT_RELATIONSHIPS_VERIFIED = FALSE
GEOSA_VERSION_VERIFIED = FALSE
GEOSA_REUSE_RIGHTS_VERIFIED = FALSE

GOVERNORATE_150_151_CONFLICT = UNRESOLVED
PHASED_REGION_GOVERNORATE_ROLLOUT_POSSIBLE = FALSE

MIGRATION_0024_PRODUCTION_APPLIED = FALSE
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE

INVEST_SAUDI_PROMOTIONS = 0
MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
BUSINESS_DATA_CHANGES = 0
REVIEW_DATA_CHANGES = 0
PRODUCTION_SCHEMA_CHANGES = 0
```

**Production changes = NONE.** The only code changes are local importer validation and fixture tests. Stop here pending approval of the next phase.
