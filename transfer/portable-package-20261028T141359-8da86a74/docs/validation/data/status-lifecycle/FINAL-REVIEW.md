# Opportunity Status / Lifecycle Deep Review

**Result:** `OPPORTUNITY_STATUS_LIFECYCLE_DEEP_REVIEW = COMPLETE`

**Acceptance snapshot:** 2026-10-19 10:58:36 UTC (13:58:36 Asia/Amman; lifecycle date handling uses Asia/Riyadh, 13:58:36). The fresh task baseline was 2026-10-19 10:27:30 UTC. Scheduled synchronization ran naturally during the review; its boundary and effects are recorded below. No source sync was manually started.

## A. Current status architecture

- `Opportunity.status` is the one current **Master lifecycle projection**. The enum is represented as a string, not as a database enum. Current values are Arabic canonical states.
- `SourceOpportunity.raw_status`, `raw_dates`, and `raw_data_json` retain the source evidence. `SourceOpportunity.canonical_status` is a derived source-level field added by migration `0022_status_lifecycle`; `standardized_data_json.fields.status` records the raw value, canonical ID/label, mapping rule, and review flags.
- `SourceOpportunity.first_seen_at`, `last_seen_at`, `missing_successful_checks`, and `last_missing_at` describe collection history. `Opportunity.first_seen_at` / `last_seen_at` describe the Master record. There are no separate Master booleans such as `is_active`, `is_historical`, `is_cancelled`, or `is_expired`; the application derives lifecycle groupings from the canonical Master status.
- `SourceObservation` stores immutable raw payload versions keyed by source record, endpoint, and content hash. The migration appended a current baseline status/payload observation; later source disappearance confirmations append source evidence. `ChangeHistory` records Master status transitions with before/after, source, and time.
- `Source.technical_health`, `sync_status`, `coverage_status`, pagination/completeness fields, and `SyncJob.status` represent technical collection and coverage. They are separate from opportunity business status.
- Relevant orchestration is in `app/service.py` (`sync_source`, `reconcile_missing_records`, `reconcile_status_lifecycle`), the hourly task in `app/tasks.py`, and the status definitions in `app/status_lifecycle.py`.

## B. Raw-status inventory

All 2,898 current SourceOpportunity rows were accounted for. Exact raw value counts and source names are in [final-inventory.json](final-inventory.json). The raw-to-canonical roll-up is:

| Source | Raw values and counts | Canonical SourceOpportunity status counts |
|---|---|---|
| فرص / Furas | `Announced` 173; `Deleted` 4 | منشورة 164; أزيلت من المصدر 13 |
| منصة الفرص الاستثمارية بالأحساء | `متاحة` 103 | متاحة 103 |
| هيئة تطوير الأحساء | null 7 | غير محددة 7 |
| استثمر في السعودية | null 2,555 | غير محددة 2,555 |
| جامعة الملك فيصل | `UNKNOWN` 5; `EXPIRED` 1 | حالة غير معروفة 4; أزيلت من المصدر 1; منتهية 1 |
| المركز الوطني للتخصيص | `UNKNOWN` 40; `IDENTITY_ALIAS` 1; `EXPIRED` 3; `AWARDED` 1 | حالة غير معروفة 40; منتهية 4; تمت الترسية 1 |
| موان | `ANNOUNCED` 5 | منشورة 5 |
| مدن | no SourceOpportunity rows | — |
| NHC الاستثمار | no SourceOpportunity rows | — |
| بوابة القطاع الخاص لصندوق الاستثمارات العامة | no SourceOpportunity rows | — |

`IDENTITY_ALIAS` is an NCP adapter identity-consolidation marker, not a lifecycle assertion. Its explicit past EOI deadline yields `منتهية`; the raw marker stays unchanged. Empty/null source status maps to `غير محددة`; a source-provided `UNKNOWN` maps to `حالة غير معروفة`. Other unrecognized values are not promoted to Available and receive an ambiguity flag.

## C. Canonical status definitions

