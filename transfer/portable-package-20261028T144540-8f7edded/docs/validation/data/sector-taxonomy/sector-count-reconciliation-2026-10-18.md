# Sector count reconciliation

**Validation timestamp:** `2026-10-18T09:49:50.020395Z`  
**Database:** local PostgreSQL 16  
**Result:** `SECTOR_TAXONOMY_DEEP_REVIEW_COMPLETE`

## Reconciled totals

| Canonical sector | Master count |
|---|---:|
| غير محدد | 164 |
| أخرى | 17 |
| صناعي | 59 |
| تجاري | 39 |
| البيئة | 6 |
| الرعاية الصحية | 3 |
| التعليم | 1 |
| الزراعة | 1 |
| السياحة | 1 |
| **Sum** | **291** |

At the captured validation time, PostgreSQL had **291 non-merged Masters**, including **279 active** and **12 historical** under the existing lifecycle predicates. The Data Dashboard endpoint returned 291, its sector buckets summed to 291, and the Opportunity List endpoint total was 291.

`أخرى` and `غير محدد` remain distinct canonical identities: `sector:other` has 17 records and `sector:unspecified` has 164. The database currently has no null or blank sector among these Masters; unspecified values are stored under the approved unspecified label.

## Root cause of 290 versus 291

The taxonomy dry-run report has separate fields `master_count=291` and `records_affected=290`. The latter counts Masters whose Sector, Activity, or Opportunity Type value changed; it is not the population size. Exactly one Master was unchanged by the standardization: **Master 21** (`AH-20261011105647-437b2bd1`). It already had canonical Sector `أخرى`, Activity blank, and its previous Opportunity Type value unchanged. It contributes exactly once to `أخرى`.

Therefore, 291 is the correct eligible population and the category sum. There is no extra/doubly counted Master and no aggregate correction is needed. “290 Masters processed” was a misreading of `records_affected`, not a database or chart defect.

The visual analytics validation dated 2026-10-14 records 289 for that earlier snapshot. It is a historical validation result and is not the denominator for this 2026-10-18 PostgreSQL snapshot.

## Query and one-sector invariant

The service path is `app/main.py`:

- `ACTIVE_EXCLUDED_STATUSES` and `HISTORICAL_STATUSES` define the existing lifecycle scopes.
- `_opportunity_filter_conditions()` starts with `Opportunity.merged_into_id IS NULL` and adds the requested dashboard filters.
- `data_dashboard()` counts IDs under those conditions, builds the eligible ID subquery, then groups `Opportunity.sector` by that ID set. Each `Opportunity` has one scalar `sector` column. The aggregation does not join source, activity, taxonomy alias, provenance, or review tables.
- `group_counts("sector", ...)` applies the shared Python canonicalization (`canonical_value` / `canonical_id`) to grouped stored values. Alias canonicalization is not a relational join.

Equivalent population SQL for this unfiltered dashboard snapshot is:

```sql
SELECT COUNT(id)
FROM opportunities
WHERE merged_into_id IS NULL;
```

The sector aggregation is equivalent to:

```sql
SELECT sector, COUNT(id)
FROM opportunities
WHERE id IN (
    SELECT id FROM opportunities WHERE merged_into_id IS NULL
)
GROUP BY sector;
```

The dashboard applies the same selected filter predicates to both the ID set and counts. Lifecycle counts use `NOT status IN (ACTIVE_EXCLUDED_STATUSES)` for active and `status IN (HISTORICAL_STATUSES)` for historical.

The read-only reconciliation dataset [`sector-count-reconciliation-2026-10-18.csv`](sector-count-reconciliation-2026-10-18.csv) contains all 291 eligible IDs. Every row has `sector_contribution=1`; the sum is 291. It also records linked source-row count and whether the scalar Activity value is populated. There are no duplicate Master IDs or multi-sector rows.

### Join and schema checks

- The eight Masters with two linked `SourceOpportunity` rows are 102, 164, 192, 193, 195, 226, 230, and 249. A hypothetical raw left join to source rows would yield 299 rows (eight more than the 291 Masters). The actual sector query has no such join and returns 291.
- Activity is a scalar field on `Opportunity`, not a one-to-many relation. Migration `0018_sector_activity` adds nullable `activity` and `source_activity` columns; it creates no activity table or aggregation join. PostgreSQL reports `0018_sector_activity (head)`.
- There are 299 linked source rows across 291 Masters. The seven former `فرصة استثمارية` records each have one linked source and resolve once: 211 → غير محدد, 212 → السياحة, 213 → الرعاية الصحية, 214 → الرعاية الصحية, 215 → الزراعة, 216 → الرعاية الصحية, 217 → التعليم.

## API reconciliation and regression

All requests below were read-only and were run against the local service in the same validation run. Each tested filtered dashboard total equals the sum of its sector groups.

| Filter | Selected value | Total | Sector sum | Result |
|---|---|---:|---:|---|
| Status | `Announced` | 163 | 163 | Pass |
| Owner | `أمانة الأحساء` | 268 | 268 | Pass |
| Source | `furas` | 177 | 177 | Pass |
| Location | `الأحساء` | 260 | 260 | Pass |
| Opportunity type | `COMMERCIAL_FACILITY_OPPORTUNITY` | 1 | 1 | Pass |
| Activity | `البيئة` | 6 | 6 | Pass |
| Status + source | `Announced` + `furas` | 163 | 163 | Pass |

The Opportunity List total and dashboard total both equal 291. Sector filtering returns 17 `أخرى` and 164 `غير محدد`. The seven detail endpoints returned the approved sectors above and one linked source each. CSV and XLSX export endpoints returned HTTP 200; the live UI/export check returned 17 CSV/XLSX rows for `أخرى`, with Sector and Activity in separate columns.

The browser regression [`scripts/verify_sector_taxonomy_ui.cjs`](../../../../scripts/verify_sector_taxonomy_ui.cjs) passed: RTL, canonical sector options, `أخرى` filter, search, reset, pagination, opportunity details, CSV/XLSX exports, and no horizontal overflow. Full test suite: **125 passed**, one existing Starlette/httpx deprecation warning. API review counters were read without changes: 26 pending duplicates, 17 pending location reviews, 67 open taxonomy conflicts, and 11 open field conflicts.

## Data preservation and code changes

No backend/query code, sector mapping, opportunity record, source record, review, or business data was changed for this reconciliation. No sync was started. The before/after taxonomy integrity snapshots match for all recorded digests: 291 Masters, 2,898 source rows, Master identity digest `c3bba55f…`, source-link/identity digest `02e09234…`, source Sector/Activity digest `6cd20d89…`, and raw-payload digest `714cf775…`. Only documentation changed: this report, its row-level CSV, and a link from the taxonomy README. No aggregation code change was required.

The aggregation result before and after reconciliation is the same because the API was already counting each eligible Master once. The correction is to the interpretation and documentation of the 290 change count.

```text
TOTAL_ELIGIBLE_MASTERS = 291
SUM_OF_CANONICAL_SECTOR_BUCKETS = 291
```

