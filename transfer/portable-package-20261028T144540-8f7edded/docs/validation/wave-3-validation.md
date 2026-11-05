# Wave 3 validation and public coverage decision

Validation run: **2026-10-12** (Asia/Amman)  
Scope: seven existing sources, with focused closure of KFU, MODON, and NCP. No Wave 4 sources were implemented.

## Public Coverage Methodology

Expansion readiness uses **PUBLIC_COMPLETENESS**: all discoverable, legitimate, unauthenticated opportunity content in the documented adapter scope has been collected. This is separate from **ABSOLUTE_SOURCE_COMPLETENESS**, which remains unknown when the publisher keeps a wider inventory behind an authenticated or private system.

Technical health describes whether collection is working. Coverage describes what the publisher makes available and what the adapter's scope includes. A healthy adapter can therefore have `PUBLIC_COVERAGE_LIMITED` or `PRIVATE_API_REQUIRED` coverage. Failures collecting a defined public scope remain technical warnings; an empty result never proves a complete zero inventory. Records enter Master Opportunities only with official opportunity or current-availability evidence. Aggregate counts, allocated properties, map features, and historical reports remain reference evidence.

## MODON Public Surface Resolution

The final sync checked **16 public surfaces** across English and Arabic: main opportunity catalog, Investor Journey, product catalog, Industrial City/product information, Shareek, site maps, smart-app information, services, news, ready-built factories, open-data information, and the MODON publisher catalog. All returned HTTP 200; there were no public-surface errors. The adapter also inspects the public catalog's rendered filters and the publicly exposed GIS layer. No login was attempted and the private Sitecore host was not queried.

The public catalog has seven pages with six cards per page, 18 product types, and city filters for **First Industrial City in Al-Ahsa** and **MODON Oasis in Al-Ahsa** (including Arabic names). The current Al-Ahsa filters yielded **0 publicly verified opportunities**. This is not an assertion that no assets are available: the current public UI has no availability field, stable product identifier, or complete live inventory payload. Its result is `publicly_verified_opportunities=0`, `current_al_ahsa_count=null`, coverage `PUBLIC_COVERAGE_LIMITED`.

The public GIS Landbank layer exposes 28 features and location/area/unit fields, but no product or availability field. Sample features were UAE locations; none identified an Al-Ahsa industrial city. It is classified `REFERENCE_ASSET_ONLY` and is excluded from opportunity ingestion. MODON's public materials describe maps, factory information, and allocated-land applications; those are existing or allocated assets, not evidence of current investment availability. The runtime advertises a Sitecore API at a `.local` private host, which was recorded as a limitation and never queried.

### Product availability checks

| Product category | Public catalog | Location / Al-Ahsa filter | Availability field | Stable product ID | Application route observed |
|---|---|---|---|---|---|
| Industrial land | Yes | Yes / Yes | No | Unknown | Yes |
| Ready-built factories | Yes | Yes / Yes | No | Unknown | Yes |
| Warehouses | Yes | Yes / Yes | No | Unknown | Not established |
| Logistics products | Yes | Yes / Yes | No | Unknown | Yes |
| Commercial products | Yes | Yes / Yes | No | Unknown | Not established |

The authoritative MODON geography dictionary contains two supported Al-Ahsa names: **Al-Ahsa First Industrial City** and **MODON Oasis in Al-Ahsa**, in the Eastern Province. The official filters support the English and Arabic names. No current official evidence found in this pass substantiated an Al-Ahsa Second Industrial City / Salwa entry, so none was added. Governorate and coordinates remain null rather than inferred.

### Public Open Data inventory

The public publisher catalog listed 48 dataset IDs. The adapter selected **30 potentially relevant datasets** and successfully checked their documented unauthenticated metadata and resource catalogs. The API scan completed with no errors. The table records each dataset's published period and update frequency. Where the published table had a row-by-industrial-city breakdown, Al-Ahsa rows were present in the current industrial-city data, ready-made factories, facilities/services, and supporting-units/warehouses datasets; producer/factory and historical allocation data are aggregate or historical evidence. No dataset provides a verified current availability status, so **none is suitable for opportunity ingestion**.

