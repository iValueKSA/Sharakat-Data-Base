# Wave 4 validation and final source gate

**Review date:** 2026-10-12  
**Scope:** Ten configured source adapters. No additional source integrations were implemented.

## NHC 403 Resolution

The route that repeatedly returned 403 was https://www.nhc.sa/en/investment-opportunities/. It is a public, indexed English category page; prior sync content and current official web content show the same investment categories and qualification/application links exposed by the accessible Arabic copy. It does not expose a unique itemized current opportunity inventory. The [route review](nhc-route-criticality.md) records its earlier successful observation, latest status, route history, content equivalence, and authentication boundary.

The endpoint was intermittent: the standalone NHC sync at 12:24:37 UTC fetched all six routes, while the final ordered run at 12:27:33 UTC received HTTP 403 for the English mirror. A retry at 12:35:37 UTC fetched all six routes successfully. The 403 is retained in route history, and while restricted it cannot produce a zero record count or removals. No private API, authenticated service, or access-control bypass was used.

## Route Criticality

Route snapshots are persisted in each NHC SyncJob.metrics_json record, including URL, route name/type, criticality, HTTP status, health state, last success/failure, consecutive failures, content role, and health/coverage effects. The Arabic category route is CRITICAL; the equivalent English locale, both Real Estate Stimulation information pages, the public intake page, and the qualification shell are SUPPORTING.

In the final ordered run, NHC was HEALTHY / PUBLIC_COVERAGE_LIMITED: 6 routes monitored, 1/1 critical successful, 4/5 supporting successful, 1 supporting route restricted, and 0 parser failures. The immediate NHC retry then returned 200 for all six routes: 1/1 critical and 5/5 supporting, 0 restricted routes, and 0 parser failures. Public scope remains category and qualification monitoring; no itemized current Al-Ahsa opportunity was verified. This is not a claim that no NHC assets are available. reconciliation_safe=false prevents any NHC route failure from inferring removals.

## Furas Live Change Validation

