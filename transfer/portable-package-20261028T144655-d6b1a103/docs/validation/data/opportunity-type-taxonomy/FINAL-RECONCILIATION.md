# Opportunity Type taxonomy — final semantic reconciliation

**Decision snapshot:** `2026-10-18T13:23:28.356773Z` (local PostgreSQL; no manual synchronization).  
**Engine:** `11`  
**Result:** `OPPORTUNITY_TYPE_TAXONOMY_DEEP_REVIEW_COMPLETE`, with 14 explicitly open source/dimension review cases.

## Domain semantics

- **Opportunity Type:** the source-supported business form/category of the offer presented to investors. A Master has one scalar Type slot. In this inventory, the sole confirmed differentiating Type is Furas temporary rental.
- **Investment Model:** how the offer is contracted or monetized (for example lease, operating contract, PPP/DBFOM/EOMT). There is no Master-level model column in the current schema; proven source-specific model signals remain in `SourceOpportunity.standardized_data_json.fields.investment_model` for the later Investment Model review.
- **Asset / Facility Type:** the physical site or facility involved. Furas `LOCATIONTYPE` is kept as source-level `asset_type_candidate`; KFU's one `مرفق تجاري` classifier is kept separately. There is no shared, approved cross-source Asset Type registry today.
- **Sector:** broad economic sector. **Activity/Sub-Activity:** the business operation carried out at the site. Neither is used as Type.
- **Publication/content class** and **status** are also separate dimensions.

`Opportunity.opportunity_type` is nullable scalar storage; there is no Type assignment join table. Missing and undetermined values use `opportunity_type:missing` and the business label `غير محدد`. `أخرى` keeps the distinct identity `opportunity_type:other`; it is not used as the fallback for missing Type.

## Canonical taxonomy and mappings

| Canonical ID | Arabic label | Approved input and scope | Decision |
|---|---|---|---|
| `opportunity_type:temporary_rental` | تأجير مؤقت | Furas `attributes.OPPORTUNITYTYPE` = `TemporaryRental` or `TempRental` | Mapped; source-scoped |
| `opportunity_type:missing` | غير محدد | missing Type, generic publication classes, unresolved or unsupported values | Stable unspecified bucket |

