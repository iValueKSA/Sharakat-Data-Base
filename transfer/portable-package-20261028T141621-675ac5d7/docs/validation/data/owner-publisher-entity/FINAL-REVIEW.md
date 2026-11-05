# Opportunity Owner / Publisher / Entity Deep Review

**Result: COMPLETE**  
**Fixed validation snapshot:** 2026-10-19 11:33:12.267278 UTC  
**Post-review snapshot:** 2026-10-19 12:01:34.766869 UTC  
**Standardization engine:** v17

## Decision

Owner, publishing entity, publication platform, source operator, and related-entity mentions are represented as separate roles. Every one of the 291 non-merged Masters has exactly one stored owner value or an explicit missing value; three ambiguous cases remain in the review queue. Those three are deliberately not auto-resolved. Master counts, source links, API options, filters, table, detail and exports reconcile. No source sync was started manually.

## A. Architecture and semantics

- **Opportunity Owner:** `opportunities.opportunity_owner`, a single-valued Master field. A value is canonicalized from supported evidence; null is displayed and filtered as `غير محدد`. A platform identity or an entity mentioned in contextual text is not sufficient evidence.
- **Source owner projection:** `source_opportunities.source_owner` is a source-record adapter projection, not by itself authoritative evidence for the Master. Raw fields remain under `raw_data_json`; immutable payload versions remain in `source_observations`.
- **Publication platform:** `opportunities.primary_publication_platform` at Master level; API source cards/details also expose `publication_platform` from the `Source` record. It names the technical/site publication channel, such as فرص or Invest Saudi.
- **Publishing entity:** exposed as nullable `sources[].publishing_entity` on opportunity details when a source payload explicitly supplies a publisher/publishing entity. Furas `ENTITIESNAME` is shown as its registered/publishing entity. It stays raw-derived and is not presumed to own the opportunity.
- **Source operator:** `sources.organization_name`, exposed as `source_operator`; it describes the operator/source publisher administration, not the opportunity owner.
- **Mentioned/related entities:** NCP `project_owner_candidate`, Invest Saudi municipality/company fields, and PIF portfolio companies remain contextual/raw related-entity evidence unless an explicit owner mapping is supported.
- No new Entity table was required. The Owner is persisted on Master; platform/operator identity is persisted on Source; publisher-specific values are exposed from preserved source payload. Owner is single-valued (`OWNER_DIMENSION_SINGLE_VALUED=TRUE`); a multi-owner model is not required.

## B. Source-specific rules

| Official source | Current records / linked non-merged Masters | Owner rule | Publisher/platform rule |
|---|---:|---|---|
| فرص (Furas) | 177 / 177 | Use the explicit `AMANA` field as owner. For the two records where it is absent, the supported entity value is retained as owner. | `ENTITIESNAME` is exposed as publishing/registered entity when present; platform is فرص. It does not override an explicit `AMANA`. |
| Al-Ahsa Investment Platform | 103 / 103 | Portal scope/name alone does not prove item-level owner; adapter now emits no owner absent record evidence. | Platform is the Al-Ahsa portal. |
| AHDA | 7 / 7 | AHDA identity alone is not item-level owner evidence; adapter now emits no owner absent record evidence. | Platform is AHDA. |
| Invest Saudi | 2,555 / 8 | Ministry, municipality, and company/context fields are not automatically owner; conflicts remain reviewable. | Platform is Invest Saudi; source operator/publishing context stays separate. |
| King Faisal University | 6 / 3 | Retain KFU where the source record identifies KFU as owner. | University source/platform stays separately identified. |
| MODON | 0 / 0 | No current source records to classify. | Configured official platform; no item-level inference. |
| NCP | 45 / 1 | Regex-derived `project_owner_candidate` is evidence only and remains raw; Master 228 stays in review. | NCP platform/source remains separate. |
| NHC | 0 / 0 | No current source records to classify. | Configured official source; no item-level inference. |
| PIF | 0 / 0 | Portfolio company is a related entity, not automatically owner. | PIF hub is a platform/source. |
| MWAN | 5 / 0 | Publisher identity is not automatically owner. | MWAN platform/source stays separate. |

There are 2,898 current SourceOpportunity rows. Linked-source Master counts sum to 299 because eight source links overlap across the 291 unique non-merged Masters (six Furas/local-portal overlaps and two Furas/Invest Saudi overlaps). No linking or Master aggregation was changed.

## C. Canonical catalogue and owner inventory

The only current canonical owner buckets are:

| Canonical owner | Masters |
|---|---:|
| أمانة الأحساء | 175 |
| جامعة الملك فيصل | 3 |
| وزارة البيئة والمياه والزراعة | 1 |
| وزارة الحرس الوطني | 1 |
| غير محدد | 111 |
| **Total** | **291** |

