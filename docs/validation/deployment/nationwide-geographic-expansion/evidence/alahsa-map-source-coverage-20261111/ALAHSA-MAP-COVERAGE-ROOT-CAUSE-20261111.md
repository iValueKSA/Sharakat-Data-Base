# Al-Ahsa Map Coverage Gap — Root Cause Analysis

**Date:** 2026-11-11  
**Mode:** targeted, read-only production verification  
**Result:** no production data, configuration, application, schedule, or service changes.

## Live population and API result

The live read-only API filter `GET /api/data-dashboard/geography?governorate_id=501` returned **518 Masters, 27 exact-mapped, and 491 unmapped**. A read-only SQL reconstruction of the current governorate filter also returned 518 Master IDs. Those IDs reconcile exactly with the earlier record-level exclusion audit: **491/491 same excluded IDs, zero new IDs, zero missing IDs**. The API map point set contains 27 Masters, so the API—not marker clustering or frontend marker drawing—removes the other 491 before the browser receives map points.

| Measure | Live result |
|---|---:|
| Current Al-Ahsa Governorate 501 Masters | 518 |
| Map-eligible / exact-mapped | 27 |
| Excluded from map API points | 491 |
| Excluded with Master coordinates | 491 |
| Excluded without Master coordinates | 0 |
| Excluded with linked Furas source geometry | 491 |
| Master/provenance/source coordinate disagreements | 0 |

The API field `missing_coordinates` is calculated as `total - mapped`; it therefore reports **491** even though all 491 have coordinates stored. The frontend labels this as “without verified coordinates.” In this dataset it means “not admitted to map points after the scope/provenance gates,” not “latitude/longitude absent.” This is a misleading count label, but it is not the cause of the missing markers.

## Primary root cause: scope gate blocks verified points

The exclusive record partition is:

| Class | Count | Finding |
|---|---:|---|
| `UNSPECIFIED` scope with explicit location evidence | 119 | Direct Furas geometry, matching identity/provenance, and explicit location evidence exist. The API returns no points solely because scope is `UNSPECIFIED`. High-priority adjudication candidates; not auto-approved. |
| `UNSPECIFIED` scope with source-filter evidence only | 302 | Coordinates and reviewed Furas Al-Ahsa city/source-filter evidence exist, but the record lacks the stronger explicit-location detection signal. Manual per-record scope review is required. |
| Governorate/region boundary conflict | 55 | Points intersect the saved Governorate 501 polygon but fail the saved Eastern Region 5 polygon. The combined retained hierarchy is internally inconsistent. |
| Outside saved regional boundary | 15 | All 15 have coordinates but fail the saved region polygon check. Prior targeted point checks found 12 intersect saved Governorate 511 (Al Udayd) and 3 with no saved governorate/region hit. They must not be moved or promoted without authoritative evidence. |
| **Total excluded** | **491** | **421 scope gate + 70 coordinate/boundary provenance gate.** |

The API helper `app/main.py::_verified_coordinate_points` returns an empty list immediately for `NATIONWIDE`, `REGION_WIDE`, and `UNSPECIFIED` scope. For the 421 `UNSPECIFIED` records, that happens before it evaluates the otherwise matching source coordinate provenance. This preserves the conservative scope policy, but it also blocks these point-specific candidates. The prior November 2 normalization changed legacy null scopes to `UNSPECIFIED` without changing location values; it did not mean that their coordinates were absent.

The other 70 fail the coordinate provenance gate because saved boundary validation is not `VERIFIED_IN_SAUDI`: 55 are cross-layer parent-boundary conflicts and 15 are outside the saved regional polygons. A broad boundary bypass would incorrectly promote unresolved geography.

## Source coordinates and connector behavior

For all 491 current exclusions, the stored evidence shows:

- A linked Furas `SourceOpportunity` with stable provider ID and HTTPS source URL.
- Numeric Furas geometry `x/y`; adapter code maps `x` to longitude and `y` to latitude.
- Matching Master, provenance, and Furas geometry coordinates.
- Matching source identity in the provenance record.
- No malformed or partial coordinate pair and no coordinate parsing/propagation defect detected.

The live `FurasAdapter` reads the public ArcGIS feature geometry and stores its raw attributes/geometry. The Al-Ahsa HTML connector captures card-level place text but its documented scope does not include opportunity attachment extraction. Official Furas tender PDFs do contain explicit `X`/`Y` values, including Arabic digit/decimal variants. An inspected PDF identifies the municipality, site/plot, and coordinates `Y=25.259751`, `X=49.827712`; however, the extracted document text does not contain a stable opportunity ID. It is evidence that a document-ingestion capability is absent, **not** evidence for assigning that coordinate to any current Master. The raw saved Furas point geometry does not consistently retain a separate CRS/SRID field; the audit verifies coordinate order, numeric range, and source/Master equality, but not a new CRS transformation.

## Official source checks and stable identity matching

- The public Furas opportunity page for provider ID `02-24-017001-38001` identifies Al-Ahsa Governorate Municipality and exposes a “site design map” attachment. The saved record is Master 18 and its source link uses that same stable provider ID. The indexed detail does not show numeric coordinates, while the saved public GIS geometry does.
- The official Furas investment-map page exposes an interactive investment map and municipality selector. The public Al-Ahsa opportunities portal exposes opportunity location fields and “view map” controls.
- Search-indexed official Furas PDFs confirm some tender documents include astronomical location `X/Y`. One inspected PDF did not expose a stable provider ID, so **zero** document coordinates were joined to an excluded Master by title or approximate location.
- **Record-level status:** 491 saved Furas identity/geometry matches are preserved in the attached CSV; one representative public detail page was independently corroborated by its exact provider ID. The other excluded records were not individually re-fetched from the live external portal. The browser search layer returned the official map/page records, while direct page fetch attempts were unavailable in this run; this does not affect the live database/API reconciliation.

## Pipeline trace

`Furas ArcGIS feature geometry (x/y)` → `SourceOpportunity.raw_data_json.geometry` → matching Master latitude/longitude and coordinate provenance → `_verified_coordinate_points` in `app/main.py` → `/api/data-dashboard/geography` response → `app/static/data-dashboard.js` loops through returned `data.points` and creates Leaflet markers/clusters.

The first failing stage is the API eligibility helper for the 421 scope cases; the remaining 70 fail its boundary/provenance validation. The API returns 27 points. Frontend code renders the returned point array without a second geographic eligibility filter, so **frontend rendering exclusions identified: 0**. No browser regression run was needed for this backend/API root cause.

## Candidate remediation and expected impact

| Review class | Count | Safe action | Automatic now? | Conditional map impact |
|---|---:|---|---|---:|
| Explicit-location `UNSPECIFIED` | 119 | Verify stable Furas ID, point, source text/site, municipality and approved scope policy; record a per-Master adjudication before any scope correction. | No | Up to 119 without inventing coordinates, after approval. |
| Source-filter-only `UNSPECIFIED` | 302 | Manual evidence review; confirm that Furas geometry is the physical opportunity site and that city filter semantics justify a specific location. | No | Unknown until review. |
| Parent-boundary conflicts | 55 | Reconcile against one authoritative, versioned boundary release; preserve current boundary review until then. | No | Unknown until reference is approved. |
| Outside saved region | 15 | Adjudicate against authoritative geography; specifically preserve 12 Al Udayd candidates and 3 unmatched cases. | No | Unknown; some may be outside Al-Ahsa and must not be added to its map. |

**Immediately safe additions: 0.** The 119 are evidence-backed candidates, not already-authorized corrections. Up to 421 could be reviewed without inventing coordinates only if each record’s point-as-site meaning and geographic scope are individually confirmed. Do not weaken the scope gate globally or bypass the boundary/provenance gate.

