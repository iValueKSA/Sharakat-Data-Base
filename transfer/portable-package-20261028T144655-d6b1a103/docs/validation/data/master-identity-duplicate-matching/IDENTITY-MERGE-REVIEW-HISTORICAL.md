# Master Identity / Duplicate & Cross-Source Matching Deep Review

**Result:** `MASTER_IDENTITY_DUPLICATE_CROSS_SOURCE_DEEP_REVIEW = NOT_COMPLETE`  
**Project:** Al-Ahsa Investment Opportunities Platform  
**Database:** local `sharakat_local`  
**Fixed pre-correction snapshot:** 2026-10-20 09:27:35.377973 UTC  
**Post-correction snapshot:** 2026-10-20 09:59:32.899366 UTC  
**Standardization Engine:** 21  
**Identity Matching Policy:** 2

Identity screening and all confirmed duplicate corrections are complete. Acceptance remains NOT_COMPLETE because 2,599 SourceOpportunity rows have no current Master root, while this task requires every source row to resolve to exactly one current Master. They remain source-only rather than being attached to unrelated Al-Ahsa Masters or promoted speculatively. Eleven unlinked Invest Saudi records contain Al-Ahsa-specific title/description text but are marked qualified_location=false and need an explicit scope decision. No uncertain identity was forced into a merge. Sixteen confirmed false splits were merged reversibly.

## A. Snapshot, scope, and scheduled-sync boundary

| Measure | Before | After |
|---|---:|---:|
| Master rows | 297 | 297 |
| Current/non-merged Masters | 292 | 276 |
| Historical/merged Masters | 5 | 21 |
| SourceOpportunity rows | 2,899 | 2,899 |
| Source observations | 11,150 | 11,150 |
| Duplicate-candidate rows | 31 | 47 |
| Open duplicate candidates | 26 | 10 |

The intended current identity population is every `Opportunity` with `merged_into_id IS NULL`, not all Master rows. Merged Master rows remain in the database as history and are excluded from current list, dashboard, search, pagination, map, and exports. Current SourceOpportunity ownership is evaluated through the current Master root; no linked SourceOpportunity is left on a merged Master.

Natural scheduled syncs were not initiated by this review. Job 376 was scheduled and received 164 records; the prior natural sequence produced the 13-observation increase from 11,137 to 11,150. Job 377 was also scheduled (103 records received, 0 new, 0 duplicate, 0 merged) and had no identity, source-row, or observation-count delta. The post snapshot still has 11,150 observations. No sync was manually requested or triggered.

## B. Identity architecture and matching rules

The data model keeps Master identity separate from source listings:

- A Master is one current opportunity identity.
- A SourceOpportunity is one source-specific listing and has one `master_opportunity_id` pointer (or is intentionally unlinked source-only evidence).
- `(source_id, source_opportunity_id)` is unique. A source external ID is source-scoped and is never compared across portals as if globally unique.
- `merged_into_id` preserves old Master identities. `MergeAudit` stores before/after canonical snapshots, source record IDs, child-record ownership, evidence, timestamp, and actor. `undo_candidate` restores the source/child links and the prior Master snapshot.
- List, detail, dashboard, and export paths query Master rows. The list query explicitly excludes merged rows; source multiplicity is summarized on the Master response and does not create duplicate rows.

`app/entity_resolution.py` declares policy version 2. Verified cross-source official references are restricted to source semantics: Furas uses raw `attributes.OPPORTUNITYID`, and Invest Saudi uses `modalData.opportunityNumber` only for the `project` family. In both cases the raw official value must agree with the stored source reference. Furas GIS `OBJECTID`, Invest Saudi numeric backend IDs, and generic listing URLs are not official opportunity references.

Matching signals are interpreted as follows:

| Signal | Use and weight |
|---|---|
| Verified official reference | Strong identity evidence; only source-verified reference fields participate. Cross-source exact match can trigger safe attachment when there is exactly one compatible match and no contradiction. |
| Source external ID | Strong only within its own source. It retrieves/upserts that source listing; it is not a cross-source identifier. |
| Parcel / plot and plan | Strong site identity support. Conflicting explicit parcels block a merge. |
| Owner / publisher | Supporting evidence. Publisher is not substituted for asset owner. A conflict blocks automatic merge. |
| Location / coordinates | Supporting evidence. Locality alone is broad; coordinates measure proximity but do not establish identity alone. |
| Area | Supporting evidence; small rounding differences may be compatible. A material difference stays review unless unit/source detail resolves it. |
| Duration / deadline | Supporting and temporal evidence. A different cycle/reference can represent a reissue; these values alone never merge. |
| Title | Weak candidate-generation support. Fuzzy title alone never auto-merges. Arabic orthographic, punctuation/spacing, Arabic digit and known bilingual-token normalization preserve numeric/site identifiers such as plot numbers. Semantic translation is not used as sole evidence. |
| Sector, activity, type, lifecycle status | Classification or lifecycle context, not identity keys. Semantic incompatibility may block a comparison; matching labels do not prove identity. |
| Same-source exact article URL + normalized title | Narrow technical-alias exception in the reversible merge workflow. Broader same-source fuzzy matches remain review-only. |

The explainable score weights are title .35, location .25, area .20, owner .08, duration .05, deadline .04, and plot/plan .03. It ranks candidate evidence; it is not a factual probability. Automatic cross-source matching requires distinct sources, semantic compatibility, no parcel/owner/verified-reference conflict, and either a verified official reference or a strong composite with title, owner, parcel/plan, compatible area and score threshold. Same-source fuzzy comparisons cannot trigger automatic merges.

Reissue rule: same-source listings with changed external IDs or URLs remain separate when they may be a new tender, amended listing, phase, or publication cycle. Keep them in review until source publication history or exact technical alias evidence proves duplication. A new official reference for the same site is not silently collapsed into the prior opportunity.

## C. Source-specific external IDs and source coverage

All external IDs below are scoped to their own source. Their reuse across historical source versions was not asserted unless an adapter exposes a stable listing key. Official references are a separate field and require source-specific verification.

| Official source | Source-local external ID semantics | SourceOpportunity rows | Linked to current Master | Unlinked source rows |
|---|---|---:|---:|---:|
| Furas | Furas `OPPORTUNITYID` / opportunity path ID. It also supplies the official reference; GIS `OBJECTID` is technical and excluded. | 177 | 177 | 0 |
| Al-Ahsa Opportunities | Numeric listing path ID (for example `/opportunities/505`), unique within this source; no propagated official reference in the current rows. | 103 | 103 | 0 |
| AHDA | Canonical public detail URL is the source-local key; no separate official reference was exposed in the linked records. | 8 | 8 | 0 |
| Invest Saudi | `investsaudi:<item-id>` is a backend/source-local key. `opportunityNumber` is an official reference only for verified project-family records; numeric item IDs are not cross-source references. | 2,555 | 8 | 2,547 |
| King Faisal University | `kfu-announcement:<content fingerprint>` identifies an announcement; it is not an official opportunity reference and may change when page content changes. | 6 | 3 | 3 |
| MODON | No current SourceOpportunity rows; no listing-ID stability claim is made from this snapshot. | 0 | 0 | 0 |
| NCP | Source-local article/project key (`ncp:` or `ncp-project:`); article URL and title are used only for the exact same-article alias case. Not an official opportunity reference. | 45 | 1 | 44 |
| NHC | No current SourceOpportunity rows; no listing-ID stability claim is made from this snapshot. | 0 | 0 | 0 |
| PIF | Adapter uses an explicit public item ID when present, otherwise a source-local fingerprint; no current SourceOpportunity rows. No cross-source reference is inferred. | 0 | 0 | 0 |
| MWAN | Source-local `mwan:` key based on a Furas-linked identifier or page slug. An embedded cross-link is not promoted to an official reference unless verified by source semantics. | 5 | 0 | 5 |
| **Total** |  | **2,899** | **300** | **2,599** |

