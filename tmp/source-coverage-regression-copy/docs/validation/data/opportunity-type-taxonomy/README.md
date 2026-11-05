# Opportunity Type taxonomy — original inventory and superseded snapshot

> **Current acceptance report:** [`FINAL-RECONCILIATION.md`](FINAL-RECONCILIATION.md). The inventory and unresolved snapshot below is historical input captured before the semantic resolution. Do not use its old counts or status as current state.

**Validation snapshot:** `2026-10-18T12:24:32Z` (local PostgreSQL/API; no manual synchronization).  
**Result:** `OPPORTUNITY_TYPE_TAXONOMY_DEEP_REVIEW_NOT_COMPLETE`  
**Database:** 291 non-merged Master Opportunities, 2,898 SourceOpportunity records.  
**Standardization engine:** 8.

## Model and intended domain

`Opportunity.opportunity_type` is one nullable scalar column on each Master. There is no join table, so the stored model is **single-valued**: one eligible Master has one type slot, including a missing/unspecified slot. The source layer does not have a dedicated `SourceOpportunity.opportunity_type` column; values and their provenance live in `raw_data_json` and `standardized_data_json`. Sources may therefore carry different evidence, but the Master projection is still one value.

The defensible domain definition is: **a source-supported category describing the form in which a specific investment opportunity is offered to investors**. It must remain separate from Sector, Activity/Sub-Activity, investment/contract model, physical asset/facility/site format, publication/content category, and status. This definition is a review boundary, not an approved taxonomy: current source fields overlap these concepts, and no dedicated Opportunity Type registry exists. `Opportunity` has neither an Investment Model nor Asset/Facility Type column; those signals are currently embedded in source payloads/details. `TaxonomyMapping` is source-scoped but does not store a dimension or canonical Opportunity Type ID, so it is not a safe canonical registry for this use.

## Master cardinality and current reconciliation

The database has exactly one stored Opportunity Type slot per eligible Master. Current raw buckets and API groups sum to 291, but most groups are unmapped or dimensionally suspect; **this is not a valid canonical type reconciliation**.

| Current Master value | Count | Current API identity / label | Review result |
|---|---:|---|---|
| NULL | 116 | `opportunity_type:missing` / `قيمة مفقودة` | Missing; must display `غير محدد` |
| `TemporaryRental` | 116 | `unmapped:opportunity_type:c54099583d8e1146` | Explicit Furas enum; type vs tenure/model unresolved |
| `Investment` | 43 | `unmapped:opportunity_type:f9b21c4bda58a631` | Generic umbrella candidate; no specific type |
| `INVESTMENT_OPPORTUNITY` | 7 | `unmapped:opportunity_type:c7dabee0ed4937c9` | AHDA `content_type`; generic publication class |
| `"العربات المتنقلة"` | 2 | `unmapped:opportunity_type:ed3272cc8fa2a73b` | Asset/site format |
| `LEASE_OPPORTUNITY` | 2 | `unmapped:opportunity_type:2ceb43d708079120` | Type vs investment model/tenure unresolved |
| `"الساحات الميادين"` | 1 | `unmapped:opportunity_type:dadd03693a594466` | Asset/site format |
| `"أخرى"` | 1 | `opportunity_type:other` / `أخرى` | Existing identity is canonical syntactically; source evidence says “other” site kind, not Other opportunity type |
| `"المباني"` | 1 | `unmapped:opportunity_type:abc23e22ff22c3cb` | Asset/facility type |
| `COMMERCIAL_FACILITY_OPPORTUNITY` | 1 | `unmapped:opportunity_type:45103176229e8e8e` | Facility type vs opportunity type unresolved |
| `PPP_PROJECT` | 1 | `unmapped:opportunity_type:d3e5463c0a052382` | PPP project type vs Investment Model unresolved |
| **Total** | **291** | Current raw/API bucket total | Not semantically canonical |

Acceptance population, without guessing:

```ini
TOTAL_ELIGIBLE_MASTERS = 291
OPPORTUNITY_TYPE_IS_SINGLE_VALUED = TRUE
MASTERS_WITH_CANONICAL_OPPORTUNITY_TYPE = 0
MASTERS_WITH_UNSPECIFIED_OPPORTUNITY_TYPE = 116
MASTERS_REQUIRING_OPPORTUNITY_TYPE_REVIEW = 175
SUM_OF_CANONICAL_OPPORTUNITY_TYPE_BUCKETS = NOT RECONCILABLE
SUM_OF_CURRENT_RAW_API_BUCKETS = 291
```

