# Invest Saudi dataset reconciliation

Snapshot date: **2026-10-12** (Asia/Amman). Collection used the four public REST endpoints with `GET`, `page`, and `per_page=100`. All 27 page requests succeeded, pagination completed, and each endpoint's reported total matched its collected row count. Full raw payloads: [`data/reconciliation/invest-saudi-snapshot-2026-10-12.json`](../../data/reconciliation/invest-saudi-snapshot-2026-10-12.json).

## Dataset Inventory

| Dataset | Endpoint | Requests | Reported / collected | Unique IDs | Duplicate IDs within dataset |
|---|---|---:|---:|---:|---:|
| Opportunities | `/backend/wp-json/v3/opportunities` | 18 | 1,771 / 1,771 | 1,771 | 0 |
| Investment projects | `/backend/wp-json/v3/investment-projects` | 5 | 431 / 431 | 431 | 0 |
| PIF opportunities | `/backend/wp-json/v3/pif-opportunities` | 2 | 184 / 184 | 184 | 0 |
| Regional opportunities | `/backend/wp-json/v3/regional-opportunities` | 2 | 138 / 138 | 138 | 0 |
| **Total endpoint rows** | 4 endpoints | **27** | **2,524 / 2,524** | — | **0** |

Each endpoint was requested without filters at 100 rows per page. Detailed fields, pagination parameters, sector/location schemas, and absent lifecycle flags are documented in [`invest-saudi-dataset-inventory.md`](invest-saudi-dataset-inventory.md).

The Investment projects total changed from **462 on 2026-10-11** to **431 on 2026-10-12**. The 31 prior IDs were collected in the successful 2,555-row snapshot at 2026-10-11 14:06 UTC and have each been absent from three subsequent successful complete snapshots; their dataset memberships are now `is_current=false`. Their retained source rows were last seen on 2026-10-11 between 13:45 and 14:07 UTC. All 31 still have raw observations and prior `NO_AL_AHSA_EVIDENCE` classification; none had a Master link. The source API provides no lifecycle status, so membership non-current after the configured threshold is the applicable source-removal state. The API does not expose status, archive, deletion, publication, or lifecycle fields, so they are described only as **not returned in the current snapshot**; they are not labeled archived or deleted. See [`invest-saudi-current-snapshot-delta.csv`](../../data/reconciliation/invest-saudi-current-snapshot-delta.csv).

## Official Identity Key

All four API collections expose integer `id`. This is the strongest shared stable identifier observed. Persisted identity fields are `official_source_id_original` (the original decimal text) and `official_source_id_normalized` (canonical decimal string); source key is `investsaudi:<id>`. Investment projects additionally expose a unique `modalData.opportunityNumber`, but no matching field was found in the other endpoint schemas. No GUID, cross-endpoint alias, or explicit language ID was supplied.

The adapter consolidates only exact official IDs from this source. Title similarity is never used to combine source records. Seven exact normalized title collision pairs were found across datasets; their official IDs differ, including two separate Opportunities IDs that share the title “Valves” with one PIF ID. Those rows remain separate; details are in [`invest-saudi-exact-title-collisions.csv`](../../data/reconciliation/invest-saudi-exact-title-collisions.csv).

## Set Cardinalities

Let A=Opportunities, B=Investment projects, C=PIF opportunities, and D=Regional opportunities, with each set defined by normalized numeric official `id`.

- `|A|=1,771`
- `|B|=431`
- `|C|=184`
- `|D|=138`
- `|A ∪ B ∪ C ∪ D|=2,524`
- Sum of endpoint rows = 2,524
- Duplicate endpoint membership rows = `2,524 - 2,524 = 0`

Membership distribution: exactly one dataset **2,524**; exactly two **0**; exactly three **0**; all four **0**. This produces a defensible **current public API unique-ID union of 2,524 records** for this snapshot. It does not establish how many records the publisher considers active because the API exposes no lifecycle state.

## Pairwise / Multi-way Overlap

All six pairwise and all four three-way intersections are zero; the four-way intersection is zero. The complete higher-order results are: `|A∩B∩C|=0`, `|A∩B∩D|=0`, `|A∩C∩D|=0`, `|B∩C∩D|=0`, and `|A∩B∩C∩D|=0`.

| Dataset | Opportunities | Investment projects | PIF opportunities | Regional opportunities |
|---|---:|---:|---:|---:|
| Opportunities | 1,771 | 0 | 0 | 0 |
| Investment projects | 0 | 431 | 0 | 0 |
| PIF opportunities | 0 | 0 | 184 | 0 |
| Regional opportunities | 0 | 0 | 0 | 138 |

Machine-readable matrix: [`invest-saudi-endpoint-overlap.csv`](../../data/reconciliation/invest-saudi-endpoint-overlap.csv). No endpoint overlap explains the difference from the UI number.