| Dataset | Published period | Frequency | Al-Ahsa / availability finding | Use |
|---|---|---|---|---|
| Producer factories dataset for 2023 Q1 | 2023 | Quarterly | Historical city totals; no availability | Reference only |
| Producer factories dataset for 2023 Q2 | 2023 | Quarterly | Historical city totals; no availability | Reference only |
| Producer factories dataset for 2023 Q3 | 2023 | Quarterly | Historical city totals; no availability | Reference only |
| Producer factories dataset for 2023 Q4 | 2023 | Quarterly | Historical city totals; no availability | Reference only |
| Dataset of factories produced semi-annually | 2022 | Yearly | Historical factory totals; no availability | Reference only |
| Industrial cities services and facilities | 2024 | Yearly | Aggregate facilities; no availability | Reference only |
| Industrial cities data | Jan–Mar 2026 | Yearly | Two Al-Ahsa city rows include area/occupancy, not vacant inventory | Reference only |
| Total area of the industrial cities | 2024 | Yearly | City area totals; no availability | Reference only |
| Allocated areas | 2024 | Yearly | Historical allocations; not unallocated stock | Reference only |
| Facilities and services Q2 2026 | Apr–Jun 2026 | Not scheduled | Two Al-Ahsa rows report facility counts, not availability | Reference only |
| Facilities and services | May 2026 | Yearly | Al-Ahsa facility counts; not availability | Reference only |
| Supporting units and warehouses in industrial cities | Mar 2026 | Yearly | Oasis row reports 40 supporting units and 0 warehouses; no availability | Reference only |
| Ready made factories | Mar 2026 | Yearly | Oasis aggregate count 44; not per-unit availability | Reference only |
| Ready Factories Q3 2024 | 2024 | Quarterly | Historical product totals; no current availability | Reference only |
| Modon Product Growth for 2023 Q1 | 2023 | Quarterly | Historical product growth | Reference only |
| Modon Product Growth for 2023 Q2 | 2023 | Quarterly | Historical product growth | Reference only |
| Modon Product Growth for 2023 Q3 | 2023 | Quarterly | Historical product growth | Reference only |
| Modon Product Growth for 2023 Q4 | 2023 | Quarterly | Historical product growth | Reference only |
| Modon products growth dataset presented on a quarterly basis | 2023 | Quarterly | Historical product growth | Reference only |
| Modon Product guide for 2025 | 2025 | Yearly | Product definitions/requirements, no city-level stock | Reference only |
| Financing Solutions Available for Investors in MODON | 2025 | Yearly | Financing information, not inventory | Reference only |
| Investor satisfaction statistics | 2025 | Yearly | Aggregate satisfaction statistics | Reference only |
| Economic activities of industrial cities ISIC | Jan–Sep 2025 | Yearly | Activity classification, not availability | Reference only |
| Safety training in industrial cities | Jan–Sep 2025 | Yearly | Aggregate safety data | Reference only |
| Industrial Safety Fire Stations and Firefighters | 2025 | Yearly | Safety infrastructure counts | Reference only |
| Data Center unit for industrial cities | 2025 | Yearly | Unit counts, not available products | Reference only |
| Number of Data Centers in industrial cities | 2025 | Yearly | City counts, not available products | Reference only |
| Advanced factories | May 2026 | Quarterly | Factory technology counts, not available products | Reference only |
| Number of advanced factories | Jan–Nov 2025 | Quarterly | Historical factory counts | Reference only |
| Attracted Investments in the Logistics Sector 2025 | 2025 | Yearly | Historical investment outcomes, not current stock | Reference only |

Monitoring remains on the public opportunity/product pages, MODON news and Al-Ahsa city announcements, public downloadable documents, and the documented open-data catalog/resource metadata. Technical collection health is **HEALTHY**; no available public evidence establishes a complete current Al-Ahsa inventory.

## NCP Public vs Authenticated Coverage

The adapter checked the public homepage, Media Center, Digital Library, Knowledge Center, sitemap, English News archive, Arabic News archive, and linked official article pages. All five discovery surfaces returned HTTP 200; the sitemap listed 23 URLs. The complete English archive covered 12 pages and 46 linked article detail pages. The Arabic archive returned 44 items across 11 complete pages; its final continuation page returned a maintenance response. English is therefore the complete canonical defined scope; the Arabic mirror is retried and retained as a `PUBLIC_DATA_PARTIAL` limitation.

The crawl identified **44 public project identities**, **45 actionable observations**, and **33 lifecycle observations**. Lifecycle notices are retained against project identity instead of being counted as independent projects. The current identified Al-Ahsa-related public project is the food-safety laboratories EOI, a multi-location project covering Al-Ahsa, Tabuk, Qassim, Hafr Al Batin, and Northern Borders. Its EOI deadline has passed, so it remains `EXPIRED`; its EOMT investment model and all five locations are retained. No Eastern Province-only match is treated as Al-Ahsa. `current_investable_public_projects` remains null because the public announcements do not establish a full current pipeline count.

The Investor Portal shell is reachable without authentication, but its client bundle advertises `http://10.2.2.43:6002/api/v1`, an RFC1918 private API origin for broader project data. The portal API is not publicly available to this integration; no request was made to it and no access control was bypassed. NCP coverage is `COMPLETE_FOR_DEFINED_SCOPE` for the complete English public News archive and its linked article pages, while broader absolute pipeline coverage is `PRIVATE_API_REQUIRED`. Technical health is **HEALTHY**.

An exact duplicate project identity previously created from two NCP announcement aliases was reconciled using matching official URL and normalized title. The merge is audited, both source rows are retained, the alias is detached from the duplicate master, and its event evidence remains preserved. No pending duplicate identity review remains.

## Source Coverage Status Model