The earlier ordered sync added one Furas source row: official ID/reference 06-26-183737-49010, title beginning “تأجير مواقع مكائن بيع ذاتي لعدد (80) موقعاً…”, at the public [Furas opportunity page](https://furas.momah.gov.sa/ar/opportunity/06-26-183737-49010?type=Investment). It was collected through the Al-Ahsa-filtered Furas source and carries Al-Ahsa/Salmānīyah location evidence. Exact reference matching linked Invest Saudi official ID 54952; it did not create a duplicate source row. The Furas record created Master 230 (AH-20261012120841-1e079990) and the Invest Saudi row was attached to the same Master. The total Master count is 225, one above the 224 baseline; the current sync repeat created no additional Master.

The ID, reference, official URL, location evidence, and exact cross-source reference were checked. The match is one source identity represented in both sources, not a false duplicate. The current Furas sync and the repeated ordered sync both report zero changes after that accepted addition.

## Invest Saudi Live Update Validation

The prior ordered sync reported one source-row update for official ID 54952 (SourceOpportunity 2368) at the [Invest Saudi public API](https://investsaudi.sa/backend/wp-json/v3/investment-projects). The API's own opportunity content remains the 32-unit vending-machine offer with site area 64; the API did not provide a source updatedAt/source_updated_at value. Its unchanged raw API observations remain in SourceObservation.

The update was a valid evidence enrichment after Furas exposed the exact same official opportunity reference: location confidence changed 0.80 → 0.95, method DESCRIPTION_ONLY_EXPLICIT_AL_AHSA → LINKED_FURAS_REFERENCE, qualification false → true, and linked Furas record none → 2831. The evidence now names the exact Furas reference. This did not create a second Master or source row and did not alter Al-Ahsa relevance without evidence; it strengthened the existing cross-source location link.

Sync job 181 recorded the one row update. SystemEvent 232 (SOURCE_RECORD_CROSS_SOURCE_ENRICHED) is the audit entry, including before/after values and source job ID. No Opportunity ChangeHistory row was appropriate because no canonical Master field changed. The latest repeated Invest Saudi run reported zero updates.

## Conflict Increase Analysis

Compared with the earlier 12 taxonomy / 4 field conflicts, the seven newly raised records (IDs 98–104) came from comparing Furas and Invest Saudi representations of reference 06-26-183737-49010:

| Conflict | Values compared | Classification | Resolution |
|---|---|---|---|
| 98 — title | Furas says 80 sites; Invest Saudi says 32 | LEGITIMATE_SOURCE_DIFFERENCE | Preserve both source values; no identity change. |
| 99 — owner | Al-Ahsa Municipality vs generic “Municipality” | LEGITIMATE_SOURCE_DIFFERENCE | Different source specificity; preserve provenance. |
| 100 — area | Furas 160 vs Invest Saudi 64 | LEGITIMATE_SOURCE_DIFFERENCE | Material source disagreement; preserve both values for review. |
| 101 — sector | Furas food-trade activity vs Invest Saudi Real Estate & Construction | TAXONOMY_DIFFERENCE | Legitimate source taxonomy disagreement. |
| 102 — opportunity type | Furas vending activity vs Invest Saudi Real Estate & Construction | TAXONOMY_DIFFERENCE | Legitimate source taxonomy disagreement. |
| 103 — status | Furas “Announced” vs Invest Saudi “unspecified” | NORMALIZATION_BUG | Fixed comparison so unknown status makes no contrary assertion; false conflict resolved and audited. |
| 104 — location | Specific Al-Ahsa site description vs generic “Municipality” | LEGITIMATE_SOURCE_DIFFERENCE | Different source precision; preserve both values. |

The owner, area, title, and location disagreements are not parser or identity errors. The two taxonomy disagreements retain each publisher's own classification. Conflict 103 exposed a normalization defect: an explicit unknown status was treated as disagreement with a known status. Unknown statuses are now non-assertive, the false conflict is resolved, and SystemEvent 231 (CONFLICT_NORMALIZATION_RESOLVED) records the action. No identity error was found. Current open conflicts are 14 taxonomy and 8 field.

## Live Regression Result

Regression checks accept live data changes when parser structure, identity, provenance, and lifecycle behavior remain valid. The prior 1 Furas addition and 1 Invest Saudi source-row enrichment were verified as legitimate, with zero false duplicates, removals, or parser failures: VALID_LIVE_CHANGE. The final repeated ten-source sync then produced zero deltas and zero parser failures: DATA_STABLE. Neither state requires the database to remain frozen.

app/regression.py defines the states DATA_STABLE, VALID_LIVE_CHANGE, UNEXPECTED_DATA_CHANGE, and PARSER_REGRESSION; the unit suite covers each selection path. Unexpected change and parser failure counts in the final ordered sync were both zero.

## Database and Reviews

- Masters: **225** (219 active; 6 historical, including expired/removed records).
- Source opportunity rows: **2,831**; source observations: **7,603**.
- Multi-source Masters: **7**.
- Pending duplicate reviews: **0**; location reviews: **17**; qualification reviews: **0**.
- Open conflicts: **14 taxonomy** and **8 field**.
- The 17 location reviews remain unchanged from Wave 3; the 39 resolved false locality conflicts remain resolved.

## Validation

- Full tests: **93 passed**, with one existing Starlette/httpx deprecation warning.
- API smoke checks: **22**, all HTTP 200.
- CSV export: **225 Master rows**, 21 columns; Arabic text and source columns checked.
- XLSX export: **225 Master rows**, 21 columns; Arabic text, source columns, Arabic worksheet name, and right-to-left layout checked.
- Alembic: **0013_public_coverage_model (head)**.

## Final Ten-Source Gate

| Source | Technical health | Coverage status | Critical routes healthy? | Current public scope | Known limitation |
|---|---|---|---|---|---|
| Furas | HEALTHY | COMPLETE_PUBLIC_SOURCE | Yes | Public Al-Ahsa filtered investment offers | Only offers exposed by the public municipality-filtered catalogue. |
| Al-Ahsa Municipality Platform | HEALTHY | COMPLETE_PUBLIC_SOURCE | Yes | Public municipal opportunities | Limited to exposed public listings. |
| AHDA | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | Yes | Public AHDA investment and project content | Defined public pages; qualification remains item-specific. |
| Invest Saudi | HEALTHY | COMPLETE_PUBLIC_SOURCE | Yes | Four official current public API datasets | Current API population is the source of truth; historical-only rows are preserved separately. |
| KFU | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | Yes | Public university investment opportunities | Defined public pages and attached-document metadata. |
| MODON | HEALTHY | PUBLIC_COVERAGE_LIMITED | Yes | Public product/catalogue, GIS schema, and data catalog | No complete current Al-Ahsa availability inventory; aggregate datasets are reference-only. |
| NCP | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | Yes | Complete English News archive and linked articles | Arabic archive final page remains under maintenance; private investor pipeline excluded. |
| NHC | HEALTHY | PUBLIC_COVERAGE_LIMITED | Yes (1/1) | Public categories and qualification/application paths | No itemized public current inventory; one English supporting route intermittently returns 403. |
| PIF Private Sector Hub | HEALTHY | PUBLIC_COVERAGE_LIMITED | Yes | Public Explore Opportunities and ecosystem route families | No deterministic current opportunity roster or company filter list exposed. |
| MWAN | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | Yes | Public investment offer and investor-card pages | No explicit Al-Ahsa relevance among current offers. |

The repeated ordered sync completed all ten sources. **Healthy: 10; warnings: 0; failed: 0.** The NHC supporting-route restriction observed during the ordered run is represented in route metadata and did not block the defined public monitoring contract; the dedicated retry subsequently received HTTP 200 for all six NHC routes. PIF remains HEALTHY / PUBLIC_COVERAGE_LIMITED.

The final gate is:

SOURCE_INTEGRATION_COMPLETE
