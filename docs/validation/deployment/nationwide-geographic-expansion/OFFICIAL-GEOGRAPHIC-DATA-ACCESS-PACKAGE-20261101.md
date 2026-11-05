# Official Geographic Data Access Package — 2026-11-01

## Decision and purpose

The production rollout remains blocked because no candidate is yet verified for Region → Governorate use. NCAR's unified coding guide is the strongest administrative coding candidate, but a machine-readable complete release, effective/version date, stable-ID contract, explicit downloadable parent keys, and dataset reuse rights remain unverified. GEOSA's accessible Geographical Names content is an aggregate class/count file rather than the required administrative register; its dataset-specific license and hierarchy are also unverified. The GASTAT 150/151 discrepancy remains unresolved and must not be resolved by guessing.

This package prepares official requests; **nothing has been submitted**. It makes no production, schema, data, sync, or backfill changes.

## Exact dataset requested

Phase 1 is a versioned, machine-readable nationwide Regions and Governorates reference. It must contain stable official IDs/codes, official Arabic names, English names where available, explicit parent-region keys, status and effective dates, a source/version identifier, completeness and record counts, update/change policy, and dataset-specific reuse/attribution terms. The complete field specification is in [REGION-GOVERNORATE-MINIMUM-DATA-SPEC.md](REGION-GOVERNORATE-MINIMUM-DATA-SPEC.md).

High-resolution boundaries are not required for Phase 1 filters. Cities/administrative centers are an optional Phase 2 with their own IDs and explicit governorate/region parents. A potential dual-authority design—NCAR for administrative codes/hierarchy and GEOSA for geographic names or geometry—is only a possibility; compatibility, versions, and rights for both sources must be confirmed before adoption.

## Prepared authority requests

### NCAR — administrative code and hierarchy

Request the complete current version of **«الدليل الموحد لترميز المناطق والمحافظات والمراكز الإدارية»**, including a machine-readable release, effective/version/update dates, stable-code guarantees, explicit Region → Governorate → Administrative Center links, counts and completeness, the current governorate total, the authority's view on the 150/151 discrepancy if within its remit, and specific permission for private database storage, platform use, normalization/matching, UI display, historical audit retention, and derived-output redistribution.

Files: [Arabic request](OFFICIAL-DATA-REQUEST-NCAR-AR.md) · [English request](OFFICIAL-DATA-REQUEST-NCAR-EN.md)

**Verified official route:** the [NCAR Contact Us page](https://ncar.gov.sa/contact-us) lists `info@ncar.gov.sa`. The official Saudi government [National Platform agency listing](https://my.gov.sa/en/agencies/17384) also lists the center's email. The contact page does not list a phone number; use the published email/contact page rather than an unverified phone listing. Recommended route: email the request to `info@ncar.gov.sa`, with the regions-coding guide title in the subject, or submit through the official contact form. No service portal for this specific data request was identified.

### GEOSA — geographic names, dataset-specific reuse rights, and optional geometry

Request the structured record-level **“Geographical Names”** dataset, exact applicable Open Data license, identifiers and parent links, completeness/counts, release/effective/update policy, required attribution, and written clarification of storage, organizational/commercial platform use, transformation, display, caching, retention, and derived-output redistribution. Request boundaries separately if available. Explicitly ask whether a separate geospatial-activity permit is required; do not treat that permit as the dataset reuse license.

Files: [Arabic request](OFFICIAL-DATA-REQUEST-GEOSA-AR.md) · [English request](OFFICIAL-DATA-REQUEST-GEOSA-EN.md)

**Verified official routes:** GEOSA's [Contact Us page](https://www.geosa.gov.sa/ar/Pages/Contact-us.aspx) lists `care@geosa.gov.sa` and the unified phone `199066`, and provides a contact form. Its [Digital Geospatial Services Portal](https://www.geosa.gov.sa/ar/Pages/GEOSAServicesPortal.aspx) describes online geospatial product requests. Recommended route: send the data/license inquiry to the beneficiary-services email or contact form; use the portal only if GEOSA directs the request to a product-request service. Clarify that the inquiry is for dataset reuse terms, not a geospatial activity license.

## What would constitute GO

Use the [approval checklist](GEOGRAPHIC-REFERENCE-APPROVAL-CHECKLIST.md) against one specific dataset version. Phase 1 GO requires:

- Confirmed official source/custodian and a complete machine-readable version with 13 current regions.
- Stable region and governorate IDs/codes and explicit parent Region keys.
- Same-version complete governorate membership, effective date, release identifier, update policy, and recorded counts.
- Documented reuse rights for internal storage, platform use, normalization/matching, UI display, audit retention, attribution, and intended derived outputs.
- Deterministic fixture/dry-run validation: zero duplicate IDs, orphan parents, invalid parent levels, and other critical hierarchy errors.

Responses that omit the applicable license, effective version/date, stable IDs, complete governorate membership, or explicit parent links remain **NO-GO**. A request response saying only “publicly viewable” or linking to a map is not a reuse grant or complete dataset. The 150/151 statistic does not itself block use of a clearly versioned authoritative roster, but the chosen release's explicit membership and total must be recorded.

## Independent city phase

Region + Governorate can proceed independently of City once their own data, rights, and validation pass. City may remain `NOT_VERIFIED`; it must not be fabricated from text labels or inferred from coordinates/owner location. The current reference is not yet sufficient for Phase 1, so activation remains pending official data and written/license evidence.

## Status

```text
GEOGRAPHIC_REFERENCE_REGION = NOT_VERIFIED
GEOGRAPHIC_REFERENCE_GOVERNORATE = NOT_VERIFIED
GEOGRAPHIC_REFERENCE_CITY = NOT_VERIFIED

NCAR_REQUEST_READY = TRUE
GEOSA_REQUEST_READY = TRUE
REGION_GOVERNORATE_MINIMUM_DATA_SPEC_READY = TRUE
OFFICIAL_CONTACT_ROUTES_VERIFIED = TRUE
PHASED_REGION_GOVERNORATE_ROLLOUT_POSSIBLE = PENDING_OFFICIAL_REFERENCE

MIGRATION_0024_PRODUCTION_APPLIED = FALSE
NATIONAL_UI_ENABLED = FALSE
NATIONAL_MAP_ENABLED = FALSE
FURAS_NATIONAL_ENUMERATION_ENABLED = FALSE

MANUAL_SOURCE_SYNCS = 0
BACKFILLS = 0
BUSINESS_DATA_CHANGES = 0
REVIEW_DATA_CHANGES = 0
PRODUCTION_SCHEMA_CHANGES = 0
APPLICATION_CODE_CHANGES = 0
```

**Stop condition met:** the official data-access package is ready for the user to submit. No request was sent and no implementation work should resume until official reference data or written authorization is obtained.