| Canonical state | Meaning and evidence | Source / Master use | Terminal / reversible | Date and presentation behavior |
|---|---|---|---|---|
| `متاحة` | Source explicitly indicates available/open/active; not inferred from missing status | Source and Master | Nonterminal; reversible | Active/actionable group; only explicit state or source-specific approved alias |
| `منشورة` | Source explicitly says announced/published | Source and Master | Nonterminal; reversible | Active/publication group; distinct from Available |
| `منتهية` | Explicit expired/closed state, or a reliable date-only deadline that is before the current Riyadh date where status is otherwise unknown/unspecified | Source and Master | Lifecycle-terminal for the current opportunity; a corrected source state can reverse it | Historical group; a future/current deadline conflicting with explicit expiry is flagged for review |
| `ملغاة` | Unambiguous official cancellation wording only | Source and Master | Terminal unless official correction/reinstatement is evidenced | Historical group; never inferred from expiry or disappearance |
| `تمت الترسية` | Explicit official award state | Source and Master | Terminal for an open investment opportunity | Historical group |
| `أزيلت من المصدر` | A record is absent after thresholded, successful, complete, reconciliation-safe source snapshots; it describes visibility at that source, not cancellation | Source and Master | Reversible on reappearance | Historical group only when no live source has higher precedence |
| `حالة غير معروفة` | A status value exists but is explicitly unknown, ambiguous, or uninterpretable | Source and Master | Nonterminal; reversible when source evidence improves | Neither active nor historical; shown as its own filter/chart bucket |
| `غير محددة` | No usable status evidence was provided | Source and Master | Nonterminal; reversible when evidence arrives | Neither active nor historical; distinct bucket from Unknown |
| `قيد مراجعة الحالة` | Deterministic Master projection cannot safely resolve cancellation versus live evidence | Master only | Review state, not terminal | Neither active nor historical; no current Master has this state |

There is no canonical `historical` business status. It is a derived grouping of `منتهية`, `ملغاة`, `تمت الترسية`, and `أزيلت من المصدر`. `متاحة` and `منشورة` remain distinct; only the former means explicitly actionable/available. Unknown and unspecified Masters are neither active nor historical, so the lifecycle groups do not exhaust the total.

## D. Source-specific mappings and coverage

The implementation uses approved aliases plus a source-specific NCP exception. Sources without a usable status remain `غير محددة`; source records with explicit `UNKNOWN` remain `حالة غير معروفة`. The current official source universe is 10 enabled sources:

| Source | Records | Activity/status evidence | Canonical statuses | Health / coverage |
|---|---:|---|---|---|
| فرص / Furas | 177 | 173 `Announced`; 4 `Deleted`; disappearance is additionally confirmed by completed scans | منشورة 164; أزيلت من المصدر 13 | HEALTHY / COMPLETE_PUBLIC_SOURCE |
| منصة الفرص الاستثمارية بالأحساء | 103 | Explicit `متاحة` | متاحة 103 | HEALTHY / COMPLETE_PUBLIC_SOURCE |
| هيئة تطوير الأحساء | 7 | Status absent | غير محددة 7 | HEALTHY / COMPLETE_FOR_DEFINED_SCOPE |
| استثمر في السعودية | 2,555 | Status absent | غير محددة 2,555 | HEALTHY / COMPLETE_PUBLIC_SOURCE |
| جامعة الملك فيصل | 6 | `UNKNOWN` 5; `EXPIRED` 1 | حالة غير معروفة 4; أزيلت من المصدر 1; منتهية 1 | HEALTHY / COMPLETE_FOR_DEFINED_SCOPE |
| مدن | 0 | No opportunity rows currently exposed | — | HEALTHY / PUBLIC_COVERAGE_LIMITED |
| المركز الوطني للتخصيص | 45 | `UNKNOWN` 40; `EXPIRED` 3; `AWARDED` 1; adapter `IDENTITY_ALIAS` 1 | حالة غير معروفة 40; منتهية 4; تمت الترسية 1 | HEALTHY / COMPLETE_FOR_DEFINED_SCOPE |
| NHC الاستثمار | 0 | No opportunity rows currently exposed | — | WARNING / PUBLIC_COVERAGE_LIMITED |
| بوابة القطاع الخاص لصندوق الاستثمارات العامة | 0 | No opportunity rows currently exposed | — | HEALTHY / PUBLIC_COVERAGE_LIMITED |
| موان | 5 | `ANNOUNCED` | منشورة 5 | HEALTHY / COMPLETE_FOR_DEFINED_SCOPE |

Source coverage limitations are not interpreted as a business state. `COMPLETE_PUBLIC_SOURCE`, `COMPLETE_FOR_DEFINED_SCOPE`, and `PUBLIC_COVERAGE_LIMITED` remain source-collection metadata only.