`A=0` means zero current populated values are certified by an approved, dimension-safe Opportunity Type registry; it does not mean all source evidence is absent. `B=116` is the current literal NULL population only. `C=175` is every populated Master value that is not currently certified as a valid Opportunity Type. C is disjoint from A and B; the 19 Masters with explicit open Opportunity Type conflicts are included in C. The current grouping equation `116 + 1 + 174 = 291` is only a raw/API bucket equation; it must not be relabeled as a canonical sum.

## Source-level coverage and findings

| Source | Source records | Type evidence present | Current canonical type | Unresolved evidence |
|---|---:|---:|---:|---:|
| فرص (`furas`) | 177 | 177 explicit `OPPORTUNITYTYPE` values | 0 approved | 177; raw enum is `TemporaryRental` 129 / `Investment` 48; standardized projection disagrees on 13 records and substitutes Arabic Activity/Sub-Activity values |
| منصة الفرص الاستثمارية بالأحساء | 103 | 0 explicit type | 0 | 103 have no source type |
| هيئة تطوير الأحساء | 7 | 7 generic `content_type` | 0 | 7 `INVESTMENT_OPPORTUNITY` labels are a generic content class |
| استثمر في السعودية | 2,555 | 2,555 standardized type projections | 0 approved | 2,555 values across 14 labels; only 8 records link to eligible Masters. Source payload has explicit `opportunity_type` in the Opportunities family and separate `sector_name`; Project-family `type` is not captured by the current extractor. Needs family-specific schema review. |
| جامعة الملك فيصل | 6 | 6 explicit/derived content categories | 0 approved | 6: 2 `LEASE_OPPORTUNITY`, 1 `COMMERCIAL_FACILITY_OPPORTUNITY`, 3 `GENERAL_ANNOUNCEMENT`; 3 announcements do not link to eligible Masters |
| مدن (`modon`) | 0 | 0 | 0 | No stored records |
| المركز الوطني للتخصيص (`ncp`) | 45 | 45 derived `PPP_PROJECT` projections | 0 approved | 45; one source record links to an eligible Master. Payload also records PPP/contract-model evidence. |
| NHC الاستثمار (`nhc`) | 0 | 0 | 0 | No stored records |
| بوابة القطاع الخاص لصندوق الاستثمارات العامة (`pif`) | 0 | 0 | 0 | No stored records |
| موان (`mwan`) | 5 | 5 source-only semantic/type projections | 0 | 5 unlinked, outside the eligible Al-Ahsa Master population |

The full per-source value census keeps raw payload fields, raw semantic/content classes, and standardized projections in separate rows in [`source-values.csv`](source-values.csv). [`source-coverage.csv`](source-coverage.csv) has source-row and linked-Master counts. The 13-record Furas disagreement is a concrete pipeline inconsistency: the source `OPPORTUNITYTYPE` distribution is 129 + 48, while the existing standardized projection has 121 `TemporaryRental`, 43 `Investment`, 2 `أنشطة تجارة المواد الغذائية`, 3 `محلات تجارية`, and 8 missing.

## Value classifications and cross-dimension review

[`value-review.csv`](value-review.csv) classifies every distinct non-null Master value and missing value with its evidence and disposition. Source technical codes remain preserved in raw provenance. Current UI behavior only partially translates them.

| Value / group | Opportunity Type evidence | Investment Model evidence | Asset / Activity evidence | Current disposition |
|---|---|---|---|---|
| `Investment`, `INVESTMENT_OPPORTUNITY` | Furas portal class and AHDA `content_type` | None established | None | Generic; candidate for `غير محدد`, raw retained |
| `TemporaryRental` | Explicit Furas `OPPORTUNITYTYPE` | Could mean lease/tenure form; no independent investment-model field in Master | Associated site-format values appear separately | Review; do not silently canonicalize |
| `LEASE_OPPORTUNITY` | KFU explicit `opportunity_type` field | Lease can be tenure/monetization model | No physical asset implied | Review source taxonomy definition |
| `PPP_PROJECT` | NCP adapter derives it for a PPP project | NCP payload also exposes PPP/DBFOM-family model evidence | Project may include an asset, not equivalent to asset type | Review; no double assignment without approved model semantics |
| `COMMERCIAL_FACILITY_OPPORTUNITY` | KFU classifier `content_type` | None established | “Facility” is asset/facility wording; not proof of Sector=تجاري | Review; do not translate into a sector or invent an asset type |
| `الساحات الميادين`, `العربات المتنقلة`, `المباني`, quoted `أخرى` | These values occur as site-kind wording; Furas raw `OPPORTUNITYTYPE` is `TemporaryRental` | None | Asset/site/facility format evidence | Wrong dimension in Master Type; asset-type design gap remains |
| Invest Saudi sector-like labels | Source has a dedicated `opportunity_type` field for one family and a separate `sector_name`; project family has separate `category` / `type` / `activity` fields | No Master model field | Values overlap sector labels and family semantics differ | Source-scoped/family-scoped mapping required; do not globally alias from label alone |