`technical_health` and `coverage_status` are independent source fields and appear separately in the API and source dashboard. The supported coverage values are `COMPLETE_PUBLIC_SOURCE`, `COMPLETE_FOR_DEFINED_SCOPE`, `PUBLIC_COVERAGE_LIMITED`, `AUTHENTICATED_SOURCE_REQUIRED`, `PRIVATE_API_REQUIRED`, `PARTIAL_OFFICIAL_COVERAGE`, and `UNKNOWN_COVERAGE`. Technical health uses `HEALTHY`, `WARNING`, `FAILED`, `BLOCKED`, `RATE_LIMITED`, or `PARSER_BROKEN`.

Source limitations are first-class records with type, description, evidence URL, verification times, completeness impact, and resolution. Opportunity rows retain provenance; coverage explanations are shown at source level. The accepted policy is documented in [ADR: Public source completeness and source health](../architecture/adr-public-source-completeness.md).

## Final source classification

Current counts are the latest successful source snapshot's Al-Ahsa-qualified opportunities (AHDA is a public-content publisher, so its seven qualified entries are shown). Retained source rows can include historical and detached alias evidence.

| Source | Technical health | Coverage status | Current opportunity count | Last successful sync (UTC) | Limitation |
|---|---|---|---:|---|---|
| Furas | HEALTHY | COMPLETE_PUBLIC_SOURCE | 134 | 2026-10-12 09:19:59 | None identified in configured public Al-Ahsa scope |
| Al-Ahsa Municipality | HEALTHY | COMPLETE_PUBLIC_SOURCE | 75 | 2026-10-12 09:20:03 | None identified in configured public scope |
| AHDA | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | 7 | 2026-10-12 09:20:27 | Only qualifying investment content is promoted from the public publisher archive |
| Invest Saudi | HEALTHY | COMPLETE_PUBLIC_SOURCE | 7 | 2026-10-12 09:21:16 | 31 historical-only records remain preserved outside the 2,524 current official-ID snapshot |
| KFU | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | 2 | 2026-10-12 09:21:16 | Two official investment notices; one expired and one status unknown; attachment metadata retained |
| MODON | HEALTHY | PUBLIC_COVERAGE_LIMITED | 0 publicly verified | 2026-10-12 09:21:24 | No complete live public Al-Ahsa availability inventory; private Sitecore host not queried |
| NCP | HEALTHY | COMPLETE_FOR_DEFINED_SCOPE | 1 Al-Ahsa-related expired project | 2026-10-12 09:21:49 | Broader investor pipeline uses a private API; Arabic mirror's final page was under maintenance |

## Database, review, and regression state

- Masters: **224** (218 active, 6 historical); source opportunity rows: **2,825**; multi-source masters: **6**.
- Reviews: **0** pending duplicates, **17** pending location reviews, **0** pending qualification reviews.
- Open conflicts: **12 taxonomy** and **4 field**. The 39 resolved false locality conflicts remain resolved; the final sync added no new conflicts.
- MODON location dictionary: **2** entries. Source limitations: **4** records across MODON and NCP. NCP project events: **45** persisted rows.
- The latest ordered sync succeeded for all seven sources. Each reported **0 new, 0 updated, and 0 newly removed**; all source syncs reported zero errors. Invest Saudi reproduced **2,524 current official IDs**, preserved its 31 historical-only rows, and recorded zero newly removed IDs.
- The NCP source-alias reconciliation reduced the duplicate master population by one while preserving the two source rows and merge audit. It does not alter the public project/observation totals.

## Validation checks

- `pytest -q`: **64 passed**, one Starlette/httpx deprecation warning.
- Production sync order: Furas → Al-Ahsa Municipality → AHDA → Invest Saudi → KFU → MODON → NCP; all completed successfully.
- API smoke: **17 checks** returned HTTP 200, including health, dashboard, sources/coverage, limitations, MODON locations, NCP events, validation report, jobs/errors, review/conflict queues, raw/source content, CSV and XLSX.
- CSV export: **224 rows**. XLSX export: **224 rows** (21 columns).
- Alembic current revision: **`0013_public_coverage_model (head)`**.
- The latest jobs have no errors. Four older source-error rows remain in cumulative history and are not current failures.
- Wave 4 sources NHC, PIF, and MWAN were not implemented.

## Expansion Gate Decision

`READY_FOR_WAVE_4`

The five established source integrations and KFU remained stable. MODON's public surfaces and relevant open-data catalog were exhaustively checked for a publicly enumerable current Al-Ahsa opportunity inventory; none was exposed, and map/aggregate assets are excluded from opportunities. NCP's public English announcement scope and lifecycle observations are monitored, while its broader investor pipeline is explicitly identified as private. Both adapters are technically healthy, coverage limitations are first-class and visible, the duplicate review queue is clear, and tests, API checks, exports, and migration head all pass. These publisher-side coverage limits do not block expansion under the documented PUBLIC_COMPLETENESS policy.