Amanah aliases normalized to `أمانة الأحساء`: `أمانة الأحساء` (canonical label), `أمانة محافظة الأحساء`, `Al Ahsa Municipality`, and orthographic `أمانة الاحساء` (stored data alias). Ministry English/Arabic name variants are normalized only as a candidate identity; Master 228 remains unresolved and is not counted as a confirmed Ministry owner. Similar Al-Ahsa entities such as the governorate, municipality, development authority, chamber, and university are not merged.

Missing, blank, `غير محدد`, `غير محددة`, `قيمة مفقودة`, `N/A`, `None`, and `Unknown` canonicalize to `owner:missing` / `غير محدد`. `أخرى` is not used as an owner alias or substitute for missing evidence. Four non-canonical alias strings are accepted for the current owner catalogue (excluding the canonical label); database organization alias rows are a broader cross-entity catalogue and are not the owner-alias count.

Full per-Master evidence is in [master-owner-reconciliation.jsonl](master-owner-reconciliation.jsonl) and its CSV companion. Distinct source-owner values by source, including nulls, are in [source-owner-inventory.jsonl](source-owner-inventory.jsonl) / CSV; source-model and Furas raw entity inventories are also included.

## D. Exact Master reconciliation

Population is every current non-merged Master (`merged_into_id IS NULL`), 291 rows. The five merged Master rows are retained in the database and source history, but are not current opportunity rows and are excluded from owner buckets.

| Mutually exclusive evidence state | Count | IDs |
|---|---:|---|
| OWNER_CONFIRMED | 178 | all non-null, non-merged Masters except IDs 102 and 230, whose selected owner is under active conflict review |
| OWNER_UNSPECIFIED | 110 | null/blank owner without an open owner conflict |
| OWNER_REVIEW_REQUIRED | 3 | 102, 228, 230 |
| **Sum** | **291** | **291 non-merged Masters** |

For a compact and exact ID listing, see `owner_evidence_class` in [master-owner-reconciliation.jsonl](master-owner-reconciliation.jsonl) (one row per Master, ordered by ID). `ALL_MASTER_ROWS` includes IDs with and without `merged_into_id`; the file intentionally focuses on the complete current/non-merged population as requested for owner reconciliation.

The review cases are:

- **Master 102 / conflict 51:** Furas identifies `أمانة الاحساء`; Invest Saudi says “Municipality”. Keep current Amanah canonical owner, but retain review because the generic English value does not identify a legal entity precisely.
- **Master 230 / conflict 99:** Furas identifies `أمانة الأحساء`; Invest Saudi says “Municipality”. Same rationale; do not collapse it automatically.
- **Master 228 / conflict 120:** NCP extracted “the Ministry of Municipalities” while its Arabic source field says `وزارة البلديات والإسكان`. It is a project-owner candidate, not verified ownership. Master owner is unspecified pending review; do not assign the Ministry merely to reduce the queue.

The field currently stores selected Amanah values on 102/230, and a missing value on 228; those three are excluded from the confirmed evidence class and counted once in the review class. Consequently field-value API counts include 102/230 in Amanah and 228 in `غير محدد`, while the evidence-state partition above remains disjoint.

## E. Corrections and contamination audit

There were **115 intentional Master owner corrections**, fully listed in [applied-owner-corrections.json](applied-owner-corrections.json):

- 111 unsupported defaults were cleared: 97 portal-only Al-Ahsa records, 7 AHDA records, 6 Invest Saudi defaults, and 1 NCP regex-inferred entity. The NCP candidate remains in raw provenance and Master 228 remains queued.
- Four Furas records were corrected to the explicit raw `AMANA` value `أمانة محافظة الأحساء`; the erroneous owner was the `ENTITIESNAME` value `وزارة البلديات والإسكان`. The four IDs are 23, 26, 69, and 122. Source owner projections were corrected to the AMANA evidence, standardization metadata set to v17, and field-provenance/change-history rows recorded. Their raw payloads were preserved; itemized before/after values and external IDs are in [furas-owner-projection-corrections.jsonl](furas-owner-projection-corrections.jsonl).

Found platform-as-owner false positives: **110** (97 local-platform defaults, 7 AHDA platform-identity defaults, 6 Invest Saudi platform/ministry defaults). Found one additional contextual NCP entity-as-owner inference and four publisher-as-owner projection errors. Platform-as-owner false positives remaining: **0**. A later natural scheduled sync updated the source-owner projection to null for 103 local portal source records under the corrected adapter; their raw payloads and Master decisions were preserved. This expected adapter output is not a further manual business-data correction.