`ASSET_TYPE_DIMENSION_GAP = TRUE` for the observed Furas site-kind values. This report does not create an Asset Type field. The exact values currently evidenced are `الساحات الميادين` (1), `العربات المتنقلة` (2), `المباني` (1), and the site-kind label `أخرى` (1). Counts are Master counts and the labels are not asserted to be a complete asset taxonomy.

## Open Opportunity Type conflicts

There are **24 open conflict rows across 19 unique Masters** for `field_name=opportunity_type`. This reconciles the previously reported “19” as distinct Master cases. Five extra rows (IDs 179, 180, 181, 187, 188) repeat the same five Furas Masters already represented by IDs 114–118; they were created on 2026-10-18 and remain open. No case was closed or rewritten during this review.

Unique-Master breakdown of the 19 cases:

- 6 Activity/Sub-Activity values in the Type slot (including `أخرى`, `منتزه`, and heavy-equipment activity labels).
- 2 Invest Saudi `Real Estate` values conflicting with Arabic activity/sub-activity evidence.
- 6 conflicting Sector/Activity labels from Al-Ahsa source reviews (`صناعي`, `تجاري`, `خدمي`).
- 5 asset/site-format values (`الساحات الميادين`, `العربات المتنقلة`, `المباني`, and asset-kind `أخرى`).

This is a dimension-specific taxonomy queue, not 19 resolved values. Each record’s conflict ID, Master, source, title, current selected value, conflicting value, source title, timestamp and state are in [`open-type-conflicts.csv`](open-type-conflicts.csv). PPP, lease, generic investment, and KFU facility enums also require classification even when they have no conflict row.

## API, dashboard, list, details and export audit

The Opportunity Type select and dashboard API expose 11 current options. For every returned option ID, the current option count equals the filtered `/api/opportunities` total (all 11 passed). The API currently uses raw or `unmapped:opportunity_type:*` IDs; the dashboard chart uses those IDs too, so there is no option/query identity mismatch. This **does not** make the values semantically canonical.

| Current API option label | Exact option ID | Option count | Query count | Match |
|---|---|---:|---:|---|
| `COMMERCIAL_FACILITY_OPPORTUNITY` | `unmapped:opportunity_type:45103176229e8e8e` | 1 | 1 | Yes |
| `Investment` | `unmapped:opportunity_type:f9b21c4bda58a631` | 43 | 43 | Yes |
| `INVESTMENT_OPPORTUNITY` | `unmapped:opportunity_type:c7dabee0ed4937c9` | 7 | 7 | Yes |
| `LEASE_OPPORTUNITY` | `unmapped:opportunity_type:2ceb43d708079120` | 2 | 2 | Yes |
| `PPP_PROJECT` | `unmapped:opportunity_type:d3e5463c0a052382` | 1 | 1 | Yes |
| `TemporaryRental` | `unmapped:opportunity_type:c54099583d8e1146` | 116 | 116 | Yes |
| `الساحات الميادين` | `unmapped:opportunity_type:dadd03693a594466` | 1 | 1 | Yes |
| `العربات المتنقلة` | `unmapped:opportunity_type:ed3272cc8fa2a73b` | 2 | 2 | Yes |
| `المباني` | `unmapped:opportunity_type:abc23e22ff22c3cb` | 1 | 1 | Yes |
| `أخرى` | `opportunity_type:other` | 1 | 1 | Yes |
| `قيمة مفقودة` | `opportunity_type:missing` | 116 | 116 | Yes |

The web filter partially translates `INVESTMENT_OPPORTUNITY`, `LEASE_OPPORTUNITY`, `PPP_PROJECT`, and `COMMERCIAL_FACILITY_OPPORTUNITY` into Arabic, but `Investment`, `TemporaryRental`, asset/site values, and `قيمة مفقودة` remain visible. It also falls back to Sector labels for some English type strings, which is not a dimension-safe registry. `/api/opportunities` details and CSV/XLSX use backend `canonical_value`, which still returns technical/raw labels for unmapped values and `قيمة مفقودة` for null. Therefore:

```ini
OPPORTUNITY_TYPE_FILTER_OPTIONS_CANONICAL_IDENTITY_OK = TRUE
OPPORTUNITY_TYPE_OPTION_COUNTS_MATCH_QUERY_COUNTS = TRUE
OPPORTUNITY_TYPE_MISSING_DISPLAY_LABEL = FAIL (currently قيمة مفقودة)
OPPORTUNITY_TYPE_OTHER_AND_UNSPECIFIED_ARE_DISTINCT = TRUE (identity only; Other semantics not valid here)
TECHNICAL_ENUMS_HIDDEN_FROM_BUSINESS_UI = FALSE
WRONG_DIMENSION_VALUES_NOT_EXPOSED_AS_OPPORTUNITY_TYPES = FALSE
```

Details and export paths are wired to the same backend canonicalization function, but the current function leaves unmapped technical values intact. The filter and chart use the same IDs; the browser has a separate partial label map. The page is RTL and had no horizontal overflow at 1920×1080 during this snapshot. Current browser evidence is [`screenshots/current-before-review.png`](screenshots/current-before-review.png) and its selector data is [`screenshots/current-before-review.json`](screenshots/current-before-review.json). No after screenshot is claimed because no taxonomy implementation was applied.

## `أخرى`, missing, identity, and provenance

`أخرى != غير محدد`: current IDs are `opportunity_type:other` versus `opportunity_type:missing`; current counts are 1 and 116. Missing is not silently mapped to Other. However, the one Other record is textually an “other” Furas site kind, not demonstrably an Other opportunity type. Also, missing displays as `قيمة مفقودة` in API/UI/exports, so the required Arabic display assertion fails.

No canonical Opportunity Type registry or alias table exists beyond the generic Other alias in the central helper. Engine v8 does not provide opportunity-type-specific missing handling, a source-scoped canonical registry, or dimension validation. Raw payloads remain separate from the current Master projection. This review performed no DB writes, no Master merge/split, no source-link edits, no review/conflict queue edits, no migration/backfill, and no manual sync. The scheduled service was left running; the latest observed job was scheduled job 323, successful at `2026-10-18T11:59:23Z` (last source success `11:59:30Z`).

## Dry run, regression and files

- Read-only snapshot only; no correction proposal was applied because asset-vs-type, lease-vs-model, and PPP-vs-model decisions are not fully established by current platform schema/source evidence.
- No changes to Sector or Activity data/code were made. Their accepted states remain documented in the existing Sector and Activity validation reports.
- Full existing backend suite: **128 passed**, one upstream Starlette/httpx deprecation warning. This is a regression baseline; it does not cover the missing Opportunity Type canonicalization behaviors and therefore is not acceptance of this taxonomy.
- The audit itself did not run ingestion, exports that write data, or scheduled sync.
- Added read-only snapshot helper [`scripts/opportunity_type_taxonomy_snapshot.py`](../../../../scripts/opportunity_type_taxonomy_snapshot.py), read-only evidence CSV/JSON files, a current-state screenshot, and this report. No application, migration, Master data, SourceOpportunity, provenance, Sector, Activity, or queue code/data changed.

## Exact acceptance blockers

1. Agree a source/family-aware Opportunity Type taxonomy and stable IDs. `PPP_PROJECT`, `LEASE_OPPORTUNITY`, `COMMERCIAL_FACILITY_OPPORTUNITY`, and `TemporaryRental` remain semantically ambiguous with models/tenure/facilities.
2. Stop the Furas standardizer from replacing 5? source Type values with Activity/Sub-Activity labels (2 food-trade + 3 shops); reconcile the 13 current raw-vs-standardized differences via a dry-run, retaining raw payload.
3. Keep `الساحات الميادين`, `العربات المتنقلة`, `المباني`, and the site-kind `أخرى` out of Opportunity Type. Decide whether a separate Asset/Site Type dimension is warranted; do not guess it into an existing business dimension.
4. Add a dimension-safe canonical registry/projection in the data-standardization layer; map missing to `غير محدد`, keep explicit Other distinct, and route unknown/wrong-dimension values to review.
5. Align Dashboard, filter IDs/options, details, CSV, XLSX and future ingestion to the same canonical type IDs and business labels; add the requested focused tests and browser verification after implementation.
6. Review the 19 unique Masters in the open Opportunity Type queue while preserving uncertainty. The live DB has 24 rows because five duplicate Furas conflict entries are present.

```ini
SECTOR_TAXONOMY_REGRESSION = PASSED (no change; baseline verified)
ACTIVITY_TAXONOMY_REGRESSION = PASSED (no change; baseline verified)
FULL_REGRESSION_SUITE = PASSED (128 passed; taxonomy acceptance assertions still blocked)
OPPORTUNITY_TYPE_TAXONOMY_DEEP_REVIEW_NOT_COMPLETE = TRUE
```
