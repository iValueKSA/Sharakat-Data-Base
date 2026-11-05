# First Live Integration Validation

**Validation date:** 11 October 2026 (Asia/Amman)  
**Scope:** Furas and Al-Ahsa platform only. No additional source adapters were implemented.

## Executive result

The two collectors reconcile to their current source snapshots: Al-Ahsa has 74 visible listings and Furas has 132 currently active Al-Ahsa features. Both latest snapshots report 100% completeness and complete pagination. Following duplicate review and merges, repeat syncs of both sources are idempotent.

The four highest-priority cross-source pairs were reviewed against live Al-Ahsa detail pages and official Furas GIS feature data. All four were confirmed duplicates and manually merged with recoverable audit state. Current counts are 206 non-merged masters (202 active plus four historical removed masters) and 210 source listings. **Recommendation: `READY_TO_EXPAND`.**

## Furas

### Extraction and geographic filter

- **Extraction method:** public ArcGIS REST JSON through the proxy used by the official Furas GIS application.
- **Configuration:** `https://gisapps.balady.gov.sa/opportunities/assets/config.json` identifies the public layer.
- **Layer:** `https://gisOppertunities.momra.gov.sa/arcgis/rest/services/GISProjects/InvestmentView/MapServer/0`
- **HTTP method:** `GET` for the ID query and feature batches.
- **Query operation:** proxy request to `/query`, first with `f=json`, `returnIdsOnly=true`, and then with `OBJECTID IN (...)`, `outFields=*`, and `returnGeometry=true`.
- **Al-Ahsa city IDs:** `1949`, `1945`, `1950`, `005011001`, `9`, `1264`, `1315`, `1299`, `1298`, `104`, `005020001`. They were checked against `CITYNAME` values in the same public feature layer and against the official map client’s `CITY_ID` filter.
- **Exact active filter on the validation date:**

```text
CITY_ID IN ('1949','1945','1950','005011001','9','1264','1315','1299','1298','104','005020001')
AND LASTRFPSELLDATE >= DATE '2026-10-11'
AND OPPORTUNITYACTIVESTATUS='Announced'
AND QualifyingOpportunity=0
```

- **Batch size:** 100 feature IDs. The 132 IDs required one ID query and two feature requests, for 3 successful API requests total.
- **Current collection:** 132 source IDs reported, 132 feature rows received and parsed, 132 unique records, 132 accepted, 0 rejected, 100% complete, pagination complete.
- **Location evidence:** records use `location_detection_method=SOURCE_FILTER`; the raw API attributes, geometry, `CITY_ID`, city name, and exact filter are retained. The classifier does not rely on a mention of “المنطقة الشرقية”. When an individual feature has an empty `CITYNAME`, its included `CITY_ID` still provides the geographic evidence.
- **20-record sample:** [furas-geographic-sample.csv](furas-geographic-sample.csv) selects records at evenly spaced positions through the returned feature set. Titles, owners, city/location, references, and IDs were read from the official GIS feature attributes. Canonical Furas detail URLs are included. Direct HTTP checks of the detail routes timed out after 15 seconds, so the sample does not claim page-level detail verification.

### Count reconciliation

The original milestone stored 133 Furas records. The corrected active filter now returns 132. Since the milestone snapshot, 3 newly active records were observed and 4 previously stored records were returned by the source as `Deleted`; those four reached the configurable three-complete-scan removal threshold and remain preserved as source/master history with status `REMOVED_FROM_SOURCE`. This explains the 133-to-132 active change. The current database retains 136 Furas source records: 132 in the latest active snapshot and 4 previously observed deleted records.

| Reconciliation item | Current result |
|---|---:|
| UI advertised count | No aggregate total was exposed by the public map UI inspected |
| API total under the exact active Al-Ahsa filter | 132 |
| API requests / feature batches | 3 / 2 |
| Records received / parsed / unique | 132 / 132 / 132 |
| Accepted / rejected | 132 / 0 |
| Active / expired in this active-only query | 132 / 0 |
| Missing from adapter | 0 |
| Collection completeness | 100% |

## Al-Ahsa platform

### Collection and pagination

- **Extraction method:** server-rendered HTML cards. No public JSON API, relevant XHR/fetch endpoint, or JavaScript-only card loading was found in the inspected pages.
- **Pagination:** numbered query pages `?page=1` through `?page=9`. The first page contains 9 cards; pages 2–8 contain 9 each; page 9 contains 2. The adapter reads the maximum page number and visits each page. It deduplicates by the numeric detail-link ID.
- **Sections:** public category links advertise 72 general opportunities, 2 featured opportunities, and 0 direct-lease opportunities. The 72 and 2 IDs are disjoint, producing 74 unique listings. The default paginated listing also contains those 74 IDs.
- **Status filters:** the public `status=متاحة` query returns 74 cards; `status=منتهية` returns 0. All 74 visible cards carry the “متاحة” badge and none has a deadline before 11 October 2026.
- **Stable IDs:** numeric ID from `/opportunities/{id}`.
- **Classification:** the platform is scoped to Al-Ahsa. Every card is tagged `SOURCE_FILTER` with its card location and title retained as evidence. This fixed 3 missed classifier results for listings in جواثا; the source total was complete even before the change, but those three were incorrectly rejected by the text classifier.