## F. API, UI and export reconciliation

`GET /api/filters` owner `option_counts` equals the Master-filter result for each canonical ID, and each option maps to one stable ID:

| API owner option | Filter ID | Masters |
|---|---|---:|
| أمانة الأحساء | `al_ahsa_municipality` | 175 |
| جامعة الملك فيصل | `unmapped:owner:b841f5b3e39dcfc7` | 3 |
| وزارة البيئة والمياه والزراعة | `unmapped:owner:b78c8c267cf0c18f` | 1 |
| وزارة الحرس الوطني | `unmapped:owner:b64c21869b8223bf` | 1 |
| غير محدد | `owner:missing` | 111 |

Filter counts total 291 and have zero false positives/false negatives against the canonical Master field. `غير محدد` is selectable in the UI and returns 111 rows. The opportunity list displays `الجهة المالكة`. Detail APIs distinguish `owner`, `publication_platform`, nullable `publishing_entity`, and `source_operator`; Master 23 verified Amanah as owner, وزارة البلديات والإسكان as Furas publishing entity, and فرص as platform. CSV and XLSX each contain 291 Master rows and 111 `غير محدد` owner rows. CSV header is `الجهة المالكة`; XLSX sheet `الفرص الاستثمارية` uses the same column. Source platform remains in its own export column(s).

Playwright checks passed at 1920×1080, 1440×900, 1366×768, 768×900, and 390×844. All remained RTL, showed the complete canonical owner options, and had no page horizontal overflow. Owner filtering, unspecified filtering, reset, search, pagination, details, CSV, XLSX and Western-digit display passed. Screenshots and machine-readable outcomes are in [screenshots/](screenshots/) and [playwright-results.json](playwright-results.json).

## G. Snapshot, scheduled sync and data safety

At the fixed task-start snapshot, there were 296 Master rows (291 non-merged, 5 merged), 2,898 source records, and **10,514 observations**. That observation count was recorded before the two natural scheduled syncs. Jobs 347 (Furas) and 348 (Al-Ahsa portal) ran at 2026-10-19 11:49:46 UTC and completed successfully. Furas parsed 164 records (164 unchanged); the portal parsed 103 (103 source-record updates). The only new observations were **13 Furas observations**, all first seen at 11:49:51.285868 UTC. Thus the post-sync count is 10,527; delta is +13. No observations were edited/deleted.

Post-review counts remain 296 Masters / 291 non-merged / 5 merged and 2,898 SourceOpportunity rows. Master identity and Master-to-source link counts/IDs remained unchanged. Owner fields and provenance audit history changed only for the intentional corrections above. Raw source payloads were retained; natural Furas observations append new immutable versions. No manual source sync was started; no business-data change is unexplained. Full start/post snapshots are `start-snapshot.json` and [post-review-snapshot.json](post-review-snapshot.json).

## H. Tests and closed-area regression

The complete test suite was rerun against the current source tree after the final four owner-data corrections: **158 passed / 0 failed** (one existing Starlette/httpx deprecation warning). The suite used an isolated in-memory SQLite database (`DATABASE_URL=sqlite://`) with Redis disabled; it did not write to the live PostgreSQL business database. This final run is recorded at 2026-10-19 15:06 Asia/Amman. API, all owner filter counts, details for Masters 102/228/230, CSV, XLSX, and the five Playwright viewports were reverified against the unchanged final live database immediately after the suite.

Previously closed areas remain unchanged and their regressions passed in the full suite: Sector, Activity/Sub-Activity, Opportunity Type, Investment Model, Asset/Facility Type, location/geographic eligibility, lifecycle status, opportunities table alignment, Sector chart “أخرى” aggregation, and Dashboard layout. No Dashboard or geographic logic was modified for this review.

## Final assertions