## E. Master aggregation rule

`aggregate_master_status` deterministically projects linked source states. Current order/rules:

| Linked source evidence | Master result | Review behavior |
|---|---|---|
| Any `ملغاة` plus any `متاحة` or `منشورة` | قيد مراجعة الحالة | Open a status conflict; preserve both assertions |
| `متاحة` plus removed/expired/cancelled | متاحة | Live source wins; flag the evidence mix for review |
| `منشورة` plus removed/expired/cancelled (and no Available) | منشورة | Live publication wins; flag the evidence mix for review |
| Cancelled plus removed, with no live state | ملغاة | Explicit cancellation wins; removal remains source visibility evidence |
| Cancelled only | ملغاة | No inference from dates/removal |
| Awarded, with no live/cancelled state | تمت الترسية | Explicit award result |
| Expired, optionally plus removed | منتهية | Expiry is a real lifecycle state; mixed expiry/removal is flagged |
| Removed only | أزيلت من المصدر | Not cancelled |
| Unknown, optionally plus unspecified | حالة غير معروفة | Known uncertainty outranks missing evidence |
| Unspecified only or no source evidence | غير محددة | No usable lifecycle assertion |

Thus `AVAILABLE + REMOVED` → Available; `AVAILABLE + EXPIRED` → Available plus review; `EXPIRED + REMOVED` → Expired plus review; `CANCELLED + REMOVED` → Cancelled; `UNKNOWN + AVAILABLE` → Available plus review only where other conflicting terminal evidence exists; `UNSPECIFIED + AVAILABLE` → Available. In the current data, 8 Masters are multi-source; each projection matches this rule and none produces a mixed-state conflict. Full evidence is in [acceptance-audit.json](acceptance-audit.json).

## F. Deadline logic

- `Asia/Riyadh` is used for current local date. Date-only deadlines remain valid through the deadline date and expire only when `deadline < local_today`; the task never assigns midnight expiry to a date-only value.
- Arabic-Indic digits are normalized. ISO date, slash/hyphen, and dotted formats are parsed; invalid dates are flagged, and missing dates are not inferred.
- A passed deadline on otherwise unknown/unspecified evidence derives `منتهية`. An explicit live state with a passed date, or an explicit expired state with a future/today deadline, is flagged rather than silently overwritten.
- Current canonical Master deadline distribution: available 103 future; published 158 future; expired 2 past; removed 7 future, 6 past, 1 missing; unspecified 13 missing; unknown 1 missing. Current unresolved status/deadline conflicts: 0. The six past-dated Furas records are already confirmed removed from their source; their old raw `Announced` status is not treated as a live/deadline contradiction.
- The date-boundary tests exercise the Riyadh-day transition, including an input timestamp on the UTC evening that is still the same local date and a later timestamp that enters the following Riyadh day.
- Final acceptance caught and fixed a legacy list omission: API/dashboard lifecycle grouping now includes the canonical Arabic `تمت الترسية` in `historical`, with a regression fixture that verifies the list and KPI include awarded Masters. No current Master has this status, so present counts are unchanged.

## G. Cancellation audit

Current explicitly cancelled SourceOpportunity rows: **0**. Current cancelled Masters: **0**. The read-only scan of raw statuses, stored raw payload text, and NCP lifecycle events found no explicit cancellation evidence candidates. Therefore:

```ini
TOTAL_CURRENTLY_CANCELLED = 0
CANCELLED_WITH_EXPLICIT_EVIDENCE = 0
CANCELLED_WITHOUT_SUFFICIENT_EVIDENCE = 0
```

The implementation maps explicit cancellation aliases to `ملغاة`, while `Deleted` maps to `أزيلت من المصدر` and expiration remains `منتهية`.

## H. Removal / disappearance logic

Removal is only applied after `sync_source` confirms successful pagination, a successful page, a complete source collection, matching reported/collected totals where provided, and `reconciliation_safe`. Incomplete collections, parser warnings, API errors, source outages, rate limits, or failed jobs do not call the removal reconciler. Missing confirmation thresholds are source-configured (minimum 1; current Furas/KFU removed rows have at least threshold evidence).