The 2,599 unlinked records are source-only records retained from broader public source populations, and were not changed by this review. They are not orphan Master rows, but they violate this task’s literal acceptance rule that every SourceOpportunity resolve to one current Master. Every one of the 276 current Masters has at least one SourceOpportunity; no linked record points to multiple current Masters. A read-only locality text screen found 14 unlinked records mentioning Al-Ahsa: 11 Invest Saudi records have DESCRIPTION_ONLY_EXPLICIT_AL_AHSA but qualified_location=false; one Invest Saudi item is a multi-region listing with raw location Al Madinah; one KFU record is a campus procurement announcement, not an opportunity; and one NCP item covers five municipalities across multiple regions. The 11 Invest Saudi items need geographic-scope adjudication before promotion or linking. They were not assigned to Masters by title alone. See unlinked-locality-screen.csv. The source external-ID and official-reference screens found no cross-Master source-ID collision and no exact official reference split across current Masters. The generic Invest Saudi listing URL appears on Masters 102 and 230; it is a portal URL, not an item detail URL, and was not treated as identity evidence.

## D. Candidate generation and same-source screen

The pre-correction screen covered all 292 current Masters and all 42,486 unordered Master pairs. Its broad generators produced 1,261 raw pair hits; those are screen hits, not 1,261 presumed duplicates. Recomputed from the source records attached to each pair, the raw hits comprise 1,219 same-source-only pairs, 27 cross-source-only pairs, and 15 pairs with both scopes (1,261 unique pairs). The broad evidence flags occur on 1,222 same-source pairs and 20 cross-source pairs, with one pair in both; 20 additional historical queue hits had no source-scope flag in the analyzer evidence.

The analyzer's displayed `cross_source_candidate_pairs=1241` was a labeling defect: its code counted generic title/owner/location and title/area/location methods as cross-source even when the evidence was not cross-source. The corrected source-key reconciliation is recorded in `candidate-screen-reconciliation.json` and the full 1,261-row `candidate-pairs.csv`.

- 42 unique actionable pairs were adjudicated: 16 confirmed cross-source duplicates, 16 confirmed distinct pairs, and 10 retained for review. Same-source and cross-source candidate scopes overlap by 12 pairs because some Masters already held listings from multiple sources.
- The remaining 1,219 raw hits were screened out: 1,082 have explicit parcel/plot conflicts and 137 lacked sufficient independent identity evidence for the manual queue.
- Same-source title screen: 1,650 pairs at title similarity ≥ .85. Of these, 1,642 had no independent identity support; eight site/title cases remain review-required. No same-source duplicate was confirmed.
- The five pre-existing historical merges are audited separately in `existing-merge-audit.json`; they are not counted as candidate pairs.

Open same-source pairs:

`155–156`, `155–159`, `156–159`, `157–160`, `158–161`, `163–254`, `197–198`, `263–264`.

These include identical titles and plot/plan text but different source listing IDs/URLs. They remain separate and review-required; no same-source fuzzy merge was applied.

## E. Cross-source candidates, false splits, and distinct pairs

The initial queue held 26 cases. Pair-level source membership shows that source scopes can overlap, so the final adjudicated set is reported as 34 cross-source and 20 same-source candidate occurrences (12 overlap; 42 unique pairs). Cross-source results are 16 confirmed duplicates, 16 distinct, and 2 review-required. Same-source results are 0 confirmed duplicates, 12 distinct, and 8 review-required. Decisions rely on record-level evidence, not title score alone.

**Ten confirmed false splits from the original queue were merged, retaining the established queued survivor:**

| Candidate | Survivor | Merged history row | Confirming evidence |
|---:|---:|---:|---|
| 7 | 163 | 233 | Lot 5 / plan 19/149; same exact 11,099 m² asset and matching opportunity description/site. |
| 20 | 231 | 265 | Plot T20 / plan 4/1082; exact 2,448.7 m², same owner/site and listing description. |
| 21 | 248 | 266 | Same numbered drive-through kiosk on King Fahd Road, Al-Mubarraz; exact site/title and area. |
| 22 | 251 | 267 | Same drive-through kiosk on Gulf Road, Hofuf; exact site/title and area. |
| 23 | 258 | 268 | Same drive-through kiosk at King Abdullah Road / Al-Amer Mall extension; exact site/title and area. |
| 24 | 246 | 269 | Same numbered (2) kiosk on Prince Abdullah bin Jalawi Road; exact title/site and area. |
| 25 | 242 | 270 | Same numbered (1) kiosk on Prince Abdullah bin Jalawi Road; exact title/site and area. |
| 28 | 262 | 273 | Same salvage-yard plot 67/1, plan 518/4 and 5,223 m². Raw titles agree; the parser’s tokenization had flagged a false plot conflict. |
| 29 | 260 | 274 | Same salvage-yard plot 60, plan 518/4 and 9,982 m², owner/site. |
| 30 | 235 | 276 | Same warehouse plot 485, plan 14/16 and 712 m², owner/site. |