```ini
OPPORTUNITY_OWNER_PUBLISHER_ENTITY_DEEP_REVIEW = COMPLETE
SNAPSHOT_TOTAL_MASTER_ROWS = 296
SNAPSHOT_NON_MERGED_MASTERS = 291
SNAPSHOT_SOURCE_OPPORTUNITIES = 2898
SNAPSHOT_OBSERVATIONS = 10514
OWNER_MODEL_EXPLICIT = TRUE
PUBLISHER_MODEL_EXPLICIT = TRUE
PUBLICATION_PLATFORM_MODEL_EXPLICIT = TRUE
OWNER_SEPARATED_FROM_PUBLISHER = TRUE
OWNER_SEPARATED_FROM_PUBLICATION_PLATFORM = TRUE
PUBLISHER_SEPARATED_FROM_PUBLICATION_PLATFORM = TRUE
OWNER_CONFIRMED_MASTERS = 178
OWNER_UNSPECIFIED_MASTERS = 110
OWNER_REVIEW_REQUIRED_MASTERS = 3
OWNER_MASTER_RECONCILIATION_SUM = 291
OWNER_MASTER_RECONCILIATION = PASSED
CANONICAL_OWNER_COUNT = 4
OWNER_ALIAS_COUNT = 4
OWNER_DIMENSION_SINGLE_VALUED = TRUE
MULTI_OWNER_MODEL_REQUIRED = FALSE
PLATFORM_AS_OWNER_FALSE_POSITIVES_FOUND = 110
PLATFORM_AS_OWNER_FALSE_POSITIVES_REMAINING = 0
OWNER_PUBLISHER_CONFLICTS = 4
MULTI_SOURCE_OWNER_CONFLICTS = 3
OWNER_REVIEW_QUEUE_OPEN = 3
CORRECTLY_RETAINED_FOR_REVIEW = 3
OWNER_FILTER_RECONCILIATION = PASSED
OWNER_FILTER_FALSE_POSITIVES = 0
OWNER_FILTER_FALSE_NEGATIVES = 0
OPPORTUNITIES_TABLE_OWNER_SEMANTICS = PASSED
DETAIL_PAGE_ENTITY_SEMANTICS = PASSED
CSV_OWNER_RECONCILIATION = PASSED
XLSX_OWNER_RECONCILIATION = PASSED
SOURCE_PLATFORM_IDENTITY_RECONCILIATION = PASSED
INTENTIONAL_OWNER_DATA_CORRECTIONS = 115
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
BROWSER_OWNER_VERIFICATION = PASSED
SECTOR_TAXONOMY_REGRESSION = PASSED
ACTIVITY_TAXONOMY_REGRESSION = PASSED
OPPORTUNITY_TYPE_TAXONOMY_REGRESSION = PASSED
INVESTMENT_MODEL_TAXONOMY_REGRESSION = PASSED
ASSET_FACILITY_TYPE_REGRESSION = PASSED
LOCATION_GEOGRAPHIC_ELIGIBILITY_REGRESSION = PASSED
STATUS_LIFECYCLE_REGRESSION = PASSED
OPPORTUNITIES_TABLE_ALIGNMENT_REGRESSION = PASSED
SECTOR_CHART_OTHER_AGGREGATION_REGRESSION = PASSED
DASHBOARD_LAYOUT_CLEANUP_REGRESSION = PASSED
FULL_REGRESSION_SUITE = 158 passed / 0 failed
STANDARDIZATION_ENGINE_VERSION = 17
POST_REVIEW_SOURCE_OBSERVATIONS = 10527
SCHEDULED_SYNC_OBSERVATION_DELTA = 13
```

## Final acceptance rerun after the four final owner corrections

The post-correction acceptance snapshot at 2026-10-19 15:06:01 +03:00 matches the preceding post-review snapshot for all Master IDs, source links, current source raw payloads, observation raw payloads, and observation count. There were no later scheduled sync jobs; the last two were jobs 347/348 and their +13 Furas observations were already included in the post-review snapshot. The current API and both exports each reconcile to 291 rows; the five selectable owner entries are distinct, with exactly four specified canonical owners and one `غير محدد` bucket. Open review IDs remain exactly 102, 228, 230.

```ini
OPPORTUNITY_OWNER_PUBLISHER_ENTITY_DEEP_REVIEW = COMPLETE
FINAL_STATE_TOTAL_NON_MERGED_MASTERS = 291
OWNER_CONFIRMED_MASTERS = 178
OWNER_UNSPECIFIED_MASTERS = 110
OWNER_REVIEW_REQUIRED_MASTERS = 3
OWNER_MASTER_RECONCILIATION_SUM = 291
OWNER_MASTER_RECONCILIATION = PASSED
OPEN_OWNER_REVIEW_MASTER_IDS = [102, 228, 230]
CANONICAL_SPECIFIED_OWNER_COUNT = 4
OWNER_ALIAS_DUPLICATES_IN_FILTER = 0
OWNER_FILTER_RECONCILIATION = PASSED
CSV_OWNER_RECONCILIATION = PASSED
XLSX_OWNER_RECONCILIATION = PASSED
BROWSER_OWNER_VERIFICATION = PASSED
INTENTIONAL_OWNER_DATA_CORRECTIONS = 115
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 158 passed / 0 failed
FULL_REGRESSION_EXECUTED_AFTER_FINAL_OWNER_CORRECTIONS = TRUE
```

Final-state machine snapshot: [final-acceptance-snapshot.json](final-acceptance-snapshot.json).

Regression transcript: [full-regression-after-final-corrections.txt](full-regression-after-final-corrections.txt).