Current removed records: **14** (Furas 13, KFU 1). All 14 have missing-check counters at/above their source thresholds and valid completed-source-coverage evidence. This includes four Furas raw `Deleted` rows, which are still classified as source removal, never cancellation. No current removal lacks valid coverage evidence.

## I. Reappearance behavior

Reappearance is supported. `_safe_record` matches the same `(source_id, source_opportunity_id)`, resets missing counters and timestamps, reuses the existing SourceOpportunity/Master link, restores the canonical source state from the new source evidence, and appends a new immutable observation instead of deleting the prior removal observation. Unit fixtures verify no duplicate Master and preserved removal history.

```ini
REMOVED_SOURCE_RECORD_REAPPEARANCE_SUPPORTED = TRUE
```

## J. Master reconciliation

At the acceptance snapshot, 296 total Master rows comprise 291 non-merged eligible Masters and 5 merged rows. Every one of the 291 eligible Masters has at least one linked SourceOpportunity. Mutually exclusive current status counts:

| Master status | Count |
|---|---:|
| متاحة | 103 |
| منشورة | 158 |
| منتهية | 2 |
| أزيلت من المصدر | 14 |
| حالة غير معروفة | 1 |
| غير محددة | 13 |
| **Sum** | **291** |

Active Masters = 261 (`متاحة` + `منشورة`). Historical Masters = 16 (`منتهية` + `أزيلت من المصدر`); there are no cancelled or awarded Masters. Unknown 1 and unspecified 13 are neither active nor historical. Open status review-required Masters = 0. The bucket sum equals eligible Masters.

## K. SourceOpportunity reconciliation

The 2,898 source records are separate from the 291 eligible Masters. Mutually exclusive source-level counts are:

| Canonical source status | Count |
|---|---:|
| متاحة | 103 |
| منشورة | 169 |
| منتهية | 5 |
| أزيلت من المصدر | 14 |
| تمت الترسية | 1 |
| ملغاة | 0 |
| حالة غير معروفة | 44 |
| غير محددة | 2,562 |
| **Sum** | **2,898** |

`acceptance-audit.json` includes per-source counts, all 8 multi-source records, and an independent recomputation of each Master projection.

## L. Conflicts and reviews

- Open lifecycle/status conflicts: 0; ambiguous Master projections: 0; deadline conflicts: 0; unsupported cancellations: 0.
- A pre-existing generic status conflict `#54` on Master 102 was a false conflict: it compared Furas `Announced` with an Invest Saudi source whose raw status was null. Null means no competing assertion. It was resolved `RESOLVED_KEEP`; a SystemEvent records the evidence. Master 102 remains `منشورة` based on Furas.
- Other open review conflicts remain in unrelated dimensions and were left untouched (95 total open generic conflicts at the acceptance snapshot; status field count is 0). No uncertain status was guessed to reduce a queue.

## M. API, dashboard, filters, list, details, map

Every canonical status option was checked against `/api/opportunities` and `/api/data-dashboard`; the six dashboard buckets sum to 291 and equal API counts. The Opportunities filter uses the canonical Master status ID, search/pagination/reset operate on that filtered Master list, and details expose both the Master status and each linked source's raw and canonical status. A live two-source detail check for Master 226 showed Master `متاحة`, Furas `منشورة`, and Al-Ahsa platform `متاحة`.

The dashboard status legend has six canonical buckets with the same counts. Playwright clicked the `منشورة` bucket and confirmed the Opportunities view selected `status:published` and returned 158 Masters. Map/geography endpoints accept the same status filter; map markers remain only the geographically eligible/located subset, so their count is intentionally not the full status count.

## N. CSV / XLSX

All six canonical Master statuses were checked through list API, dashboard bucket, CSV, and XLSX. Every list/CSV/XLSX count and exported status label matched exactly:

| Status | API/list | Dashboard | CSV | XLSX |
|---|---:|---:|---:|---:|
| أزيلت من المصدر | 14 | 14 | 14 | 14 |
| حالة غير معروفة | 1 | 1 | 1 | 1 |
| غير محددة | 13 | 13 | 13 | 13 |
| متاحة | 103 | 103 | 103 | 103 |
| منتهية | 2 | 2 | 2 | 2 |
| منشورة | 158 | 158 | 158 | 158 |

CSV and XLSX status columns are the Master canonical status, not a source row's status. Source multiplicity/provenance is retained in details, while exports remain one row per Master.