These ten corrections retain every original Master row and relink the source records through the standard `merge_candidate` operation. Each has a MergeAudit with before/after snapshot and can be undone.

**Six additional cross-source false splits found in the raw broad screen were also confirmed and merged:**

| Candidate | Survivor | Merged history row | Confirming evidence |
|---:|---:|---:|---|
| 40 | 234 | 236 | Furas/Al-Ahsa warehouse, plot 484 / plan 14/16, 653.74 m², matching title and site; Furas ref `01-26-017001-26003`. |
| 41 | 237 | 252 | Furas/Al-Ahsa commercial plot B1 / plan 15/28 at Jawatha, 2,000 m², matching title/site; Furas ref `01-26-017001-30001`. |
| 42 | 239 | 247 | Factory/workshop plot 214 / plan 14/16, 464.52 m², matching title/site; Furas ref `01-26-017001-34002`. |
| 43 | 240 | 243 | Factory/workshop plot 54 / plan 14/16, 538.72 m², matching title/site; Furas ref `01-26-017001-34005`. |
| 44 | 241 | 244 | Mixed-use plot 2030 / plan 187 at Al-Saifa, 2,513.16 m², matching title/site; Furas ref `01-26-017001-40001`. |
| 45 | 253 | 261 | Mixed-use plot 12 / plan 4/253, 1,991 m², matching title/site; Furas ref `01-26-017001-1`. |

The established survivor rule is: retain the lowest pre-correction Master ID within a proven duplicate pair; this matches the reviewed queue's prior survivor choices and is deterministic. For all six new pairs, the survivor also retains the Furas record carrying the source-verified official reference. Each new merge has a reversible MergeAudit and preserves the other source listing.

**Sixteen pairs are confirmed distinct and were rejected without changing Master/source ownership:** candidate IDs `6, 8–19, 26, 27, 31`. Their decisive conflicts are different explicit parcels/plots or different asset types; examples include lot 11 vs lot 12 (Masters 191/249), salvage-yard plot 67/1 vs equipment/office plots T82/T84/T85 (Master 262 vs 271/272/277), and Master 193 plot 471 vs separate plots 54, 122, 214, 483, 484, 485, or 524. The 16 IDs and pair-by-pair reasons are in `confirmed-distinct-pairs.json` and `candidate-pairs.csv`.

Two additional kiosk pairs remain separate and pending: `107–186` has a highly similar 15 m² university-walkway listing but lacks an Al-Ahsa official reference and precise matching site evidence; `107–187` says Diyar Al-Ahsa promenade opposite the university, which may be a separate nearby kiosk. Both require source-level location/detail confirmation. After review: 16 confirmed cross-source duplicates were merged, 16 cross-source candidate pairs were confirmed distinct, 12 same-source candidate pairs were confirmed distinct, eight same-source cases and two cross-source cases remain pending. No fuzzy-title-only merge was made.

## F. Multi-source Master reconciliation and false-merge audit

Post-correction there are 24 current Masters with multiple source listings: 23 identity-confirmed, 1 review-required, 0 incorrectly linked.

- Confirmed Masters: `102, 163, 164, 192, 193, 195, 226, 231, 234, 235, 237, 239, 240, 241, 242, 246, 248, 249, 251, 253, 258, 260, 262`.
- Review required: **Master 230**. The Furas and Invest Saudi listings carry the same verified official reference `06-26-183737-49010`, but the Invest Saudi `siteArea=64` has no comparable unit and differs from Furas 160 m². The identity remains linked based on the verified reference; both source values are preserved and the discrepancy remains an explicit fact review. It is not classified as a confirmed false merge.
- Incorrect multi-source identities: 0.

Master 230 is the single suspect-false-merge review signal in the current multi-source set; it is not a confirmed false merge. `SUSPECT_FALSE_MERGES=1`, `CONFIRMED_FALSE_MERGES=0`, and no split was improvised.

All five pre-existing merges were individually audited and confirmed valid:

| Historical merged Master | Survivor | Result |
|---:|---:|---|
| 74 | 195 | Valid: same industrial parcel(s) 461/1 and 461/2, plan 14/16, 752.34 m², owner, term and deadline. |
| 140 | 164 | Valid: same gas-cylinder storage/distribution facility, site and source details. |
| 75 | 193 | Valid: same industrial plot 471 / plan 14/16, area and deadline. |
| 135 | 192 | Valid: same equipment/transportation, workshop and office site for plots 405/T–409/T, plan 14/154. |
| 229 | 228 | Valid same NCP news article alias: exact official URL and normalized title; the changed external-ID scheme did not create a new opportunity. |

Historical merge outcome: 5 audited, 5 valid, 0 review-required, 0 incorrect. `existing-merge-audit.json` includes the original reasons, evidence, references, source rows and preserved snapshots.

## G. Source-link and reference reconciliation

| Assertion | Result |
|---|---:|
| SourceOpportunity rows with a current Master root | 300 |
| SourceOpportunity rows without a Master | 2,599 |
| Linked source rows still pointing at merged Master rows | 0 |
| SourceOpportunity rows linked to multiple current Masters | 0 |
| Current non-merged Masters with zero linked sources | 0 |
| Source external-ID collisions across current Masters | 0 |
| Exact official references split across current Masters | 0 |
| Verified exact cross-source references on the same Master | 2 |
| Reference collisions requiring review | 0 |

The 16 relinks are the documented false-split corrections only. No SourceOpportunity, raw payload, source observation, or Master row was deleted. The current map endpoint returns 176 exact-mapped Master IDs and 176 unique IDs (0 repeated Master IDs), so source multiplicity does not duplicate map opportunities.

## H. Reissue, Arabic/English, and future-ingestion safeguards

Arabic normalization converts Arabic digits for comparison, normalizes punctuation/spacing, and supports a bounded bilingual vocabulary while retaining numbers such as plot and plan identifiers. The comparison normalizer does not remove numeric lot/phase identifiers. Arabic/English title resemblance is candidate evidence only; it cannot merge without a verified reference or independent site/owner/area evidence.

For future ingestion, the source-local external ID first upserts the same source listing. A verified source-semantic official reference or a strong cross-source composite may attach the listing to one current Master only when unambiguous and conflict-free. Same-source fuzzy matches, unknown references, conflicting references/parcels, and ambiguous composites stay in `duplicate_candidates` for review. The current code does not use technical Furas or Invest Saudi IDs as official references.

## I. API, UI, dashboard, search, map, and exports

Live platform was already running and remained ready; API and worker were rebuilt/recreated from the local project code to load identity policy v2. Scheduler, database, Redis and frontend were not reset. `/health/ready` reported database, Redis and worker healthy.

- Current opportunities API: 276 total, 276 returned in the 500-row verification request, 276 unique Master IDs.
- Each current multi-source Master appears once with `source_count=2`; details for Masters 163 and 234 return the Al-Ahsa + Furas source records together. Master 234 is one of the six additional reconciled pairs.
- Master 233 (a merged history row) does not appear as a separate current list row.
- Search for plot 485 returned one current Master (235), not source-row duplicates.
- UI page size is 50; first and second pages had zero overlapping Master IDs.
- Source filter for Al-Ahsa returned 103 unique current Masters.
- Default Data Dashboard KPI total is 276 and matches the current Master API total; the dashboard filter reset was used before comparison.
- The geo API returns unique current Master IDs; no duplicate map point arose from the merged source multiplicity.
- CSV export: HTTP 200, exactly 276 data rows; the opportunity-title multiset matches the 276-item API result.
- XLSX export: HTTP 200, exactly 276 opportunity data rows (six header/metadata rows are separate); the opportunity-title multiset also matches the API.
- Playwright verified the list, search, owner filter selection, pagination, detail modal with two sources, dashboard, CSV/XLSX endpoints, RTL and five viewport sizes. Every viewport had no document/body horizontal overflow.

Viewport checks: `1920×1080`, `1440×900`, `1366×768`, `768×900`, and `390×844`.

Screenshots and browser evidence:

- [Opportunity list — 1920×1080](screenshots/opportunities-1920x1080.png)
- [Opportunity list — 390×844](screenshots/opportunities-390x844.png)
- [Data Dashboard — 1920×1080](screenshots/identity-dashboard-1920x1080.png)
- [Playwright results](playwright-results.json)
- [CSV/XLSX row reconciliation](export-identity-reconciliation.json)

## J. Data safety, regression, and closed dimensions

The source payload SHA-256 is identical before/after (`bd3b6a…babf2a`), and the observation SHA-256 is identical (`4cfee4…f8f6cdf6`). The SourceOpportunity rows and all Master rows remain present. The Master-to-source relationship hash changed as intended because 16 source records moved to their audited survivors. The canonical Master-field hash changed only through the documented merge reconciliation; no other business-data edit was performed.

A compressed PostgreSQL backup was created and validated before the writes: `backups/master-identity-pre-correction-20261020.dump` (`pg_restore --list` succeeded). No `docker compose down -v`, reset, delete, or manual source sync was used.

Final full regression ran after all 16 identity corrections on a disposable SQLite database with the workspace code mounted read-only: **185 passed / 0 failed**. Identity policy version 2 and Standardization Engine 21 match in the workspace, running API, and worker.

Closed-dimension regression: sector taxonomy, Activity/Sub-Activity taxonomy, Opportunity Type, Investment Model, Asset/Facility Type, Location/Geographic Eligibility, Status/Lifecycle, Owner/Entity, Deadline/Timeline/Date Semantics, Quantitative/Commercial Fields, Source Link Integrity, and Dashboard Layout all remained covered by the passing full regression suite. No closed-dimension behavior was changed.

## K. Final reconciliation

