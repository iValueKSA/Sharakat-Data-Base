# Geographic Reference Approval Checklist

**Current status:** no production reference approved. Use this checklist against one specific candidate and one specific release. Do not infer permission, identifiers, parent links, or completeness from a public webpage or map display.

## Phase 1 — Region + Governorate

- [ ] Official source and responsible custodian confirmed
- [ ] Machine-readable dataset obtained
- [ ] Complete nationwide membership confirmed for a stated effective version
- [ ] 13 current regions confirmed
- [ ] Region IDs and official codes verified
- [ ] Governorate IDs and official codes verified
- [ ] Explicit parent Region relationships verified from fields in the dataset
- [ ] Effective date verified
- [ ] Dataset version/release identifier verified
- [ ] Reuse rights for this exact dataset/version verified in writing or applicable license
- [ ] Internal/private database use permitted
- [ ] Use in the investment-opportunities information platform permitted
- [ ] Normalization/matching permitted
- [ ] Display of names/codes in application filters permitted
- [ ] Attribution requirement recorded
- [ ] Update policy and change-notification process documented
- [ ] Historical retention/version reconciliation permitted
- [ ] Dataset checksum stored with source URL, acquisition time, and release metadata
- [ ] Dry-run import passed
- [ ] Orphan parents = 0
- [ ] Duplicate official IDs = 0 within the source's documented identity scope
- [ ] Invalid parent levels = 0
- [ ] Governorate membership is internally consistent for the same effective version
- [ ] Reported governorate count recorded as supplied by this release; no global 150/151 hardcode

## Optional Phase 2 — City / Administrative Center

- [ ] Official source and responsible custodian confirmed
- [ ] City/center IDs and codes verified
- [ ] Arabic names and English names (if supplied) verified
- [ ] Administrative type verified
- [ ] Explicit parent Governorate and Region relationships verified
- [ ] Effective date and dataset version verified
- [ ] Reuse/display/storage rights verified
- [ ] Completeness and record counts documented
- [ ] Duplicate IDs, orphan parents, invalid parent levels, and cycles = 0

## Geometry (separate, optional review)

- [ ] Geometry provenance and source authority verified
- [ ] Coordinate reference system documented
- [ ] Geometry version/effective date verified
- [ ] Geometry-specific reuse rights and attribution verified
- [ ] Geometry is not being used to infer an opportunity location absent source evidence

## GO / NO-GO

**GO for Phase 1** only when all required Phase 1 items above pass for the same dataset version. City coverage may remain `NOT_VERIFIED` and must not block Phase 1. Geometry is not required for region/governorate filtering.

**NO-GO** if reuse permission, current version/effective date, stable IDs, complete governorate membership, or explicit parent relationships are absent or ambiguous. A GO decision still requires its own import dry-run and separately authorized deployment decision; this checklist does not authorize migration 0024, import, or feature activation.