## O. Data corrections and safety

There were **177 intentional Master status corrections** during migration `0022_status_lifecycle`; the complete per-Master ID, prior/after status, linked source record IDs, raw status, deadlines, and disappearance evidence are in [correction-ledger.json](correction-ledger.json):

| Before → after | Masters | Reason |
|---|---:|---|
| Announced → منشورة | 158 | Explicit Furas/Mwan publication wording |
| Announced → متاحة | 2 | A linked Al-Ahsa source explicitly says available |
| REMOVED_FROM_SOURCE → أزيلت من المصدر | 14 | Canonical Arabic projection of confirmed source disappearance |
| EXPIRED → منتهية | 2 | Canonical Arabic projection of explicit/derived expiry |
| Unknown → حالة غير معروفة | 1 | Canonical Arabic projection of known unknown evidence |

SourceOpportunity's new `canonical_status` was backfilled for all 2,898 records; `raw_status`, `raw_dates`, and `raw_data_json` were not canonicalized in place. The migration appended 2,898 baseline observations; the 7,603 pre-existing observations were preserved. The two natural scheduled scans added 13 further removal-confirmation observations (Furas 13), with no Master change-history additions. Identity and SourceOpportunity-link fingerprints were unchanged through the migration, and current counts remain 296 Masters / 2,898 source records. No unexplained business data changes were found.

**History boundary:** previous SourceObservation rows are preserved, but those 7,603 pre-lifecycle observations contain no top-level raw/canonical status field. The current baseline and all subsequent status transitions are auditable; earlier raw-status versions that were never recorded before this rollout cannot be reconstructed. This is a documented pre-existing history limitation, not a destructive change from this task.

## P. Playwright evidence

Live browser validation used `http://localhost:8080` after the natural scheduled syncs. It verified status filter/badges, count totals, reset, search, pagination, details, CSV/XLSX responses, dashboard status buckets and drilldown, RTL, Western digits, and horizontal overflow at all five requested viewports.

| Viewport | Document scroll width | Reset fully inside viewport | Filter controls inside container, non-overlapping | Dropdown filter usable | Direction |
|---|---:|---|---|---|
| 1920×1080 | 1920 | Yes | Yes | Yes | RTL |
| 1440×900 | 1440 | Yes | Yes | Yes | RTL |
| 1366×768 | 1366 | Yes | Yes | Yes | RTL |
| 768×900 | 768 | Yes | Yes | Yes | RTL |
| 390×844 | 390 | Yes | Yes | Yes | RTL |

Artifacts: [browser results](playwright-results.json), [all-status export reconciliation](export-reconciliation.json), [1440×900 Opportunities screenshot](screenshots/opportunities-1440x900-viewport.png), [390×844 Opportunities screenshot](screenshots/opportunities-390x844-viewport.png), and [1440×900 dashboard status screenshot](screenshots/dashboard-status-1440x900-viewport.png). The reset/filter controls wrap on desktop widths when needed and stack responsively; none is clipped. No page-level horizontal overflow was observed.

## Q. Full regression and lifecycle assertions

- Full test suite: **154 passed / 0 failed** (one Starlette/httpx deprecation warning).
- Focused lifecycle tests cover aliases, Unknown vs Unspecified, cancellation vs removal, date-only/Riyadh boundary handling, invalid/null/future deadlines, Master aggregation combinations, API/dashboard/filter/search/pagination/details/CSV/XLSX, source disappearance, incomplete scans, outages, and reappearance.
- A read-only live asset/facility regression was re-run successfully after correcting its stale XLSX auto-filter expectation to use the actual 30-column output. Existing taxonomy data/semantics were not changed. (The opportunity XLSX currently contains 30 columns, RTL, frozen A7, and filter A6:AD7.)
- Closed-area regression assertions: Sector taxonomy **PASSED** (live filter/chart/export reconciliation); Activity/Sub-Activity taxonomy **PASSED** (`test_activity_taxonomy.py` in the full suite); Opportunity Type **PASSED** (129 temporary-rental and 162 unspecified rows reconcile through CSV/XLSX); Investment Model **PASSED** (4 lease, 1 EOMT, 286 unspecified rows reconcile through list/dashboard/CSV/XLSX); Asset/Facility Type **PASSED** (all nine buckets reconcile); Location/Geographic Eligibility **PASSED** (`test_location_geography.py` in the full suite); Opportunities table alignment **PASSED** (`test_excel_presentation.py` plus live RTL viewport inspection); Sector chart “أخرى” aggregation **PASSED** (dashboard 291 total and the 17-Master “أخرى” set remains consistent through API/CSV/XLSX).
- Status standardization rule: `source_aware_lifecycle_v1`; Standardization Engine version: **16**.
- No source sync was manually started. Natural sync IDs 343 (Furas) and 344 (Al-Ahsa) were scheduled and successful: Furas 10:47:48–10:47:54 UTC, 164 complete records, 13 removals confirmed, 0 new, 0 updates, 164 unchanged; Al-Ahsa 10:48:48–10:48:56 UTC, 103 complete records, 0 removals, 0 new, 0 updates, 103 unchanged. A fresh acceptance reconciliation was taken after both.