| Reconciliation item | Current result |
|---|---:|
| Source-advertised category total | 72 general + 2 featured + 0 direct lease = 74 |
| API-reported total | Not applicable; no API found |
| UI-visible unique total | 74 |
| Adapter collected / parsed / unique | 74 / 74 / 74 |
| Accepted / rejected | 74 / 0 |
| Active / expired by source badge | 74 / 0 |
| Missing from adapter | 0 |
| Pages requested / successful | 9 / 9 |
| Collection completeness | 100% |

The main platform is [alahsa-opportunities.com](https://alahsa-opportunities.com/).

## Deduplication and review completion

- Same-source idempotency uses the stable source opportunity ID. Fuzzy resolution runs across different sources only.
- Candidate generation, scoring, and merge authorization are separate. Reference normalization handles Arabic digits and punctuation. Ranking features include core title after removing standard Furas activity suffixes, owner aliases, locality/GIS, area, parcel/plan, contract term, and dates. Missing features remain unknown. The description feature is explicitly a title proxy.
- Tier 1 auto-merge requires a matching normalized official reference or propagated official source identifier. Tier 2 requires title similarity ≥ 0.92, same normalized owner, exact parcel or subdivision plan, compatible area and known duration, no parcel/owner contradiction, and overall score ≥ 0.90. Title alone or generic city/area cannot authorize automatic merge. Scores are ranking signals, not probabilities.
- All four priority candidates were checked against Al-Ahsa live opportunity pages and official Furas GIS feature responses, using `OFFICIAL_GIS_API` for Furas. They are confirmed duplicates and were merged manually after review. Pair 4 scored 0.741 because its GIS location is coarse; the score threshold was not lowered. Detailed pair evidence and decisions are in [cross-source-duplicate-review.md](cross-source-duplicate-review.md).
- Master count before review: 210. Four master pairs merged; current non-merged masters: 206 (202 active and four historical removed masters). The 210 source rows are unchanged; four masters now have two source rows each. Pending duplicate candidates: 0. All source raw payloads, source IDs, titles, URLs, and timestamps remain preserved.

## Data quality and architecture

- Master opportunities remain separate from source listings. There are 206 current non-merged masters (202 currently active and four historical `REMOVED_FROM_SOURCE` masters) and 210 source records. Each of the 74 Al-Ahsa and 136 historical/current Furas source rows retains its own original IDs, titles, reference, URL, owner, raw location/area/date/status, raw JSON, content hash, and parser version. Four Furas source rows marked `Deleted` remain preserved, historical, and classified `DELETED_FROM_SOURCE`, not `CANCELLED`.
- Field-level source provenance remains attached. The four merge audits store the survivor and archived master IDs, source-record IDs, timestamp, evidence/reason, actor, and target before/after snapshots. Archived master rows are soft-linked and can be restored through the admin undo endpoint. Field selection uses source authority with per-field provenance; lifecycle and owner aliases are normalized without erasing source values.
- There are 8 open field conflicts across the confirmed pairs for differing sector/opportunity taxonomy values. The source values remain linked and auditable. Forty-two portal-format, owner-alias, lifecycle-equivalent, publisher, and reviewed location-precision differences were explicitly resolved while retaining raw source evidence. No unresolved identity decision remains.
- Fresh complete syncs report Furas 132/132 active records and Al-Ahsa 74/74 visible records; both have 100% completeness and complete pagination. A subsequent repeat scan reports zero new, updated, or newly merged records. No merged opportunity was recreated as a master.
- Lifecycle values distinguish `ACTIVE`, `EXPIRED`, `DELETED_FROM_SOURCE`, `CANCELLED`, `AWARDED`, and `UNKNOWN`; raw source status remains available. `Deleted` is not mapped to cancellation.

## API and export checks

- HTTP 200 smoke checks passed for the home page, health, dashboard, opportunities, sources, admin jobs, validation report, duplicate review, merged duplicates, conflicts, CSV, and XLSX. Duplicate review has 0 pending candidates and 4 completed merges.
- Dashboard metrics report 206 unique master opportunities, 210 source listings collected, and 4 multi-source opportunities. The opportunities API returns 206 non-merged masters, including four explicitly historical `REMOVED_FROM_SOURCE` records; the dashboard active metric excludes those records and reports 202.
- CSV and XLSX each contain 206 data rows (one per current non-merged master, including four historical removed masters), 18 columns, and the joined `المصادر` field alongside source count. CSV is UTF-8 with BOM; XLSX is right-to-left with numeric area values.
- Automated tests: 20 passed. Python compilation, JavaScript syntax check, and Alembic head check passed. The isolated admin API test exercises merge→undo and verifies restored canonical fields, master/source links, provenance, conflicts, and change history. A transaction-rolled-back undo check against a live audit also verified the actual source/master links and removal of all four merge-generated history rows without changing the final merged state.

## Final recommendation

```text
READY_TO_EXPAND
```

All four current duplicate candidates have documented decisions and confirmed pairs have reversible audited merges. No candidate remains queued. The current master/source counts reconcile (206 / 210), historical deleted Furas records remain preserved, both source syncs are complete and idempotent, exports and dashboard counts are correct, API smoke tests pass, and merge/undo is covered by an API test. The duplicate review does not implement AHDA, Invest Saudi, or any other additional source.
