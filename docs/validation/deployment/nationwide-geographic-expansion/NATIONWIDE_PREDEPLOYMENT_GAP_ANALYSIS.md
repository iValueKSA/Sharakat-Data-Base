# Nationwide geographic expansion — predeployment gap analysis

**Reviewed:** 2026-11-01 (Asia/Amman)  
**Production status:** geography reference not verified; national UI, map, and Furas enumeration remain off. This analysis describes repository code and isolated validation, not deployed national capability.

| Capability | Status | Finding |
|---|---|---|
| Region model | IMPLEMENTED | `GeographicReferenceUnit` supports version-scoped `region` units and stable external IDs. No production unit rows exist. |
| Governorate model | IMPLEMENTED | Same versioned unit table; a governorate must have a region parent. |
| City/Center model | IMPLEMENTED | Optional `city` level; no city rows or city completeness are required for Region/Governorate Phase 1. |
| Versioned reference dataset | IMPLEMENTED | Dataset key/version is unique, SHA-256 is checked, prior versions are retained, and current version selection is explicit. |
| Provenance | IMPLEMENTED | Operator, source URL, content digest, source record, stable-ID/parent/completeness attestations, and import state are retained. |
| Licence metadata | IMPLEMENTED | License name, URL, evidence URL, and verification attestation are required by the validator. |
| Parent validation | IMPLEMENTED | Required parent, allowed parent level, unknown parent, and duplicate identities are rejected. |
| API filters | IMPLEMENTED | Country, region, governorate, city and geographic-scope parameters share the Master and source-location predicate. Unverified levels fail closed. |
| Dependent selectors | IMPLEMENTED | Region limits governorates; governorate limits cities; parent changes clear child values. Selectors remain hidden until both reference readiness and `NATIONAL_UI_ENABLED` pass. |
| URL query parameters | IMPLEMENTED | Geographic IDs and scope restore from and persist to table/dashboard URLs. |
| Search | IMPLEMENTED | Shared `q` predicate is used in table, dashboard, map and both export formats. |
| Pagination | IMPLEMENTED | Opportunity pages use `last_updated_at DESC, id DESC` for deterministic ordering. |
| CSV | IMPLEMENTED | Same geographic and search filters as the table; reference-derived geography fields remain evidence-backed. |
| XLSX | IMPLEMENTED | Same geographic and search filters as the table and CSV. |
| Dashboard | IMPLEMENTED | Geographic summary counts unique Masters, labels location memberships as non-additive, and is behind the dashboard/UI gates. |
| Map | IMPLEMENTED | National markers require verified HTTPS source coordinate provenance; broad/unknown scopes never get markers. Map code is behind the national map gate. |
| Al-Ahsa quick filter | IMPLEMENTED | Resolves governorate name through the loaded verified reference; before one is available, the current Al-Ahsa filter remains the fallback. No future ID is hardcoded. |
| National quick filter | IMPLEMENTED | “All opportunities” clears geography selectors; the national-scope shortcut filters the explicit `NATIONWIDE` scope. |
| Unknown geography handling | IMPLEMENTED | `UNSPECIFIED` is distinct from national scope; missing/unknown reference IDs do not silently map to a unit. |
| Nationwide-scope opportunity handling | IMPLEMENTED | `NATIONWIDE` is not represented as 13 locations and is not attached to every region. It appears in an unscoped national list and is omitted from physical map markers. |
| Multi-location handling | IMPLEMENTED | Verified location memberships can match unit filters; unique dashboard totals remain Master-based. Multiple verified points may display for one Master without increasing unique totals. |
| Feature flags | IMPLEMENTED | UI, map and dashboard require a ready reference plus their explicit flags. Furas enumeration remains a separate flag and is not activated by the national UI. Defaults are false. |
| Rollback | IMPLEMENTED | Imported versions are retained; rollback switches current version, preserves the imported dataset, marks it rolled back, and appends rollback provenance. Business/source records are not deleted or rewritten. |
| Deployment gating | IMPLEMENTED | Catalog/options, map, and national dashboard fail closed when schema/reference/flag readiness is absent. Production rollout still requires approval. |
| Thirteen-region source coverage | IMPLEMENTED | Migration 0025 adds source-to-region assessments. Missing assessments return `NOT_ASSESSED`; the isolated table contains zero rows. |

## Remaining blockers

- **BLOCKED_BY_REFERENCE:** No supplied official Region/Governorate roster with authorized reuse terms, effective date, stable IDs, parent relationships, and completeness evidence has passed validation. No Saudi administrative records were invented or loaded.
- **BLOCKED_BY_PRODUCTION_APPROVAL:** Migrations 0024 and 0025, code deployment, reference import, and flag changes have not been applied to production. The working tree changes are not present in the running service.
- **Operational gate:** At the latest read-only capture, the latest persisted fast DQ run had 48 PASS and 1 FAIL: `SYNC_JOB_STATE_CONSISTENCY`, sample Job 663 (AHDA). This finding remains visible and was not rerun or suppressed. Historical Furas Job 651 remains a deadlock failure. Resolve the lifecycle discrepancy and review DQ before rollout.
- **Historical migration issue:** Clean full-chain bootstrap previously fails at migration 0022 because `canonical_status` already exists. This predates geography work and remains separately documented; it was not modified here.

## Filter semantics

- Selecting a Region/Governorate/City matches only that reference unit and its descendants, plus source-preserved opportunity locations explicitly linked to units in the selected version.
- A `NATIONWIDE` opportunity has no implied physical membership in each region. Region filters do not include it unless it has an independently verified regional location.
- `UNSPECIFIED` means the opportunity is explicitly classified as having unspecified location. A missing value is not promoted to `NATIONWIDE`.
- Region and Governorate remain usable when the reference has no City/Center level. City controls are hidden or disabled in that case.
- National map extent is a viewport only. Markers require specific, verified source coordinates; region/national/unspecified scope alone cannot create points.