```ini
OPPORTUNITY_STATUS_LIFECYCLE_DEEP_REVIEW = COMPLETE
SNAPSHOT_TOTAL_MASTERS = 296
SNAPSHOT_ELIGIBLE_MASTERS = 291
SNAPSHOT_SOURCE_OPPORTUNITIES = 2898
SNAPSHOT_OBSERVATIONS = 10514
SOURCE_STATUS_MODEL_EXPLICIT = TRUE
MASTER_STATUS_MODEL_EXPLICIT = TRUE
SOURCE_AND_MASTER_STATUS_SEPARATED = TRUE
DELETED_FROM_SOURCE_NOT_CANCELLED = VERIFIED
EXPIRED_NOT_CANCELLED = VERIFIED
TECHNICAL_HEALTH_SEPARATED_FROM_STATUS = TRUE
COVERAGE_STATUS_SEPARATED_FROM_STATUS = TRUE
TOTAL_MASTER_STATUS_RECONCILIATION = 291
TOTAL_SOURCE_STATUS_RECONCILIATION = 2898
AVAILABLE_MASTERS = 103
PUBLISHED_MASTERS = 158
EXPIRED_MASTERS = 2
CANCELLED_MASTERS = 0
HISTORICAL_MASTERS = 16
UNKNOWN_MASTERS = 1
UNSPECIFIED_MASTERS = 13
STATUS_REVIEW_REQUIRED_MASTERS = 0
EXPLICITLY_CANCELLED_WITH_EVIDENCE = 0
UNSUPPORTED_CANCELLED_RECORDS = 0
REMOVED_SOURCE_RECORDS = 14
REMOVAL_WITH_VALID_COVERAGE_EVIDENCE = 14
REMOVAL_WITHOUT_VALID_COVERAGE_EVIDENCE = 0
REMOVED_SOURCE_RECORD_REAPPEARANCE_SUPPORTED = TRUE
STATUS_DEADLINE_CONFLICTS = 0
MULTI_SOURCE_STATUS_CONFLICTS = 0
STATUS_REVIEW_QUEUE_OPEN = 0
CORRECTLY_RETAINED_FOR_REVIEW = 0
STATUS_FILTER_RECONCILIATION = PASSED
DASHBOARD_STATUS_RECONCILIATION = PASSED
STATUS_CHART_DRILLDOWN_RECONCILIATION = PASSED
CSV_STATUS_RECONCILIATION = PASSED
XLSX_STATUS_RECONCILIATION = PASSED
BROWSER_STATUS_VERIFICATION = PASSED
INTENTIONAL_STATUS_DATA_CORRECTIONS = 177
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MASTER_IDENTITIES_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
STANDARDIZATION_ENGINE_VERSION = 16
FULL_REGRESSION_SUITE = 154 passed / 0 failed
SECTOR_TAXONOMY_REGRESSION = PASSED
ACTIVITY_TAXONOMY_REGRESSION = PASSED
OPPORTUNITY_TYPE_TAXONOMY_REGRESSION = PASSED
INVESTMENT_MODEL_TAXONOMY_REGRESSION = PASSED
ASSET_FACILITY_TYPE_REGRESSION = PASSED
LOCATION_GEOGRAPHIC_ELIGIBILITY_REGRESSION = PASSED
OPPORTUNITIES_TABLE_ALIGNMENT_REGRESSION = PASSED
SECTOR_CHART_OTHER_AGGREGATION_REGRESSION = PASSED
```
