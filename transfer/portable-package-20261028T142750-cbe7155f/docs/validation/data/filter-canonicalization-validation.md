# Filter canonicalization validation

**Validation date:** 2026-10-14  
**Scope:** Existing local production database and business filter dimensions shared by Investment Opportunities and Data Dashboard.

## Dimension audit

“Raw distinct” counts distinct nonblank Master/source labels before the read projection. “Canonical options” counts distinct selectable labels after projection; null and blank values are reported separately and are not emitted as dropdown choices. Activity and Sector are reported separately because both UI dimensions read the same `Opportunity.sector` field.

| Dimension | Raw distinct | Canonical options | Duplicate groups merged | Missing rows / note |
|---|---:|---:|---:|---|
| Activity | 20 | 19 | 1 | 124 null Master values; same backing field as Sector |
| Sector | 20 | 19 | 1 | 124 null Master values |
| Opportunity type | 19 | 18 | 1 | 124 null Master values |
| Owner | 10 | 7 | 2 | Verified municipality aliases and NCP English alias consolidated; no ambiguous groups |
| Source | 10 configured keys | 10 | 0 | Values are stable source keys |
| Publication platform | 6 | 6 | 0 | Exported Master field, not a separate dropdown |
| Location | 8 | 8 | 0 | District is null for all 289 non-merged Masters; location uses city fallback |
| City | 8 | 8 | 0 | City/locality levels retained |
| Status | 6 | 5 | 1 | `UNKNOWN` aggregated with `غير محددة` |
| Investment model | 5 | 5 | 0 | Detail/provenance only; not a filter |
| Subsector | 0 | 0 | 0 | Null for all 289 non-merged Masters; not a filter |
| District | 0 | 0 | 0 | Null for all 289 non-merged Masters |

There are six dimension-local merge groups: quoted `أخرى` with `أخرى` in Activity; the same alias in Sector; quoted `أخرى` with `أخرى` in Opportunity Type; two verified owner alias groups; and `UNKNOWN` with `غير محددة` in Status. Activity and Sector count separately because both filter dimensions were audited, even though they read the same Master field. Every observed raw value and its count is in the audit CSV.

The existing `OrganizationAlias` registry assigns `أمانة محافظة الأحساء` (source `furas`) and `Al Ahsa Municipality` to organization ID `al-ahsa-municipality`; those labels are displayed as `أمانة الأحساء`. The standalone `محافظة الأحساء` and `هيئة تطوير الأحساء` remain separate. The single NCP owner label `the Ministry of Municipalities` belongs to source record `ncp:foodsafetylabs`; its linked [official article](https://ncp.gov.sa/en/MediaCenter/News/Pages/FoodSafetyLabs.aspx) names the Ministry of Municipalities and Housing (MOMAH), so it maps to `وزارة البلديات والإسكان`. The dimension-specific Other aliases do not merge with missing values.

Review screens use workflow states for duplicate, location, qualification, taxonomy, and field-conflict decisions. These are not shared business filters; no review or conflict decision was changed. Investment model and project stage are source evidence/detail fields, not filter controls.

## Known cases

- Activity `أخرى` and quoted `"أخرى"`: **RESOLVED**, one option with aggregated count **17**.
- Owner `أمانة الأحساء`, `أمانة الاحساء`, `أمانة محافظة الأحساء`, and the registered English alias: **RESOLVED**, one option with aggregated count **267**.
- Owner `the Ministry of Municipalities` / `وزارة البلديات والإسكان`: **RESOLVED** using the source record and official NCP article; aggregated count **5**.
- Opportunity Type `أخرى` and quoted `"أخرى"`: **RESOLVED**, one option with aggregated count **17**.
- `أخرى` versus `غير محدد`: **kept separate**; missing values are not selectable options.
- `أمانة الأحساء` versus `هيئة تطوير الأحساء`: **kept separate**.
- Governorate aliases for `الأحساء` are canonicalized; city/locality names remain distinct.

## Regression validation

- Full automated test suite: **116 passed**.
- Live API options: 19 Activity/Sector labels, 18 Type labels, 7 Owner labels, 10 source keys, 8 locations, and 5 statuses; no blank labels or duplicate canonical values.
- Live canonical counts: Activity/Sector `أخرى` = **17**, Type `أخرى` = **17**, Owner `أمانة الأحساء` = **267**, and Owner `وزارة البلديات والإسكان` = **5**. Dashboard grouped counts reconcile to these values.
- Live `/api/health/ready`, `/api/health`, `/api/filters`, filtered opportunities, filtered dashboard, filtered CSV, and filtered XLSX returned HTTP **200**.
- Search `مستودع` returned **16** records; adding Activity `أخرى` narrowed the result to **4**.
- Browser audit of all six opportunities dropdowns found no duplicate values. Pagination visited all six pages (**50, 50, 50, 50, 50, 39**) and returned **289 unique IDs** with no repetition. The dashboard displayed one canonical owner bar and one Other sector bar with aggregated counts. No browser errors were observed.
- Filtered CSV for Activity `أخرى`: **17 data rows** plus the header. Filtered XLSX for Owner `أمانة الأحساء`: **267 data rows**, all displaying the canonical owner. UI export links passed their selected canonical filter to each download. Automated tests compare filtered API, CSV and XLSX populations for Activity, Owner, Type, and Industrial sector.
- Source provenance tests confirm existing `SourceOpportunity.source_owner` values remain exact and a future ingestion stores the source owner/status/payload unchanged while canonicalizing only Master fields. Review and conflict records are not modified.
- The configured scheduler remained running. No manual sync was invoked or disabled. API and worker were rebuilt/restarted after backend changes; the frontend was already on the current static build and the scheduler container was left running.

## Database safety

| Measure | Before | After | Change |
|---|---:|---:|---:|
| Opportunity rows (including merged history) | 294 | 294 | 0 |
| Non-merged Masters | 289 | 289 | 0 |
| Merged historical Masters | 5 | 5 | 0 |
| SourceOpportunity rows | 2,896 | 2,896 | 0 |
| SourceObservation rows | 7,603 | 7,603 | 0 |

No production business row or review decision was changed. Canonical Master output is a read projection; future ingestion canonicalizes only the Master representation and leaves source evidence untouched. No database migration was required. Counts were snapshotted before implementation and after the container restart on 2026-10-14; they match.

## Documentation and audit files

- Rules and alias decisions: `docs/design/filter-canonicalization.md`
- Raw value, comparison key, canonical label, count, action, reason, and confidence for every inventoried value: `docs/validation/data/filter-value-duplicate-groups.csv`
- This validation report: `docs/validation/data/filter-canonicalization-validation.md`

## Gate

`FILTER_CANONICALIZATION_COMPLETE`

All observed duplicate groups are resolved across options, filtering, dashboard aggregation, and exports. Owner aliases are explicitly verified, and all other organizations and legitimate category distinctions remain separate.

