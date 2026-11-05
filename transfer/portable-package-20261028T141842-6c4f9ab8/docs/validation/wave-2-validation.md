# Wave 2 validation

Validation run: 2026-10-12 (Asia/Amman)  
Scope: AHDA and Invest Saudi only; no Wave 3 source was enabled or implemented.

## AHDA — Al-Ahsa Development Authority

- **Extraction:** public sitemap discovery followed by server-rendered HTML requests with browser-like public headers. Only public pages were accessed; no authentication or access control was bypassed.
- **Target sections:** investment opportunities, major projects, investment sectors, business enablers, and media-center news, announcements, events, and press releases. Arabic and English sitemap entries were included. Content classification is based on URL/content evidence, not the menu label alone.
- **Live snapshot:** 213 sitemap-targeted pages, 213 content items parsed, 143 pages containing monitored investment keywords, 7 qualified opportunity records, 206 rejected as non-qualifying content, 0 attachment links, 0 errors after retry, and 100% page completeness. The crawl made 214 requests including the sitemap. Qualification remains conservative: actionable Arabic investment-opportunity pages can qualify; completed projects, general plans, investor meetings, and English-only investment pages do not qualify automatically.
- **Persistence:** all 213 pages are stored in the raw content layer with URL, title, date when available, classification, text, attachments, keywords, fingerprint, parser version, and extraction timestamp. The 7 qualified records use `SOURCE_SCOPE` location evidence; no city or district is inferred.
- **Change tracking:** a follow-up pass retries only failed pages after the concurrent scan. This recovered the single transient page failure and allowed a complete snapshot. A subsequent failure will leave the source in an incomplete-warning state and will not reconcile missing records.
- **Risk/limit:** no downloadable attachment was found in this snapshot. HTML parsing and sitemap coverage can change with publisher layout; parser warnings and incomplete status are exposed rather than treated as a healthy empty result.

## Invest Saudi

- **Current extraction snapshot (2026-10-12):** four public GET endpoints, `page`/`per_page=100`, all 27 requests successful, pagination complete, and endpoint totals matched collected rows. Current endpoint totals are Opportunities 1,771; Investment projects 431; PIF opportunities 184; Regional opportunities 138. Full schemas and request details are in [`invest-saudi-dataset-inventory.md`](invest-saudi-dataset-inventory.md).
- **Stable identity:** all four collections expose numeric `id`; normalized decimal ID is persisted in the canonical key `investsaudi:<id>`. Current union is 2,524 distinct IDs, with 0 repeated IDs within any dataset and 0 pairwise, three-way, or four-way intersections. The complete overlap matrix is in [`data/reconciliation/invest-saudi-endpoint-overlap.csv`](../../data/reconciliation/invest-saudi-endpoint-overlap.csv).
- **Previous snapshot change:** Investment projects decreased from 462 on 2026-10-11 to 431 on 2026-10-12. The 31 prior IDs are retained historically and their memberships were marked non-current after three complete successful snapshots. No lifecycle fields establish archive/deletion state; they are only described as not returned. Historical logs remain unchanged.
- **UI comparison:** the English Investment Opportunities page shows 2,197 in a hero statistic. Its frontend bundle contains the literal value; no request/response field or live result supplies it. The UI exposes no IDs, filters, or cutoff for the counter. The current numeric difference is 327 (the earlier endpoint sum of 2,555 differed by 358). This is not an ID-level comparison: API-only, UI-only, and intersection sets cannot be computed because the UI count has no corresponding identity list. The counter is a hard-coded editorial value with undocumented population semantics, so the numerical difference cannot be assigned to overlap, active/archive state, language, or filters. Full evidence and the remaining uncertainty are in [`invest-saudi-dataset-reconciliation.md`](invest-saudi-dataset-reconciliation.md).
- **Source identity and evidence:** Invest Saudi now stores one SourceOpportunity per exact official ID, endpoint membership rows, raw immutable endpoint observations, and dataset taxonomy memberships in separate relational tables. Same-title/different-ID rows remain separate. Seven title collisions are listed in [`data/reconciliation/invest-saudi-exact-title-collisions.csv`](../../data/reconciliation/invest-saudi-exact-title-collisions.csv). Current snapshot has no cross-endpoint overlap; total retained Invest Saudi source rows are 2,555, of which 2,524 correspond to current API IDs and 31 are historical. The database retains 7,603 observation versions/evidence rows and 2,555 taxonomy rows.
- **Al-Ahsa classification:** applied to each unique official ID once. Six direct local-evidence records and one exact Furas linkage were accepted; 17 unique IDs are in Location Review; 2,500 were rejected as non-Al-Ahsa. The Furas-linked Invest Saudi ID 54963 remains attached to Furas record/master 102. Totals equal the current 2,524-ID union.

## Invest Saudi Authoritative Population Decision