### Single recommended correction

Run an approval-only, record-level scope adjudication for the 119 explicit-location candidates first. If separately approved, correct only those specific Master scope classifications while preserving source geometry and provenance. Keep the 302 source-filter-only records in manual review and leave the 70 boundary cases excluded until the authoritative boundary issue is resolved. No production correction is authorized by this investigation.

## Evidence and status

- Record-level current CSV: [`alahsa-excluded-map-records-20261111.csv`](alahsa-excluded-map-records-20261111.csv) — 491 rows; includes Master/source IDs and references, source URLs, municipality, source and Master coordinates, provenance/boundary status, geographic scope, exact map rejection gate, and per-record review disposition.
- Prior detail audit: `docs/validation/deployment/nationwide-geographic-expansion/evidence/alahsa-record-level-audit-20261109/alahsa-map-exclusion-records-20261109.json`.
- Prior boundary analysis: `docs/validation/deployment/nationwide-geographic-expansion/ALAHSA-GEOGRAPHIC-BOUNDARY-RECONCILIATION-20261109.md`.
- Code inspected: `app/adapters.py`, `app/main.py`, `app/static/data-dashboard.js`.

```text
CURRENT_ALAHSA_MASTER_COUNT=518
CURRENT_MAP_ELIGIBLE_COUNT=27
CURRENT_EXCLUDED_COUNT=491
EXCLUDED_WITH_EXISTING_COORDINATES=491
EXCLUDED_WITHOUT_COORDINATES=0
SOURCE_GEOMETRY_NOT_PROPAGATED=0
COORDINATE_PARSING_DEFECTS=0
GEOGRAPHIC_SCOPE_FALSE_NEGATIVES=421
BOUNDARY_CONFLICTS=55
OUTSIDE_SAVED_REGION=15
OFFICIAL_FURAS_SOURCE_LINKS=491
MAP_API_EXCLUSIONS=491
FRONTEND_RENDERING_EXCLUSIONS=0
SAFELY_RECOVERABLE_NOW=0
EXPLICIT_LOCATION_CANDIDATES=119
REQUIRES_MANUAL_REVIEW=302+55+15 (plus approval for the 119 candidates)
PRODUCTION_DATA_MUTATIONS=0
CODE_OR_FRONTEND_CHANGES=0
SOURCE_SYNCHRONIZATION=NOT_RUN
```
## Public references inspected

- [Furas investment map](https://gisapps.momra.gov.sa/opportunities/) — search-indexed page shows the interactive investment map and municipality selector.
- [Furas opportunity 02-24-017001-38001](https://furas.momah.gov.sa/index.php/ar/opportunity/02-24-017001-38001?type=TempRental) — public page exposes the stable opportunity number, Al-Ahsa municipality, and site-design-map attachment.
- [Al-Ahsa opportunities portal](https://alahsa-opportunities.com/) — public listing results expose city/location and map-view controls.
- [Furas municipal tender PDF example](https://furas.momah.gov.sa/sites/default/files/176466581_%D8%A5%D9%86%D8%B4%D8%A7%D8%A1%20%D9%88%D8%AA%D8%B4%D8%BA%D9%8A%D9%84%20%D9%88%D8%B5%D9%8A%D8%A7%D9%86%D8%A9%20%D9%85%D8%B5%D9%86%D8%B9%20%20%D8%A8%D8%A7%D9%84%D9%82%D8%B7%D8%B9%D8%A9%20%D8%B1%D9%82%D9%85%207%20%D9%88%D8%A7%D9%84%D9%82%D8%B7%D8%B9%D8%A9%20%D8%B1%D9%82%D9%85%208%20%D8%A7%D9%84%D9%85%D8%AC%D9%85%D9%88%D8%B9%D8%A9%20%28.pdf) — identifies Al-Ahsa Municipality and site Y/X values; its extracted text did not provide a stable Furas opportunity ID, so it was not joined to a Master.