The Furas government service page describes temporary rental as reservation of investment sites for 1–180 days; an official Furas opportunity page is titled “تأجير مؤقت” and carries `type=TempRental`. These source definitions establish a real offer category while its duration/contract remains a separate commercial attribute. [Furas temporary rental service](https://furas.momah.gov.sa/ar/services/55400?page=1), [Furas opportunity example](https://furas.momah.gov.sa/ar/opportunity/02-26-011001-17001?type=TempRental).

Raw Furas `Investment` (48 source records), AHDA `INVESTMENT_OPPORTUNITY` (7 generic `content_type` records), and all other non-approved Type signals remain unspecified. `TemporaryRental` from a non-Furas source does not inherit the Furas alias. Missing input never maps to `أخرى`.

## Required enum and asset resolutions

| Raw value | Source meaning | Final dimension | Canonical value | Raw preserved? |
|---|---|---|---|---|
| `PPP_PROJECT` (NCP adapter projection; raw `content_type=PPP_PROJECT_ANNOUNCEMENT`, 45 records) | NCP project/announcement class; payload separately carries contract-model evidence | Source/project class; Investment Model only when explicit model field exists | Type = `غير محدد`; models such as PPP/BOOT/DBFOM/EOMT/ROMT retained separately | Yes |
| `LEASE_OPPORTUNITY` (KFU, 2) | KFU notice classification for lease-based offer | Investment Model / tenure | Type = `غير محدد`; model = `تأجير` | Yes |
| `COMMERCIAL_FACILITY_OPPORTUNITY` (KFU, 1) | Adapter-derived classifier for a commercial facility/service notice; the notice describes a three-year contract but does not identify the contract mechanism | Asset candidate; Investment Model remains review-required | Type = `غير محدد`; candidate = `مرفق تجاري`; no model or Sector inferred | Yes |
| `INVESTMENT_OPPORTUNITY` (AHDA, 7) | Generic content class describing the site-wide publication | Publication class | Type = `غير محدد` | Yes |
| `الساحات الميادين` | Furas `LOCATIONTYPE`, a site format | Asset/site candidate | Type comes from Furas `OPPORTUNITYTYPE`; not a Type alias | Yes |
| `العربات المتنقلة` | Furas `LOCATIONTYPE`, a site format | Asset/site candidate | Type comes from Furas `OPPORTUNITYTYPE`; not a Type alias | Yes |
| `المباني` | Furas `LOCATIONTYPE`, a site format | Asset/site candidate | Type comes from Furas `OPPORTUNITYTYPE`; not a Type alias | Yes |

**Asset Type decision:** `ASSET_TYPE_DIMENSION_REQUIRED = FALSE` for this implementation. Furas has the only reviewed, explicit structured site-kind taxonomy. The one KFU “commercial facility” result is an adapter-derived notice class, not a comparable second source taxonomy. Creating a Master column now would imply unsupported cross-source equivalence. Candidate values are preserved in derived review metadata; no migration was made.

| Asset-like candidate | Source | Source records | Linked Masters |
|---|---|---:|---:|
| أخرى | Furas | 10 | 10 |
| الأراضي | Furas | 8 | 8 |
| الحدائق | Furas | 23 | 23 |
| الساحات الميادين | Furas | 3 | 3 |
| الساحات الميادين + الطرق والأرصفة | Furas | 2 | 2 |
| الشواطئ والواجهات | Furas | 11 | 11 |
| الطرق والأرصفة | Furas | 2 | 2 |
| العربات المتنقلة | Furas | 69 | 69 |
| المباني | Furas | 1 | 1 |
| مرفق تجاري | KFU | 1 | 1 |

These are source-record candidates, not a canonical Asset Type count; source labels can overlap on linked Masters.

## Dry run, application, and reconciliation

The pre-write v10 dry run was generated at `2026-10-18T13:08:57.441805Z`. It proposed only deterministic Furas Type assignments and evidence-based conflict closure:

| Dry-run measure | Count |
|---|---:|
| Deterministic canonical Type changes | 129 |
| Moved/retained as Investment Model evidence (initial v10 proposal) | 47 source records / 4 unique linked Masters |
| Moved to Master Asset Type | 0 |
| Mapped to unspecified | 0 Master changes; 162 were already unspecified after the earlier v9 projection |
| Remain review-required | 14 Masters |
| No Type change | 162 unspecified Masters |
| Conflict rows proposed for evidence-based resolution | 5 |

The per-Master decision ledger is available in [`resolution-preapply-dry-run.csv`](resolution-preapply-dry-run.csv). The original dry run was executed before the write; because it ran in a disposable container without a report-directory mount, the persisted row ledger was reconstructed afterward from the unchanged raw payloads and the immutable v10 `ChangeHistory` entries. Its JSON explicitly records `reconstructed_from_immutable_change_history=true`; the source database was read-only during reconstruction. The original pre-write summary and counts were captured above.

Applied at `2026-10-18T13:09:07.922321Z`: 129 Master values were restored to `تأجير مؤقت` from linked Furas raw fields; 2,898 SourceOpportunity standardized projections were refreshed to v10; five Type-vs-site-kind conflict rows were marked `RESOLVED_CANONICAL`; `ChangeHistory` and conflict rows remain intact. Raw payloads, source links, Master IDs, Sector, Activity and Sub-Activity were not written by this resolution script. No migration was required.

The source-semantics review identified that KFU's `COMMERCIAL_FACILITY_OPPORTUNITY` class does not prove an operating contract model. Version 11 removes that unsupported model inference, records the classifier as `investment_model_evidence` with `REVIEW_REQUIRED`, and retains the separate `مرفق تجاري` asset candidate. Applied at `2026-10-18T13:23:23.264262Z`: 0 Masters changed, all 2,898 source standardized projections refreshed to v11, and 0 conflict rows were closed. The post-apply dry run at `2026-10-18T13:23:28.356773Z` confirms the Type buckets and review queue are unchanged.

The v11 post-apply model evidence consists of 46 source records across 3 linked Masters: NCP BOOT (4), DBFOM (4), EOMT (2; one linked Master), PPP (33), ROMT (1), and KFU `تأجير` (2; two linked Masters). KFU `COMMERCIAL_FACILITY_OPPORTUNITY` is separately recorded as 1 `REVIEW_REQUIRED` model candidate, with no proposed model. The database check confirmed all 2,898 source projections now carry engine version 11 and the KFU evidence has no `investment_model` assignment.

The five resolutions are conflict IDs `179, 180, 181, 187, 188`: the raw Furas `OPPORTUNITYTYPE` is explicit while the conflicting Arabic values describe the site's format. The five decorative-quote duplicate rows `114–118` had already been safely marked `RESOLVED_KEEP`, with rows retained. This reconciles the original 24 rows / 19 unique Masters: five quote-only duplicate rows were closed first; five source-proven site-kind conflicts were then closed; **14 rows / 14 unique Masters remain open**. These 14 remain human-review cases; no ambiguous value was forced into a Type.

Open-case breakdown (unique Masters):

| Review class | Cases |
|---|---:|
| Activity/Sub-Activity evidence in Type slot | 6 |
| Other wrong-dimension ambiguity (Sector/Activity conflicts, including 2 Invest Saudi cases) | 8 |
| Unmapped source value | 0 |
| Other | 0 |
| **Total open** | **14** |

## Authoritative Master reconciliation

Validation snapshot `2026-10-18T13:23:28.356773Z`:

```ini
TOTAL_ELIGIBLE_MASTERS = 291
OPPORTUNITY_TYPE_IS_SINGLE_VALUED = TRUE
MASTERS_WITH_CANONICAL_OPPORTUNITY_TYPE = 129
MASTERS_WITH_UNSPECIFIED_OPPORTUNITY_TYPE = 162
MASTERS_REQUIRING_OPPORTUNITY_TYPE_REVIEW = 14
SUM_OF_CANONICAL_OPPORTUNITY_TYPE_BUCKETS = 291
```

`A=129` and `B=162` are disjoint; `A+B=291`. The sum includes the stable `opportunity_type:missing` filter bucket as a canonical query identity (`129 + 162`). The 14 review Masters are a subset of the 162 unspecified Masters, not an additional population.

## Ten-source coverage

Counts below describe the source inventory; the Master reconciliation above is the Al-Ahsa eligible-Master population. “Type evidence” includes a source taxonomy/content class when that is all a source exposes; it does **not** certify a business Type. Wrong-dimension counts identify current legacy projection/source evidence kept outside canonical Type. Review is the number of source records representing an open Type conflict.

| Source | Records | Raw Type / semantic evidence present | Canonical Type | Unspecified | Wrong dimension | Review |
|---|---:|---|---:|---:|---:|---:|
| Furas | 177 | 177 explicit `OPPORTUNITYTYPE` (129 TemporaryRental, 48 Investment) | 129 | 48 | 0 current | 6 |
| Al-Ahsa Opportunities | 103 | 0 | 0 | 103 | 0 | 6 |
| AHDA | 7 | 7 generic `content_type` values | 0 | 7 | 0 | 0 |
| Invest Saudi | 2,555 | 2,555 legacy Type projections; raw `type=Government-Led` occurs on 462 and `category` on 600 | 0 | 2,555 | 808 flagged wrong-dimension projections | 2 |
| KFU | 6 | 6 adapter/source classification values (2 Lease, 1 Commercial Facility, 3 General Announcement) | 0 | 6 | 1 facility classifier | 0 |
| Modon | 0 | 0 | 0 | 0 | 0 | 0 |
| NCP | 45 | 45 `content_type=PPP_PROJECT_ANNOUNCEMENT` source classes | 0 | 45 | 0 | 0 |
| NHC | 0 | 0 | 0 | 0 | 0 | 0 |
| PIF | 0 | 0 | 0 | 0 | 0 | 0 |
| Mwan | 5 | 5 source semantic classes; no linked eligible Masters | 0 | 5 | 0 | 0 |

For this table, “evidence present” counts any source type/classification signal or the historical standardized projection, not only a dedicated raw Opportunity Type field. Invest Saudi's raw `type` field is populated on 462 records as `Government-Led`; `category` appears on 600. These, and the 2,555 historical derived projections, are not approved Opportunity Types; 808 rows are specifically flagged as wrong-dimension projections in the current source evidence. Eight Invest Saudi source rows link to eligible Masters. See the raw-vs-projection census in [`source-values.csv`](source-values.csv) and the post-resolution source table in [`source-coverage-after-resolution.csv`](source-coverage-after-resolution.csv).

## API, dashboard, details, list, and export verification

| Filter option | Canonical ID | Displayed count | Exact API query count |
|---|---|---:|---:|
| تأجير مؤقت | `opportunity_type:temporary_rental` | 129 | 129 |
| غير محدد | `opportunity_type:missing` | 162 | 162 |

The live filter API and Dashboard Type chart return the same two IDs, Arabic labels and counts. List filtering preserves the canonical Type alongside Sector, Activity, Sub-Activity, Status, Owner, Source and Location; the selected option count equals the exact filtered Master query count. Dashboard chart drill-down applies `opportunity_type:temporary_rental` and returns 129.

Playwright verification passed after the v11 API refresh at 1920×1080 with RTL, no horizontal overflow, both Type options only, option/query equality, cross-filter combinations, pagination next/previous, search, reset, canonical Type in Details, dashboard drill-down, and no technical enum in the NCP detail/history. Screenshots and structured evidence are in [`screenshots/`](screenshots/) and [`after-opportunity-type-resolution.json`](screenshots/after-opportunity-type-resolution.json).

Live exports were parsed and reconciled, not just signature-checked:

| Canonical Type | CSV rows / labels | XLSX rows / labels |
|---|---|---|
| تأجير مؤقت | 129 / all canonical | 129 / all canonical |
| غير محدد | 162 / all canonical | 162 / all canonical |

See [`live-export-verification.json`](live-export-verification.json). Details sanitize historical technical taxonomy tokens in displayed change history; audit history and source payloads are retained in storage.

## Future ingestion, safety, and regression

- Furas `TemporaryRental` / `TempRental` maps to the canonical Type automatically. The same token from another source remains review-required.
- Missing Type stays `opportunity_type:missing` / `غير محدد`; generic `Investment` / `INVESTMENT_OPPORTUNITY` does not become a fake business Type.
- KFU Lease values stay out of Type and are retained as `تأجير` model evidence. The commercial facility classifier stays out of Type and is retained as review-required model evidence plus the separate `مرفق تجاري` asset candidate; no operating model is inferred. NCP PPP/project class is not promoted to Type; explicit source model values are retained separately. Unknown Type remains unspecified/reviewable.
- Raw Activity and Sub-Activity, raw Type, raw payload/hash, Master identity, and SourceOpportunity links are unchanged. Sector/Activity/Sector taxonomy logic was not changed by the Type mapping. Technical legacy enum values are redacted from business-visible history while kept in audit storage.
- `ASSET_TYPE_DIMENSION_REQUIRED = FALSE`; no Asset Type migration/schema change was made.
- `STANDARDIZATION_ENGINE_VERSION = 11`.
- Sector regression: passed. Activity regression: passed. Full v11 suite: `133 passed`, 1 existing Starlette/httpx deprecation warning, 0 failed.

## Required final assertions

```ini
OPPORTUNITY_TYPE_IS_SINGLE_VALUED = TRUE
OPPORTUNITY_TYPE_FILTER_OPTIONS_CANONICAL_IDENTITY_OK = TRUE
OPPORTUNITY_TYPE_OPTION_COUNTS_MATCH_QUERY_COUNTS = TRUE
OPPORTUNITY_TYPE_MISSING_DISPLAY_LABEL = غير محدد
OPPORTUNITY_TYPE_OTHER_AND_UNSPECIFIED_ARE_DISTINCT = TRUE
RAW_TECHNICAL_ENUMS_HIDDEN_FROM_BUSINESS_UI = TRUE
WRONG_DIMENSION_VALUES_NOT_EXPOSED_AS_OPPORTUNITY_TYPES = TRUE
SECTOR_TAXONOMY_REGRESSION = PASSED
ACTIVITY_TAXONOMY_REGRESSION = PASSED
BROWSER_UI_VERIFICATION = PASSED
FULL_REGRESSION_SUITE = PASSED
STANDARDIZATION_ENGINE_VERSION = 11
KFU_COMMERCIAL_FACILITY_MODEL_INFERENCE = WITHDRAWN_REVIEW_REQUIRED
ALL_SOURCE_PROJECTIONS_AT_ENGINE_VERSION_11 = TRUE
TOTAL_ELIGIBLE_MASTERS = 291
MASTERS_WITH_CANONICAL_OPPORTUNITY_TYPE = 129
MASTERS_WITH_UNSPECIFIED_OPPORTUNITY_TYPE = 162
SUM_OF_CANONICAL_OPPORTUNITY_TYPE_BUCKETS = 291
```