## UI Count Provenance

- **Page:** [https://investsaudi.sa/investment-opportunities](https://investsaudi.sa/investment-opportunities)
- **Section / language:** hero statistic above the opportunity listing; English page.
- **Displayed text:** `2,197` with label `Opportunities`.
- **Provenance:** the public frontend JavaScript bundle [`InvestmentOpportunities-CIdvyJwD.js`](../../data/reconciliation/InvestmentOpportunities-CIdvyJwD.js) contains the literal hero-card value `{value:"2,197",label:"Opportunities"}`. It is part of the frontend component, not a value calculated from the four API responses.
- **Network request / response field:** no request or response field supplying 2,197 was observed. The four public data endpoints paginate opportunity records; none supplied this hero count.
- **Filters/default state:** no count-specific filter or active/inactive setting is attached to the hero statistic. The page's actual listing is separately backed by API data. The hero component does not expose a record set, identity list, language split, category rule, or lifecycle cutoff.

Therefore the count is verified as a **hard-coded frontend editorial counter**, but what editorial population or cutoff its author intended is not documented by the page or API. It cannot be treated as a live count of all four current collections or as a verified active-only count.

## API vs UI Reconciliation

Current unique API ID union is **2,524**; the page displays **2,197**, a numeric difference of **327**. The earlier 2026-10-11 endpoint sum was 2,555, hence the originally observed difference of 358. The 31-record change came from Investment projects moving from 462 to 431; no evidence supports assigning an archived/deleted status.

A mathematical count difference is established, but ID-level `API_ONLY`, `UI_ONLY`, and `BOTH` sets are **not computable**: the hard-coded UI card supplies no IDs or query result to compare. Thus `unique API ∩ UI`, `API-only`, and `UI-only` are unknown, not zero. The page’s statistic has a different, non-live provenance than the API union, which explains why the two numbers are not a like-for-like metric. The specific business definition behind 2,197—and therefore the reason that editorial value is exactly 327 below today’s union—remains unverified. It is classified as `UNRESOLVED_NON_AUTHORITATIVE_UI_METADATA`. No evidence supports attributing the gap to overlap, language, status, filters, archive state, taxonomy multiplicity, or location multiplicity. The frontend value is excluded from endpoint completeness, `source_total_reported`, source health, and lifecycle decisions.

## Endpoint Membership Model

The latest sync exposes separate health metadata: `pagination_complete=true`, `dataset_count=4`, `datasets_complete=true`, `current_unique_source_records=2524`, `historical_missing_from_current_snapshot=31`, `ui_counter_observed=2197`, `ui_counter_authoritative=false`, `ui_counter_type=STATIC_FRONTEND_VALUE`, and `ui_counter_semantics=UNKNOWN`. The endpoint row count, unique ID count, duplicate membership count, additions, updates, historical removals, accepted/review/rejected classifications, and page errors are also separate fields in `/api/sources` and sync-job metrics.


A canonical view is represented by one `SourceOpportunity` row per `investsaudi:<id>`. Endpoint-specific representations are preserved as immutable `SourceObservation` payload versions; collection appearances are recorded in `SourceOpportunityDatasetMembership`; endpoint taxonomy values are stored in `SourceOpportunityTaxonomy`. This is exact source-identity consolidation, not fuzzy deduplication. Raw observations retain endpoint, dataset, full raw payload, source ID, content hash, and timestamps. Membership reconciliation is scoped by dataset, so a listing's disappearance from one collection does not erase its other collection membership. Memberships are deactivated only after three complete successful snapshots missing the ID.

## SourceOpportunity Impact

The historical database held 2,555 Invest Saudi `SourceOpportunity` rows from the earlier 2,555 endpoint-row snapshot. Current distinct endpoint IDs remain 2,524, and all 2,524 map one-to-one to canonical `investsaudi:<id>` rows. Since there was no overlap in either observed snapshot, no source rows were duplicative because of cross-endpoint membership; the 31 additional rows in storage are retained historical identities whose project memberships are no longer current.

Current database audit:

- Invest Saudi SourceOpportunity rows retained: **2,555**
- Distinct official IDs retained: **2,555**
- Current API unique official IDs: **2,524**
- Current dataset memberships: **2,524**
- Historical, no-longer-current project memberships: **31**
- Raw `SourceObservation` rows: **7,603**
- Source taxonomy memberships: **2,555**

The observation table includes migration backfills and payload-version rows created as the parser representation was enriched; it is a version/evidence count, not the count of current endpoint records. Current sync of the unchanged raw snapshot added no source rows or observation versions. Historical sync logs that report the earlier 2,555 endpoint rows remain unchanged and auditable.

## Al-Ahsa Classification Impact

Classification is performed once per consolidated official ID. On the current 2,524-ID snapshot:

- Explicit/local Al-Ahsa accepted: **6**
- Accepted through exact existing Furas opportunity-number linkage: **1**
- Location Review: **17**
- Rejected as non-Al-Ahsa: **2,500**

The totals reconcile to 2,524. The exact Furas-linked listing is Invest Saudi ID `54963`, linked to Furas source record 102 and master opportunity 102. It remains one Invest Saudi SourceOpportunity linked to the same master; both source records and their source URLs/identifiers are retained. The 17 review records each map to a distinct official ID; no overlap-induced review duplication was found.

## Database Impact

- Master rows: **223**
- Non-merged masters: **219**
- Active non-merged masters per dashboard status rules: **215**
- Historical `REMOVED_FROM_SOURCE` masters: **4**
- SourceOpportunity rows across all sources: **2,772**
- Multi-source masters: **5**
- Pending duplicate reviews: **0** (4 historical duplicate rows are completed `MERGED` decisions)
- Pending location reviews: **17**
- Open taxonomy conflicts: **10**
- Open field conflicts: **3**

Because current and prior snapshots had zero cross-endpoint ID overlap, endpoint overlap did not inflate taxonomy or field conflict queues. Multiple taxonomy values are represented as source taxonomy memberships, not as extra SourceOpportunity rows. The present 10 open taxonomy conflicts concern cross-source normalization decisions, not duplicate Invest Saudi endpoint rows.

## Regression Results

- All four endpoint paginations remain verified complete; current source record count and endpoint total are 2,524.
- Existing Furas (132/132), Al-Ahsa Investment Platform (74/74), and AHDA (213/213 pages; 7 qualified items) remain healthy and complete.
- Database is migrated to Alembic head `0011_invest_saudi_source_identity`.
- **Automated tests:** `pytest -q` — 35 passed, with one Starlette/httpx deprecation warning. Added coverage for same-ID consolidation, distinct IDs with same title, Arabic/English representations, two dataset taxonomy memberships on one source identity, per-dataset disappearance, and deactivation after three complete missing snapshots.
- **API smoke:** 13 checks across health, dashboard, sources/health metadata, validation report, sync jobs, duplicate reviews, location reviews, taxonomy conflicts, field conflicts, raw records, source content, and CSV/XLSX exports all returned HTTP 200. CSV and XLSX each contain 219 non-merged master rows.
- **Migration:** `alembic current` reports `0011_invest_saudi_source_identity (head)`.

## Final Conclusion

The four current public datasets contain **2,524 distinct official IDs**, with **zero cross-dataset overlap**. Thirty-one source-only identities from the prior snapshot remain stored with raw evidence and three confirmed missing checks; current sync does not count them as current API opportunities. The database uses the exact shared numeric `id` to retain one source identity, with independent endpoint memberships and raw observations. The 2,197 figure is a literal hard-coded frontend editorial counter rather than a live API count, and its semantics are undocumented. Internal source health is **HEALTHY** because `endpoint_completeness=PAGINATION_COMPLETE` and `unique_dataset_reconciliation=DATASET_RECONCILED` (2,524 endpoint rows = 2,524 unique official IDs + 0 duplicate memberships). The UI value is classified as `UNRESOLVED_NON_AUTHORITATIVE_UI_METADATA` and is excluded from API completeness and lifecycle decisions. Wave 2 is complete under the authoritative API-count policy in [the architecture decision record](../architecture/adr-invest-saudi-source-of-truth.md); the static counter does not block expansion.

## Required Numerical Summary

```text
Invest Saudi

Endpoint datasets: 4
Endpoint rows: 2,524 (2026-10-12; previous 2026-10-11 snapshot: 2,555)

Opportunities: 1,771
Investment projects: 431
PIF opportunities: 184
Regional opportunities: 138

Sum of endpoint rows: 2,524
Unique official IDs: 2,524
Overlap rows: 0

UI-displayed total: 2,197
UI total semantic meaning: hard-coded frontend editorial counter; population/cutoff undocumented

Unique API ∩ UI: unknown (UI provides no ID set)
API-only: unknown (no UI ID set for set difference)
UI-only: unknown (no UI ID set for set difference)

Unique Al-Ahsa accepted: 7 (6 direct + 1 exact Furas linkage)
Location Review: 17
Rejected: 2,500

Invest Saudi SourceOpportunity rows: 2,555 retained, of which 2,524 are current API IDs
Invest Saudi Raw Observations: 7,603 version/evidence rows
Invest Saudi Dataset Memberships: 2,524 current + 31 historical non-current

Latest sync: 0 new / 0 updated / 0 newly removed / 0 errors
Endpoint completeness: PAGINATION_COMPLETE
Unique dataset reconciliation: DATASET_RECONCILED
```