```text
Current API unique IDs: 2,524
Historical records absent from current snapshot: 31
Observed frontend counter: 2,197
Frontend counter implementation: Hard-coded / non-live
Frontend counter authoritative: No
Authoritative completeness basis: Four current public API datasets
Unresolved 327 difference: Non-authoritative UI metadata; semantic population undocumented
```

The official API identity union, not the hero counter, defines Invest Saudi discovery, completeness, and lifecycle monitoring. The 31 records have stable IDs and retained raw observations, were seen in the successful 2,555-row snapshot, and are absent from the latest successful complete snapshot. Their dataset memberships each passed three successful missing checks and are `is_current=false`; the source records and their observations remain in storage. The API supplies no official lifecycle state, so the records are not labeled cancelled. No current master links existed for these national-only historical records.

Current sync metrics separately expose endpoint rows, unique IDs, historical source-only IDs, Al-Ahsa accepted/review/rejected counts, additions, updates, removals, errors, four-dataset completeness, and the static UI metadata. Latest repeat sync returned 2,524 rows/IDs, 31 historical-only records, 0 new, 0 updated, 0 newly removed, 0 errors, and `PAGINATION_COMPLETE` / `DATASET_RECONCILED`. The UI value is marked `STATIC_FRONTEND_VALUE`, non-authoritative, with unknown semantics; it does not feed source health or `source_total_reported`. Observation history for counter inspections is in [`data/reconciliation/invest-saudi-ui-counter-history.csv`](../../data/reconciliation/invest-saudi-ui-counter-history.csv).

Architecture decision: [`adr-invest-saudi-source-of-truth.md`](../architecture/adr-invest-saudi-source-of-truth.md).

## Cross-source matching and taxonomy

- The live Invest Saudi snapshot was matched against existing masters from all four enabled sources. One exact Furas opportunity-number linkage was confirmed. There are 5 multi-source masters overall and 0 pending identity duplicate candidates.
- No known false merge was identified in the live records. Four historical merge audits remain intact. The 4 `MERGED` duplicate-candidate rows are historical completed actions, not pending reviews.
- The database contains 10 open `TAXONOMY_CONFLICT` rows and 3 open `FIELD_VALUE_CONFLICT` rows. The eight pre-Wave-2 sector/activity conflicts remain classified as taxonomy conflicts. The Wave 2 source taxonomy is retained separately from its normalized broad sector; 110 taxonomy mapping rows exist across sources after the expanded backfill.
- Location review is separate from duplicate review. The live location queue has 17 pending Invest Saudi records. The dashboard/API exposes the review list and accept/reject actions.

## Regression, exports, and migrations

- **Existing source snapshots:** Furas completed 132/132 (100%; unchanged); Al-Ahsa Municipality completed 74/74 (100%; unchanged).
- **AHDA:** 213/213 content items (100%; 7 qualifying, 206 rejected); **Invest Saudi:** current 2,524/2,524 endpoint records (100%; 7 accepted, 17 review, 2,500 rejected); prior 2,555-row snapshot remains in historical logs.
- **Database after backfill:** 2,772 source records, 213 AHDA content items, 223 master rows including 4 merged rows, 219 non-merged masters, 215 active non-merged masters, 4 historical removed masters, 5 multi-source masters, 0 pending duplicate reviews, 17 pending location reviews, 10 open taxonomy conflicts, and 3 open field conflicts. No new source was added beyond the four Wave 2 sources.
- **Tests:** `pytest -q` — 35 passed, with one Starlette/httpx deprecation warning. Added identity consolidation, language-representation, taxonomy membership, membership disappearance, and three-successful-snapshot regression cases.
- **API smoke:** 13 checks passed across health, dashboard, sources/health metadata, validation report, sync jobs, duplicate review, location review, taxonomy conflicts, field conflicts, raw records, source content, and CSV/XLSX exports. All returned HTTP 200; CSV and XLSX each expose one row per non-merged master (219).
- **Migrations:** Alembic is at `0011_invest_saudi_source_identity (head)`.
- The Furas/Al-Ahsa live syncs ran before the final AHDA retry and Invest Saudi expanded snapshot; their final reported source state remained healthy, complete, and unchanged. Their latest metrics are included above.
- The validation API reports 3 historical source-error rows from earlier incomplete/rejected attempts (2 transient AHDA page failures and the Invest Saudi taxonomy-shape error fixed before the successful retry). Both latest Wave 2 snapshots completed with 0 errors; the historical error rows remain for audit.

## Expansion gate

`READY_FOR_WAVE_3`

Wave 2 is complete. Current population and historical-only records are separately defined; the 2,197 hard-coded UI value is explicitly non-authoritative and excluded from endpoint completeness and health decisions. The latest repeat Invest Saudi sync reproduced 2,524 current official IDs with no additions, updates, newly removed records, or errors; 31 historical records remain preserved. All four source integrations remain healthy. Full tests, API smoke, review queues/conflicts, exports, and Alembic head pass. No Wave 3 source was implemented.