```ini
FIXED_VALIDATION_SNAPSHOT_UTC = 2026-10-20 09:59:32.899366
MASTER_IDENTITY_DUPLICATE_CROSS_SOURCE_DEEP_REVIEW = NOT_COMPLETE
SNAPSHOT_TOTAL_MASTER_ROWS = 297
SNAPSHOT_NON_MERGED_MASTERS = 276
SNAPSHOT_MERGED_MASTERS = 21
SNAPSHOT_SOURCE_OPPORTUNITIES = 2899
SNAPSHOT_OBSERVATIONS = 11150

IDENTITY_MODEL_EXPLICIT = TRUE
FUZZY_TITLE_ONLY_AUTO_MERGE_ALLOWED = FALSE
SAME_SOURCE_FUZZY_AUTO_MERGE_ALLOWED = FALSE

CANDIDATE_DUPLICATE_PAIRS = 1261
ACTIONABLE_CANDIDATE_PAIRS = 42
RAW_SCREEN_PAIRS_SCREENED_OUT = 1219
SAME_SOURCE_CANDIDATE_PAIRS = 20
SAME_SOURCE_CONFIRMED_DUPLICATES = 0
SAME_SOURCE_CORRECTLY_DISTINCT = 12
SAME_SOURCE_REVIEW_REQUIRED = 8
CROSS_SOURCE_CANDIDATE_PAIRS = 34
CROSS_SOURCE_CONFIRMED_DUPLICATES = 16
CROSS_SOURCE_CORRECTLY_DISTINCT = 16
CROSS_SOURCE_REVIEW_REQUIRED = 2
SAME_AND_CROSS_SOURCE_SCOPE_OVERLAP = 12
RAW_BROAD_SCREEN_HITS = 1261
RAW_SCREEN_EXPLICIT_PARCEL_CONFLICTS = 1082
RAW_SCREEN_BELOW_ACTIONABLE_THRESHOLD = 137
ANALYZER_CROSS_SOURCE_COUNT_1241 = INVALID_METHOD_LABEL_COUNT

FALSE_SPLIT_MASTERS_CONFIRMED = 32
FALSE_SPLIT_PAIRS_CONFIRMED = 16
FALSE_SPLIT_MERGES_APPLIED = 16
SUSPECT_FALSE_MERGES = 1
CONFIRMED_FALSE_MERGES = 0
FALSE_MERGES_CORRECTED = 0

EXISTING_MERGED_MASTERS_AUDITED = 5
EXISTING_MERGES_CONFIRMED_VALID = 5
EXISTING_MERGES_REVIEW_REQUIRED = 0
EXISTING_MERGES_CONFIRMED_INCORRECT = 0

MULTI_SOURCE_MASTERS = 24
MULTI_SOURCE_IDENTITY_CONFIRMED = 23
MULTI_SOURCE_IDENTITY_REVIEW_REQUIRED = 1
MULTI_SOURCE_IDENTITY_INCORRECT = 0

SOURCE_RECORDS_WITH_CURRENT_MASTER = 300
SOURCE_RECORDS_WITHOUT_MASTER = 2599
SOURCE_RECORDS_WITHOUT_CURRENT_MASTER_ACCEPTANCE = BLOCKER
STRICT_ALL_SOURCEOPPORTUNITIES_CURRENT_MASTER_GATE = NOT_PASSED
SOURCE_RECORDS_LINKED_TO_MULTIPLE_CURRENT_MASTERS = 0
NON_MERGED_MASTERS_WITH_ZERO_SOURCES = 0
EXACT_REFERENCE_SPLIT_ACROSS_MASTERS = 0
REFERENCE_COLLISIONS_REQUIRING_REVIEW = 0

CONFIRMED_FALSE_SPLITS_REMAINING = 0
CONFIRMED_FALSE_MERGES_REMAINING = 0
DUPLICATE_REVIEW_QUEUE_OPEN = 10
CORRECTLY_RETAINED_FOR_REVIEW = 10
OPEN_SAME_SOURCE_REVIEW_CASES = 8
OPEN_CROSS_SOURCE_REVIEW_CASES = 2
OPEN_CROSS_SOURCE_REVIEW_MASTER_PAIRS = [[107, 186], [107, 187]]

MERGE_ACTIONS_APPLIED = 16
SOURCE_RELINK_ACTIONS_APPLIED = 16
UNMERGE_SPLIT_ACTIONS_APPLIED = 0

MERGE_AUDIT_PRESERVED = TRUE
MERGES_REVERSIBLE = TRUE
CURRENT_MASTER_LIST_UNIQUENESS = PASSED
SEARCH_MASTER_UNIQUENESS = PASSED
PAGINATION_MASTER_SEMANTICS = PASSED
DASHBOARD_MASTER_COUNT_RECONCILIATION = PASSED
CSV_MASTER_IDENTITY_RECONCILIATION = PASSED
XLSX_MASTER_IDENTITY_RECONCILIATION = PASSED
BROWSER_IDENTITY_VERIFICATION = PASSED

MASTER_IDENTITIES_PRESERVED_OR_AUDITABLY_MERGED = TRUE
TOTAL_MASTER_ROWS_PRESERVED = TRUE
SOURCE_LINKS_PRESERVED = TRUE
RAW_PROVENANCE_PRESERVED = TRUE
OBSERVATION_HISTORY_PRESERVED = TRUE
UNEXPLAINED_BUSINESS_DATA_CHANGES = 0
MANUAL_SOURCE_SYNC_STARTED = FALSE
FULL_REGRESSION_SUITE = 185 passed / 0 failed
FULL_REGRESSION_EXECUTED_AFTER_FINAL_IDENTITY_CORRECTIONS = TRUE

WORKSPACE_STANDARDIZATION_ENGINE_VERSION = 21
RUNNING_API_STANDARDIZATION_ENGINE_VERSION = 21
RUNNING_WORKER_STANDARDIZATION_ENGINE_VERSION = 21
RUNTIME_STANDARDIZATION_PARITY = PASSED
IDENTITY_MATCHING_POLICY_VERSION = 2
```

## Machine-readable artifacts

- `candidate-pairs.csv` (1,261 unique screened pairs with evidence and disposition)
- `candidate-screen-reconciliation.json`
- `confirmed-duplicates.json`
- `confirmed-distinct-pairs.json`
- `multi-source-master-reconciliation.json`
- `existing-merge-audit.json`
- `merge-correction-ledger.json`
- `reconciliation-summary.json`
- `snapshot-pre-correction-live.json`
- `snapshot-post-correction.json`
- `playwright-results.json`
- `export-identity-reconciliation.json`
- `full-regression-results.txt` (original post-correction run)
- `full-regression-final-rerun.txt` (final read-only rerun: 185 passed / 0 failed)
- `acceptance-blocker.json`
- `unlinked-locality-screen.csv`
- `screenshots/`





